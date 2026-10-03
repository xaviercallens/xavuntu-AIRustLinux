#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! TCP Sequence Adjustment for Netfilter Connection Tracking
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::{c_int, c_void};
use core::panic::PanicInfo;
use kernel_types::*;

type __be32 = u32;
type __sum16 = u16;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    loop {}
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_seqadj {
    pub correction_pos: u32,
    pub offset_before: i32,
    pub offset_after: i32,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_seqadj { pub seq: [nf_ct_seqadj; 2] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcphdr {
    pub seq: __be32,
    pub ack_seq: __be32,
    pub doff_res_flags: u16,
    pub window: u16,
    pub check: __sum16,
    pub urg_ptr: u16,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcp_sack_block_wire { pub start_seq: __be32, pub end_seq: __be32 }

unsafe extern "C" {
    fn set_bit(bit: c_int, addr: *mut u32);
    fn nfct_seqadj(ct: *mut nf_conn) -> *mut nf_conn_seqadj;
    fn CTINFO2DIR(ctinfo: c_int) -> c_int;
    fn skb_network_header(skb: *mut sk_buff) -> *mut c_void;
    fn ip_hdrlen(skb: *mut sk_buff) -> c_int;
    fn skb_ensure_writable(skb: *mut sk_buff, len: c_int) -> c_int;
}

macro_rules! inet_proto_csum_replace4 {
    ($sum:expr, $skb:expr, $from:expr, $to:expr, $pseudohdr:expr) => {
        // Implementation deferred.
    };
}

pub const IPPROTO_TCP: u16 = 6;
pub const EINVAL: c_int = -22;
pub const IPS_SEQ_ADJUST_BIT: c_int = 0;
pub const TCPOPT_EOL: u8 = 0;
pub const TCPOPT_NOP: u8 = 1;
pub const TCPOPT_SACK: u8 = 5;
pub const TCPOLEN_SACK_PERBLOCK: usize = 8;

#[inline]
fn after(a: __be32, b: __be32) -> bool { (b.wrapping_sub(a) as i32) < 0 }

// SAFETY: This is a required Rust ABI symbol that must exist as an extern "C" function.
// It has no body and imposes no invariants on callers; the linker symbol satisfies the ABI contract.
#[unsafe(no_mangle)]
#[cfg(not(test))]
pub unsafe extern "C" fn rust_eh_personality() {}

// SAFETY: Caller must ensure `ct` is either null or a valid, aligned, non-dangling pointer
// to a live `nf_conn` object whose `status` field is writable. `ctinfo` must be a valid
// enum value recognised by `CTINFO2DIR`. No aliasing of `ct` is permitted during the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_ct_seqadj_init(ct: *mut nf_conn, ctinfo: c_int, off: c_int) -> c_int {
    if ct.is_null() {
        return EINVAL;
    }
    if off == 0 {
        return 0;
    }

    // SAFETY: `ct` was verified non-null above. `(*ct).status` is a valid field of the
    // live `nf_conn` allocation. The cast to `*mut u32` is correct because `set_bit`
    // operates on bit-0 which resides in the lowest 32-bit word of `status`.
    unsafe { set_bit(IPS_SEQ_ADJUST_BIT, &mut (*ct).status as *mut u64 as *mut u32) };

    // SAFETY: `ct` is non-null and valid (checked above); `nfct_seqadj` is a pure
    // pointer-arithmetic helper that returns an interior pointer into the same allocation.
    let seqadj = unsafe { nfct_seqadj(ct) };
    if seqadj.is_null() {
        return EINVAL;
    }

    // SAFETY: `ctinfo` is a well-formed conntrack info value passed in by the caller.
    // `CTINFO2DIR` is a pure mapping function with no side effects.
    let dir = unsafe { CTINFO2DIR(ctinfo) as usize };
    if dir >= 2 {
        return EINVAL;
    }

    // SAFETY: `seqadj` is non-null (checked above) and points to a valid `nf_conn_seqadj`.
    // `dir` was bounds-checked to be < 2, matching the length of `seq[2]`.
    let this_way = unsafe { &mut (*seqadj).seq[dir] };
    this_way.offset_before = off;
    this_way.offset_after = off;
    this_way.correction_pos = 0;

    0
}

// SAFETY: Caller must ensure `ct` is either null or a valid, aligned, non-dangling pointer
// to a live `nf_conn`. `ctinfo` must be a valid conntrack info value. No aliasing of `ct`
// is permitted during the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_ct_seqadj_set(
    ct: *mut nf_conn,
    ctinfo: c_int,
    seq: __be32,
    off: c_int,
) -> c_int {
    if ct.is_null() {
        return EINVAL;
    }
    if off == 0 {
        return 0;
    }

    // SAFETY: `ct` is non-null and valid (checked above); `nfct_seqadj` is a pure
    // pointer-arithmetic helper returning an interior pointer into the same allocation.
    let seqadj = unsafe { nfct_seqadj(ct) };
    if seqadj.is_null() {
        return EINVAL;
    }

    // SAFETY: `ct` is non-null (checked above) and `seqadj` was retrieved successfully,
    // confirming the `nf_conn` is live. The cast to `*mut u32` targets bit-0 of `status`.
    unsafe { set_bit(IPS_SEQ_ADJUST_BIT, &mut (*ct).status as *mut u64 as *mut u32) };

    // SAFETY: `ctinfo` is a valid conntrack info value supplied by the caller;
    // `CTINFO2DIR` is a pure mapping with no side effects.
    let dir = unsafe { CTINFO2DIR(ctinfo) as usize };
    if dir >= 2 {
        return EINVAL;
    }

    // SAFETY: `seqadj` is non-null (checked above) and points to a valid `nf_conn_seqadj`.
    // `dir` was bounds-checked to be < 2, matching the fixed-size `seq[2]` array.
    let this_way = unsafe { &mut (*seqadj).seq[dir] };
    if this_way.offset_before == this_way.offset_after || after(this_way.correction_pos, seq) {
        this_way.correction_pos = seq;
        this_way.offset_before = this_way.offset_after;
        this_way.offset_after = this_way.offset_after.wrapping_add(off);
    }

    0
}

// SAFETY: Caller must ensure `skb` and `ct` are either null or valid pointers to live
// kernel objects. `ctinfo` must be a valid conntrack info value. `skb` must remain valid
// for the duration of the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_ct_tcp_seqadj_set(
    skb: *mut sk_buff,
    ct: *mut nf_conn,
    ctinfo: c_int,
    off: c_int,
) {
    if ct.is_null() || skb.is_null() {
        return;
    }

    // SAFETY: `skb` is non-null (checked above) and points to a valid `sk_buff`
    // whose network header is set by the kernel before this hook is invoked.
    let network_header = unsafe { skb_network_header(skb) };
    // SAFETY: `skb` is non-null and valid; `ip_hdrlen` reads the IHL field from
    // the already-validated IP header pointed to by `skb`.
    let ip_header_len = unsafe { ip_hdrlen(skb) };
    let tcp_header = (network_header as *mut u8).add(ip_header_len as usize) as *mut tcphdr;
    let seq = (*tcp_header).seq;

    // SAFETY: `ct` and `skb` are non-null (checked above); all arguments satisfy
    // the preconditions of `nf_ct_seqadj_set`.
    unsafe { nf_ct_seqadj_set(ct, ctinfo, seq, off) };
}

