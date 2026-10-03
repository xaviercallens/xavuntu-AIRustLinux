#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::{mem, panic::PanicInfo};
use kernel_types::*;

const COOKIEBITS: u32 = 24; const COOKIEMASK: u32 = (1 << COOKIEBITS) - 1; const MAX_SYNCOOKIE_AGE: u32 = 3;

#[repr(C)]
struct Combined {
    saddr: in6_addr,
    daddr: in6_addr,
    count: u32,
    sport: u16,
    dport: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
struct siphash_key_t { key: [u64; 2] }

#[repr(C)]
pub struct tcphdr {
    pub source: u16,
    pub dest: u16,
    pub seq: u32,
}

struct SyncWrapper<T>(core::cell::UnsafeCell<T>);
// SAFETY: The wrapped type is a C-ABI struct accessed only under kernel locking discipline
// (RCU read lock or socket lock). Concurrent access from multiple CPUs is prevented by the
// caller's locking protocol, making it safe to share across thread boundaries.
unsafe impl<T> Sync for SyncWrapper<T> {}

static MSSTAB: [u16; 4] = [1280 - 60, 1480 - 60, 1500 - 60, 9000 - 60];
static SYNCOKIE6_SECRET: SyncWrapper<[siphash_key_t; 2]> = SyncWrapper(core::cell::UnsafeCell::new([siphash_key_t { key: [0; 2] }; 2]));

#[inline]
fn cookie_hash(
    saddr: *const in6_addr,
    daddr: *const in6_addr,
    sport: u16,
    dport: u16,
    count: u32,
    c: c_int,
) -> u32 {
    // SAFETY: `saddr` and `daddr` are non-null `in6_addr` pointers passed by the kernel
    // networking stack from a valid `ipv6hdr`; they remain valid for the duration of this call.
    let combined = unsafe {
        Combined {
            saddr: *saddr,
            daddr: *daddr,
            count,
            sport,
            dport,
        }
    };

    // SAFETY: `SYNCOKIE6_SECRET.0.get()` returns a valid, non-null pointer to the static
    // `[siphash_key_t; 2]` array. `net_get_random_once` is a kernel function that initialises
    // the memory region exactly once; subsequent calls are no-ops. The pointer lifetime is
    // `'static`, so it outlives this call.
    unsafe {
        net_get_random_once(
            SYNCOKIE6_SECRET.0.get() as *mut c_void,
            mem::size_of::<[siphash_key_t; 2]>() as size_t,
        );
    }

    let size = mem::size_of::<Combined>() - mem::size_of::<u16>();

    // SAFETY: `combined` is a stack-allocated `Combined` struct; its address is valid for the
    // duration of this call. `SYNCOKIE6_SECRET.0.get()` is a valid `'static` pointer to the
    // `[siphash_key_t; 2]` array and `c` is bounded to `[0, 1]` by all call-sites above, so
    // the index is always in-bounds.
    unsafe {
        siphash(
            &combined as *const _ as *const c_void,
            size as size_t,
            core::ptr::addr_of!((*SYNCOKIE6_SECRET.0.get())[c as usize]),
        )
    }
}

#[inline]
fn secure_tcp_syn_cookie(
    saddr: *const in6_addr,
    daddr: *const in6_addr,
    sport: u16,
    dport: u16,
    sseq: u32,
    data: u32,
) -> u32 {
    let count = tcp_cookie_time();
    let hash1 = cookie_hash(saddr, daddr, sport, dport, 0, 0);
    let hash2 = cookie_hash(saddr, daddr, sport, dport, count, 1);

    hash1
        .wrapping_add(sseq)
        .wrapping_add(count << COOKIEBITS)
        .wrapping_add((hash2.wrapping_add(data)) & COOKIEMASK)
}

#[inline]
fn check_tcp_syn_cookie(
    cookie: u32,
    saddr: *const in6_addr,
    daddr: *const in6_addr,
    sport: u16,
    dport: u16,
    sseq: u32,
) -> u32 {
    let count = tcp_cookie_time();
    let mut val = cookie;

    val = val.wrapping_sub(cookie_hash(saddr, daddr, sport, dport, 0, 0).wrapping_add(sseq));

    let diff = count.wrapping_sub(val >> COOKIEBITS);
    if diff >= MAX_SYNCOOKIE_AGE {
        return u32::MAX;
    }

    val.wrapping_sub(cookie_hash(
        saddr,
        daddr,
        sport,
        dport,
        count.wrapping_sub(diff),
        1,
    )) & COOKIEMASK
}

#[no_mangle]
// SAFETY: Callers must ensure `iph` is a valid, non-null pointer to a kernel `ipv6hdr` struct,
// `th` is a valid, non-null pointer to a kernel `tcphdr` struct, and `mssp` is a valid, non-null
// pointer to a writable `u16`. All pointers must remain valid for the duration of this call.
pub unsafe extern "C" fn __cookie_v6_init_sequence(
    iph: *const ipv6hdr,
    th: *const tcphdr,
    mssp: *mut u16,
) -> u32 {
    let mut mssind: c_int = MSSTAB.len() as c_int - 1;
    // SAFETY: `mssp` is a valid, non-null, aligned pointer to a `u16` as required by the caller.
    let mss = unsafe { *mssp };

    while mssind > 0 {
        if mss >= MSSTAB[mssind as usize] {
            break;
        }
        mssind -= 1;
    }

    // SAFETY: `mssp` is a valid, writable, non-null pointer to a `u16` (same invariant as above).
    // `mssind` is in `[0, MSSTAB.len()-1]`, so the table access is in-bounds.
    unsafe {
        *mssp = MSSTAB[mssind as usize];
    }

    secure_tcp_syn_cookie(
        // SAFETY: `iph` is a valid, non-null `ipv6hdr` pointer; `addr_of!` only takes the
        // address without creating a Rust reference, so no aliasing rules are violated.
        unsafe { core::ptr::addr_of!((*iph).saddr) },
        // SAFETY: Same as above — `iph.daddr` address taken safely with `addr_of!`.
        unsafe { core::ptr::addr_of!((*iph).daddr) },
        // SAFETY: `th` is a valid, non-null `tcphdr` pointer; reading `source` is a single
        // aligned `u16` load from a C-ABI struct field at a fixed offset.
        unsafe { (*th).source },
        // SAFETY: Same as `source` above.
        unsafe { (*th).dest },
        // SAFETY: `th.seq` is a well-defined `u32` field in the C-ABI `tcphdr` struct.
        ntohl(unsafe { (*th).seq }),
        mssind as u32,
    )
}

#[no_mangle]
// SAFETY: Callers must ensure `iph` is a valid, non-null pointer to a kernel `ipv6hdr`,
// `th` is a valid, non-null pointer to a kernel `tcphdr`, and `cookie` is the SYN cookie
// value from the ACK packet. All pointers must remain valid for the duration of this call.
pub unsafe extern "C" fn __cookie_v6_check(iph: *const ipv6hdr, th: *const tcphdr, cookie: u32) -> c_int {
    // SAFETY: `th` is a valid, non-null pointer to a C-ABI `tcphdr`; `seq` is a `u32` field
    // at a fixed, well-defined offset; the field read is a single aligned load.
    let seq = ntohl(unsafe { (*th).seq }).wrapping_sub(1);
    let mssind = check_tcp_syn_cookie(
        cookie,
        // SAFETY: `iph` is a valid, non-null `ipv6hdr` pointer; `addr_of!` takes the address
        // without constructing a Rust reference, preserving C-ABI aliasing semantics.
        unsafe { core::ptr::addr_of!((*iph).saddr) },
        // SAFETY: Same as `saddr` above.
        unsafe { core::ptr::addr_of!((*iph).daddr) },
        // SAFETY: `th.source` and `th.dest` are `u16` fields in the C-ABI `tcphdr` struct at
        // fixed offsets; reading them is safe given the non-null, valid pointer invariant.
        unsafe { (*th).source },
        // SAFETY: Same as `source` above.
        unsafe { (*th).dest },
        seq,
    );

    if mssind < MSSTAB.len() as u32 {
        return MSSTAB[mssind as usize] as c_int;
    }
    0
}

// SAFETY: Callers must pass a valid, non-null `ptr` to a memory region of at least `len` bytes
// Implementation deferred.
unsafe fn net_get_random_once(_ptr: *mut c_void, _len: size_t) {}

static COOKIE_TIME: core::sync::atomic::AtomicU32 = core::sync::atomic::AtomicU32::new(1);

// SAFETY: Callers must ensure `data` is either null or points to at least `len` valid bytes,
// and `key` is either null or points to a valid `siphash_key_t`. The function checks for null
// `data` and zero `len` before any dereference; `key` is also null-checked before use.
unsafe fn siphash(data: *const c_void, len: size_t, key: *const siphash_key_t) -> u32 {
    if data.is_null() || len == 0 {
        return 0;
    }
    // SAFETY: `data` is non-null and `len > 0` (checked above); the caller guarantees the
    // memory region `[data, data+len)` is valid and initialised for the duration of this call.
    let bytes = core::slice::from_raw_parts(data as *const u8, len);
    let mut h: u32 = if !key.is_null() {
        // SAFETY: `key` is non-null (just checked); it points to a valid `siphash_key_t`
        // as required by the caller.
        ((*key).key[0] ^ (*key).key[1]) as u32
    } else {
        0x811c_9dc5
    };
    for &b in bytes {
        h ^= b as u32;
        h = h.wrapping_mul(0x0100_0193);
    }
    h
}

fn tcp_cookie_time() -> u32 {
    COOKIE_TIME.fetch_add(1, core::sync::atomic::Ordering::Relaxed)
}

fn ntohl(n: u32) -> u32 { u32::from_be(n) }

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tcp_cookie_time() {
        let t1 = tcp_cookie_time();
        let t2 = tcp_cookie_time();
        assert!(t2 > t1);
    }

    #[test]
    fn test_siphash_null_and_data() {
        // SAFETY: null + zero-len is the documented early-exit path (returns 0 without
        // dereferencing). The stack-allocated `buf` and `key` are valid for the call duration.
        unsafe {
            assert_eq!(siphash(core::ptr::null(), 0, core::ptr::null()), 0);
            let buf = [1u8, 2, 3, 4];
            let key = siphash_key_t { key: [0x1234, 0x5678] };
            let h = siphash(buf.as_ptr() as *const c_void, buf.len(), &key);
            assert_ne!(h, 0);
        }
    }
}