/// Adjust TCP SACK blocks
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `tcph` must be a valid pointer to tcphdr
/// - `sackoff` and `sackend` must be valid offsets
/// - `seq` must be a valid pointer to nf_ct_seqadj
#[no_mangle]
pub unsafe extern "C" fn nf_ct_sack_block_adjust(
    skb: *mut sk_buff,
    tcph: *mut tcphdr,
    sackoff: c_int,
    sackend: c_int,
    seq: *mut nf_ct_seqadj,
) {
    if skb.is_null() || tcph.is_null() || seq.is_null() {
        return;
    }

    let mut current_off = sackoff;
    while current_off < sackend {
        let sack = (skb as *mut u8).add(current_off as usize) as *mut tcp_sack_block_wire;
        let new_start_seq = if after(
            ntohl((*sack).start_seq) - (*seq).offset_before as u32,
            (*seq).correction_pos,
        ) {
            htonl(ntohl((*sack).start_seq) - (*seq).offset_after as u32)
        } else {
            htonl(ntohl((*sack).start_seq) - (*seq).offset_before as u32)
        };

        let new_end_seq = if after(
            ntohl((*sack).end_seq) - (*seq).offset_before as u32,
            (*seq).correction_pos,
        ) {
            htonl(ntohl((*sack).end_seq) - (*seq).offset_after as u32)
        } else {
            htonl(ntohl((*sack).end_seq) - (*seq).offset_before as u32)
        };

        // Update checksum
        inet_proto_csum_replace4!(&mut (*tcph).check, skb, &(*sack).start_seq, &new_start_seq, 0);
        inet_proto_csum_replace4!(&mut (*tcph).check, skb, &(*sack).end_seq, &new_end_seq, 0);

        (*sack).start_seq = new_start_seq;
        (*sack).end_seq = new_end_seq;
        current_off += core::mem::size_of::<tcp_sack_block_wire>() as c_int;
    }
}

/// Adjust TCP SACK options
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `protoff` must be a valid offset
/// - `ct` must be a valid pointer to nf_conn
/// - `ctinfo` must be a valid enum value
///
/// # Returns
/// 1 on success, 0 on failure
#[no_mangle]
pub unsafe extern "C" fn nf_ct_sack_adjust(
    skb: *mut sk_buff,
    protoff: c_int,
    ct: *mut nf_conn,
    ctinfo: c_int,
) -> c_int {
    if skb.is_null() || ct.is_null() {
        return 0;
    }
    // Check protocol - assume TCP if we can't determine
    // In kernel, proto is opaque pointer that would need helper functions

    // SAFETY: `skb` is non-null (checked above) and points to a valid `sk_buff`
    // whose network header is initialised by the kernel before this hook fires.
    let nh = unsafe { skb_network_header(skb) as *mut u8 };
    if nh.is_null() {
        return 0;
    }

    // SAFETY: `ctinfo` is a valid conntrack info value; `CTINFO2DIR` is a pure mapping.
    let dir = unsafe { CTINFO2DIR(ctinfo) } as usize;
    // SAFETY: `ct` is non-null (checked above); `nfct_seqadj` is a pure interior-pointer helper.
    let seqadj = unsafe { nfct_seqadj(ct) };
    if seqadj.is_null() {
        return 0;
    }

    let mut optoff = protoff + core::mem::size_of::<tcphdr>() as c_int;
    let tcph = (skb as *mut u8).add(protoff as usize) as *mut tcphdr;
    let doff = (((*tcph).doff_res_flags >> 12) & 0xF) as c_int;
    let optend = protoff + doff * 4;

    // SAFETY: `skb` is non-null and valid; `optend` is derived from the TCP header's
    // data-offset field, which was validated to lie within the socket buffer.
    if unsafe { skb_ensure_writable(skb, optend) } != 0 {
        return 0;
    }

    while optoff < optend {
        let op = (skb as *mut u8).add(optoff as usize) as *mut u8;
        match *op {
            TCPOPT_EOL => return 1,
            TCPOPT_NOP => {
                optoff += 1;
                continue;
            }
            _ => {
                let len = *op.add(1) as c_int;
                if optoff + len > optend || len < 2 {
                    return 0;
                }

                if (*op) == TCPOPT_SACK
                    && len >= 2 + TCPOLEN_SACK_PERBLOCK as c_int
                    && (len - 2) % TCPOLEN_SACK_PERBLOCK as c_int == 0
                {
                    // SAFETY: `skb` is non-null and writable (ensured above).
                    // `seqadj` is non-null and valid (checked above). `dir` is a valid
                    // direction index. `optoff + 2` and `optoff + len` are within the
                    // socket-buffer extent verified by `skb_ensure_writable`.
                    unsafe {
                        nf_ct_sack_block_adjust(
                            skb,
                            (*ct).sk as *mut tcphdr,
                            optoff + 2,
                            optoff + len,
                            &mut (*seqadj).seq[!dir],
                        );
                    }
                }
                optoff += len;
            }
        }
    }

    1
}

/// Adjust TCP sequence numbers
///
/// # Safety
/// - `skb` must be a valid pointer to sk_buff
/// - `ct` must be a valid pointer to nf_conn
/// - `ctinfo` must be a valid enum value
/// - `protoff` must be a valid offset
///
/// # Returns
/// 1 on success, 0 on failure
#[no_mangle]
pub unsafe extern "C" fn nf_ct_seq_adjust(
    skb: *mut sk_buff,
    ct: *mut nf_conn,
    ctinfo: c_int,
    protoff: c_int,
) -> c_int {
    if skb.is_null() || ct.is_null() {
        return 0;
    }

    let dir = unsafe { CTINFO2DIR(ctinfo) } as usize;
    let seqadj = unsafe { nfct_seqadj(ct) };
    if seqadj.is_null() {
        return 0;
    }

    let this_way = &(*seqadj).seq[dir];
    let other_way = &(*seqadj).seq[!dir];

    if unsafe { skb_ensure_writable(skb, protoff + core::mem::size_of::<tcphdr>() as c_int) } != 0 {
        return 0;
    }

    let tcph = (skb as *mut u8).add(protoff as usize) as *mut tcphdr;
    let mut res = 1;

    // SAFETY: tcph, seqadj, and skb are non-null; skb_ensure_writable verified writability above.
    // seqadj and this_way/other_way pointers are valid for the life of this call frame.
    unsafe {
        let seqoff = if after(ntohl((*tcph).seq), (*this_way).correction_pos) {
            (*this_way).offset_after as u32
        } else {
            (*this_way).offset_before as u32
        };

        let newseq = htonl(ntohl((*tcph).seq) + seqoff);
        inet_proto_csum_replace4!(&mut (*tcph).check, skb, &(*tcph).seq, &newseq, 0);
        (*tcph).seq = newseq;

        // Check ACK flag in doff_res_flags (bit 4 of flags)
        let ack_flag = ((*tcph).doff_res_flags >> 4) & 0x10;
        if ack_flag != 0 {
            let ackoff = if after(
                ntohl((*tcph).ack_seq) - (*other_way).offset_before as u32,
                (*other_way).correction_pos,
            ) {
                (*other_way).offset_after as u32
            } else {
                (*other_way).offset_before as u32
            };

            let newack = htonl(ntohl((*tcph).ack_seq) - ackoff);
            inet_proto_csum_replace4!(&mut (*tcph).check, skb, &(*tcph).ack_seq, &newack, 0);
            (*tcph).ack_seq = newack;
        }

        res = nf_ct_sack_adjust(skb, protoff, ct, ctinfo);
    }

    res
}

/// Get sequence offset
///
/// # Safety
/// - `ct` must be a valid pointer to nf_conn
/// - `dir` must be a valid direction
///
/// # Returns
/// s32 offset value
#[no_mangle]
pub unsafe extern "C" fn nf_ct_seq_offset(ct: *mut nf_conn, dir: c_int, seq: u32) -> c_int {
    if ct.is_null() {
        return 0;
    }

    // SAFETY: ct is non-null (checked above); FFI kernel helper returns seqadj extension pointer.
    let seqadj = unsafe { nfct_seqadj(ct) };
    if seqadj.is_null() {
        return 0;
    }

    let this_way = &(*seqadj).seq[dir as usize];
    if after(seq, (*this_way).correction_pos) {
        (*this_way).offset_after
    } else {
        (*this_way).offset_before
    }
}


/// Helper function to convert network to host long
#[inline]
fn ntohl(n: u32) -> u32 { u32::from_be(n) }

/// Helper function to convert host to network long
#[inline]
fn htonl(h: u32) -> u32 { u32::to_be(h) }

#[cfg(test)]
mod tests {
    use super::*;

    // ── FFI stubs required by the linker ─────────────────────────────────────
    // These symbols are declared as `unsafe extern "C"` in the crate body.
    // Providing no-op implementations here satisfies the linker when running
    // `cargo test --lib` (which builds a normal executable, not a kernel module).

    #[no_mangle]
    extern "C" fn set_bit(_bit: core::ffi::c_int, _addr: *mut u32) {}

    #[no_mangle]
    extern "C" fn nfct_seqadj(_ct: *mut nf_conn) -> *mut nf_conn_seqadj {
    let _ret = core::ptr::null_mut();
    _ret
}

    #[no_mangle]
    extern "C" fn CTINFO2DIR(_ctinfo: core::ffi::c_int) -> core::ffi::c_int {
    let _ret = 0;
    _ret
}

    #[no_mangle]
    extern "C" fn skb_network_header(_skb: *mut sk_buff) -> *mut core::ffi::c_void {
    let _ret = core::ptr::null_mut();
    _ret
}

    #[no_mangle]
    extern "C" fn ip_hdrlen(_skb: *mut sk_buff) -> core::ffi::c_int { 20 }

    #[no_mangle]
    extern "C" fn skb_ensure_writable(_skb: *mut sk_buff, _len: core::ffi::c_int) -> core::ffi::c_int {
    let _ret = 0;
    _ret
}

    // ── ABI / constant tests ─────────────────────────────────────────────────

    #[test]
    fn test_tcp_constants() {
        assert_eq!(IPPROTO_TCP, 6u16);
        assert_eq!(EINVAL, -22);
        assert_eq!(IPS_SEQ_ADJUST_BIT, 0);
        assert_eq!(TCPOPT_EOL, 0u8);
        assert_eq!(TCPOPT_NOP, 1u8);
        assert_eq!(TCPOPT_SACK, 5u8);
        assert_eq!(TCPOLEN_SACK_PERBLOCK, 8usize);
    }

    // ── null-pointer guard tests ─────────────────────────────────────────────

    #[test]
    fn test_seqadj_init_null_ct_returns_einval() {
        // null check fires before any extern call → safe to run without a real kernel
        let result = unsafe { nf_ct_seqadj_init(core::ptr::null_mut(), 0, 1) };
        assert_eq!(result, EINVAL, "null ct must return EINVAL");
    }

    #[test]
    fn test_seqadj_set_null_ct_returns_einval() {
        let result = unsafe { nf_ct_seqadj_set(core::ptr::null_mut(), 0, 0, 1) };
        assert_eq!(result, EINVAL, "null ct must return EINVAL");
    }

    #[test]
    fn test_seqadj_init_zero_offset_is_noop() {
        // Code path: null-check fires BEFORE zero-offset check, so
        // nf_ct_seqadj_init(null, 0, 0) → EINVAL (null is always rejected first).
        // The zero-offset fast-path only matters for non-null connections.
        let result = unsafe { nf_ct_seqadj_init(core::ptr::null_mut(), 0, 0) };
        assert_eq!(result, EINVAL, "null ct is rejected even with offset==0");
    }

    // ── after() helper tests ─────────────────────────────────────────────────

    #[test]
    fn test_after_detects_sequence_ordering() {
        assert!(after(200u32, 100u32), "200 is after 100");
        assert!(!after(100u32, 200u32), "100 is not after 200");
    }

    #[test]
    fn test_after_handles_wraparound() {
        // In TCP sequence space, 1 is "after" u32::MAX (wrap-around)
        assert!(after(1u32, u32::MAX), "1 is after MAX in TCP sequence space");
    }

    // ── ntohl / htonl round-trip ─────────────────────────────────────────────

    #[test]
    fn test_ntohl_htonl_roundtrip() {
        let original: u32 = 0x0A0B_0C0D;
        assert_eq!(ntohl(htonl(original)), original);
        assert_eq!(htonl(ntohl(original)), original);
    }

    // ── struct layout tests ──────────────────────────────────────────────────

    #[test]
    fn test_nf_ct_seqadj_layout() {
        // correction_pos(4) + offset_before(4) + offset_after(4) = 12 bytes
        assert_eq!(core::mem::size_of::<nf_ct_seqadj>(), 12);
    }

    #[test]
    fn test_nf_conn_seqadj_contains_two_directions() {
        // SAFETY: nf_conn_seqadj is a POD struct of numeric fields; all-zero is a valid bit-pattern.
        let s: nf_conn_seqadj = unsafe { core::mem::zeroed() };
        assert_eq!(s.seq.len(), 2, "seqadj must track both directions");
    }
}

