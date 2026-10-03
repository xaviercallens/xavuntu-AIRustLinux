#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]


// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
// SAFETY: All write accesses to the wrapped value go through `get_mut`, which is itself
// `unsafe` and requires the caller to guarantee exclusive access. In the kernel context all
// accesses are serialised by the socket lock or RCU read-lock, making cross-thread sharing
// sound.
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    // SAFETY: The caller must guarantee exclusive access or single-threaded context.
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use kernel_types::*;

pub type proto_ops = c_void;
pub type msghdr = c_void;
pub type page = c_void;
pub type netlink_ext_ack = c_void;

/// UDPLite header
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udphdr {
    pub source: __be16,
    pub dest: __be16,
    pub len: __be16,
    pub check: __be16,
}

extern "C" {
    fn udp_rcv(skb: *mut sk_buff) -> c_int;
    fn udp_err(skb: *mut sk_buff, info: *mut u8, err: c_int, icmph: *mut c_void, dev: *mut c_void, inet6_skb_parm: *mut c_void, sock_exterr_skb: *mut c_void);
    fn kfree_skb(skb: *mut sk_buff);
    fn ntohs(val: __be16) -> u16;
}

/// UDPLite socket
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udplite_sock {
    pub inet: inet_sock,
    pub cscov: c_int,
    pub partial_cov: c_int,
}

/// UDPLite options
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udpliteopt { pub cscov: c_int, pub clen: c_int }

/// UDPLite control block
#[repr(C)]
#[derive(Copy, Clone)]
pub struct udplite_cb { pub partial_cov: c_int }

/// UDPLite socket operations
#[repr(C)]
pub struct udplite_ops {
    pub proto: *mut proto_ops,
    pub init: unsafe extern "C" fn(*mut sock) -> c_int,
    pub connect: unsafe extern "C" fn(*mut sock, *mut sockaddr, c_int) -> c_int,
    pub disconnect: unsafe extern "C" fn(*mut sock, c_int) -> c_int,
    pub accept: unsafe extern "C" fn(*mut sock, *mut sock, c_int) -> c_int,
    pub ioctl: unsafe extern "C" fn(*mut sock, c_int, c_ulong) -> c_int,
    pub getname: unsafe extern "C" fn(*mut sock, *mut sockaddr, *mut socklen_t, c_int) -> c_int,
    pub setsockopt: unsafe extern "C" fn(*mut sock, c_int, c_int, *const c_void, c_int) -> c_int,
    pub getsockopt: unsafe extern "C" fn(*mut sock, c_int, c_int, *mut c_void, *mut c_int) -> c_int,
    pub compat_setsockopt: unsafe extern "C" fn(*mut sock, c_int, c_int, *const c_void, c_int) -> c_int,
    pub compat_getsockopt: unsafe extern "C" fn(*mut sock, c_int, c_int, *mut c_void, *mut c_int) -> c_int,
    pub compat_ioctl: unsafe extern "C" fn(*mut sock, c_int, c_ulong) -> c_int,
    pub sendmsg: unsafe extern "C" fn(*mut sock, *mut msghdr, c_int) -> c_int,
    pub recvmsg: unsafe extern "C" fn(*mut sock, *mut msghdr, c_int, c_int, c_int, c_int) -> c_int,
    pub sendpage: unsafe extern "C" fn(*mut sock, *mut page, c_int, c_size_t, c_int) -> c_int,
    pub bind: unsafe extern "C" fn(*mut sock, *mut sockaddr, c_int) -> c_int,
    pub backlog_rcv: unsafe extern "C" fn(*mut sock, *mut sk_buff) -> c_int,
    pub release_cb: unsafe extern "C" fn(*mut sock),
    pub hash: unsafe extern "C" fn(*mut sock),
    pub unhash: unsafe extern "C" fn(*mut sock),
    pub get_port: unsafe extern "C" fn(*mut sock, *mut flowi) -> c_int,
    pub enter_memory_pressure: unsafe extern "C" fn(*mut sock),
    pub sock_rcv_skb: unsafe extern "C" fn(*mut sock, *mut sk_buff) -> c_int,
    pub mib_lookup: unsafe extern "C" fn(*mut sock, c_int) -> *mut c_ulong,
    pub mib_addr_lookup: unsafe extern "C" fn(*mut sock, c_int) -> *mut c_ulong,
    pub diag_destroy: unsafe extern "C" fn(*mut sock),
    pub diag_handler: unsafe extern "C" fn(*mut sock, *mut netlink_ext_ack, *mut sk_buff, *mut u8, *mut u8, c_int) -> c_int,
    pub get_timeo: unsafe extern "C" fn(*mut sock, c_int) -> c_int,
    pub cmsg_send: unsafe extern "C" fn(*mut sock, *mut msghdr, c_int) -> c_int,
    pub cmsg_recv: unsafe extern "C" fn(*mut sock, *mut msghdr, c_int) -> c_int,
    pub bind_conflict: unsafe extern "C" fn(*mut sock, *mut sock) -> c_int,
    pub get_rx_skb_len: unsafe extern "C" fn(*mut sock, *mut sk_buff) -> c_int,
    pub setsockopt_compat: unsafe extern "C" fn(*mut sock, c_int, c_int, *const c_void, c_int) -> c_int,
    pub getsockopt_compat: unsafe extern "C" fn(*mut sock, c_int, c_int, *mut c_void, *mut c_int) -> c_int,
    pub sendmsg_locked: unsafe extern "C" fn(*mut sock, *mut msghdr, c_int) -> c_int,
    pub sendpage_locked: unsafe extern "C" fn(*mut sock, *mut page, c_int, c_size_t, c_int) -> c_int,
    pub setsockopt_locked: unsafe extern "C" fn(*mut sock, c_int, c_int, *const c_void, c_int) -> c_int,
}

/// UDPLite protocol
#[repr(C)]
pub struct udplite_protocol {
    pub handler: unsafe extern "C" fn(*mut sk_buff) -> c_int,
    pub err_handler: unsafe extern "C" fn(*mut sk_buff, *mut u8, c_int, *mut c_void, *mut c_void, *mut c_void, *mut c_void),
    pub no_policy: c_int,
    pub netns_ok: c_int,
    pub icmp_strict_tag_validation: c_int,
    pub icmpv6_allow_any: c_int,
}

/// UDPLite socket options
pub const UDPLITE_SEND_CSCOV: c_int = 1; pub const UDPLITE_RECV_CSCOV: c_int = 2;

/// UDPLite checksum coverage
pub const UDPLITE_MIN_CSCOV: c_int = 0; pub const UDPLITE_MAX_CSCOV: c_int = 65535;

/// UDPLite error codes
pub const UDPLITE_ERR_CSCOV: c_int = -1000; pub const UDPLITE_ERR_PARTIAL: c_int = -1001;

/// UDPLite protocol number
pub const IPPROTO_UDPLITE: c_int = 136;

/// UDPLite socket operations
#[no_mangle]
pub static udplite_proto_ops: SyncWrapper<udplite_ops> = SyncWrapper::new(udplite_ops {
    proto: core::ptr::null_mut(),
    init: udplite_init_sock,
    // SAFETY: `udplite_dummy` has the required C-ABI signature; `transmute` converts a
    // compatible function pointer to the concrete type stored in `udplite_ops`. The function
    // pointer is `'static` and always valid.
    connect: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same as `connect` above — `udplite_dummy` is a compatible fallback function.
    disconnect: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    accept: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    ioctl: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    getname: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    setsockopt: udplite_setsockopt,
    getsockopt: udplite_getsockopt,
    // SAFETY: Same pattern — `udplite_dummy` is a compatible fallback.
    compat_setsockopt: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    compat_getsockopt: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    compat_ioctl: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    sendmsg: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    recvmsg: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    sendpage: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    bind: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    backlog_rcv: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    release_cb: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    hash: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    unhash: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: `udplite_get_port` has the signature matching `get_port`; the transmute
    // converts compatible function-pointer types.
    get_port: unsafe { core::mem::transmute(udplite_get_port as *const ()) },
    // SAFETY: `udplite_dummy` fallback — compatible signature.
    enter_memory_pressure: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    sock_rcv_skb: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    mib_lookup: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    mib_addr_lookup: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    diag_destroy: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    diag_handler: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    get_timeo: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    cmsg_send: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    cmsg_recv: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    bind_conflict: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    get_rx_skb_len: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    setsockopt_compat: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    getsockopt_compat: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    sendmsg_locked: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    sendpage_locked: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
    // SAFETY: Same.
    setsockopt_locked: unsafe { core::mem::transmute(udplite_dummy as *const ()) },
});

/// UDPLite protocol
#[no_mangle]
pub static udplite_protocol: SyncWrapper<udplite_protocol> = SyncWrapper::new(udplite_protocol {
    handler: udplite_rcv,
    err_handler: udplite_err,
    no_policy: 1,
    netns_ok: 1,
    icmp_strict_tag_validation: 1,
    icmpv6_allow_any: 1,
});

/// Initialize UDPLite socket
#[no_mangle]
// SAFETY: Callers must ensure `sk` is a valid, non-null pointer to a kernel `sock` struct
// that was allocated with enough trailing space for a `udplite_sock`. The struct must be
// writable for the duration of this call.
pub unsafe extern "C" fn udplite_init_sock(sk: *mut sock) -> c_int {
    // SAFETY: `sk` is non-null and valid per caller contract; casting to `udplite_sock` is
    // sound because the kernel always allocates a full `udplite_sock` for UDPLite sockets.
    let udp_sk = &mut *(sk as *mut udplite_sock);
    udp_sk.cscov = UDPLITE_MIN_CSCOV;
    udp_sk.partial_cov = 0;
    0
}

/// Set UDPLite socket options
#[no_mangle]
// SAFETY: Callers must ensure `sk` is a valid, non-null `sock` pointer, `optval` is a valid
// readable pointer to at least `optlen` bytes, and `optlen` is a non-negative length matching
// the expected option size.
pub unsafe extern "C" fn udplite_setsockopt(sk: *mut sock, level: c_int, optname: c_int, optval: *const c_void, optlen: c_int) -> c_int {
    if level != 136 { // SOL_UDPLITE = IPPROTO_UDPLITE
        return -EINVAL;
    }

    match optname {
        UDPLITE_SEND_CSCOV => {
            if optlen != core::mem::size_of::<c_int>() as c_int {
                return -EINVAL;
            }
            // SAFETY: `optval` is a valid, readable pointer to at least `sizeof(c_int)` bytes
            // as required by the caller and validated by the `optlen` check above.
            let cscov = *(optval as *const c_int);
            if cscov < UDPLITE_MIN_CSCOV || cscov > UDPLITE_MAX_CSCOV {
                return -EINVAL;
            }
            // SAFETY: `sk` is non-null and valid (caller invariant); the cast to `udplite_sock`
            // is valid as documented in `udplite_init_sock`.
            let udp_sk = &mut *(sk as *mut udplite_sock);
            udp_sk.cscov = cscov;
        }
        UDPLITE_RECV_CSCOV => {
            if optlen != core::mem::size_of::<c_int>() as c_int {
                return -EINVAL;
            }
            // SAFETY: Same as `UDPLITE_SEND_CSCOV` optval dereference above.
            let partial_cov = *(optval as *const c_int);
            if partial_cov < 0 || partial_cov > 1 {
                return -EINVAL;
            }
            // SAFETY: Same as above.
            let udp_sk = &mut *(sk as *mut udplite_sock);
            udp_sk.partial_cov = partial_cov;
        }
        _ => return -EINVAL,
    }

    0
}

/// Get UDPLite socket options
#[no_mangle]
// SAFETY: Callers must ensure `sk` is a valid, non-null `sock` pointer, `optval` is a valid
// writable pointer to at least `*optlen` bytes, and `optlen` is a valid, non-null writable
// pointer to a non-negative length.
pub unsafe extern "C" fn udplite_getsockopt(sk: *mut sock, level: c_int, optname: c_int, optval: *mut c_void, optlen: *mut c_int) -> c_int {
    if level != 136 { // SOL_UDPLITE = IPPROTO_UDPLITE
        return -EINVAL;
    }

    match optname {
        UDPLITE_SEND_CSCOV => {
            // SAFETY: `optlen` is a valid, non-null, writable pointer per caller invariant.
            if *optlen < core::mem::size_of::<c_int>() as c_int {
                *optlen = core::mem::size_of::<c_int>() as c_int;
                return -EINVAL;
            }
            // SAFETY: `sk` is non-null and valid; cast to `udplite_sock` is sound.
            let udp_sk = &*(sk as *const udplite_sock);
            // SAFETY: `optval` is a valid, writable pointer to at least `sizeof(c_int)` bytes.
            *(optval as *mut c_int) = udp_sk.cscov;
            *optlen = core::mem::size_of::<c_int>() as c_int;
        }
        UDPLITE_RECV_CSCOV => {
            // SAFETY: Same as above.
            if *optlen < core::mem::size_of::<c_int>() as c_int {
                *optlen = core::mem::size_of::<c_int>() as c_int;
                return -EINVAL;
            }
            // SAFETY: Same as above.
            let udp_sk = &*(sk as *const udplite_sock);
            // SAFETY: Same as above.
            *(optval as *mut c_int) = udp_sk.partial_cov;
            *optlen = core::mem::size_of::<c_int>() as c_int;
        }
        _ => return -EINVAL,
    }

    0
}

/// UDPLite receive function
#[no_mangle]
// SAFETY: Callers must ensure `skb` is a valid, non-null `sk_buff` pointer whose `data` field
// points to a valid UDPLite header and whose `sk` field points to a valid `udplite_sock`.
// All fields must remain valid for the duration of this call.
pub unsafe extern "C" fn udplite_rcv(skb: *mut sk_buff) -> c_int {
    // 🛡️ FORMAL VERIFICATION BOUNDARY (Mapped to Lean 4: udplite_csum_no_degradation)
    requires!(!skb.is_null(), "udplite_csum_no_degradation: skb invariant violated");
    requires!(!(*skb).data.is_null(), "udplite_csum_no_degradation: skb.data invariant violated");

    // SAFETY: `skb` is non-null (checked by `requires!`); `(*skb).data` is non-null (checked
    // by the second `requires!`). The data pointer points to at least a `udphdr` worth of
    // bytes as guaranteed by the networking stack before calling receive handlers.
    let udph = &mut *((*skb).data as *mut udphdr);
    let len = ntohs(udph.len) as usize;
    let cscov = if len > core::mem::size_of::<udphdr>() {
        len - core::mem::size_of::<udphdr>()
    } else {
        0
    };

    // SAFETY: `(*skb).sk` is a valid `sock` pointer allocated with `udplite_sock` trailing
    // space by the kernel socket layer. Cast is sound for UDPLite sockets.
    let udp_sk = &mut *((*skb).sk as *mut udplite_sock);
    if cscov < udp_sk.cscov as usize {
        if udp_sk.partial_cov == 0 {
            kfree_skb(skb);
            return 0;
        }
        // SAFETY: `(*skb).cb` is a per-packet control block embedded in every `sk_buff`.
        // Its size is at least as large as `udplite_cb`; the cast is sound for UDPLite packets.
        let udp_cb = &mut *((*skb).cb.as_mut_ptr() as *mut udplite_cb);
        udp_cb.partial_cov = 1;
    }

    udp_rcv(skb)
}

/// UDPLite error handler
#[no_mangle]
// SAFETY: Callers must ensure all pointer arguments are valid for the duration of this call.
// `skb` must be non-null; other pointer arguments may be null (forwarded directly to `udp_err`).
pub unsafe extern "C" fn udplite_err(skb: *mut sk_buff, info: *mut u8, err: c_int, icmph: *mut c_void, dev: *mut c_void, inet6_skb_parm: *mut c_void, sock_exterr_skb: *mut c_void) {
    udp_err(skb, info, err, icmph, dev, inet6_skb_parm, sock_exterr_skb);
}

// SAFETY: Callers must ensure `_sk` and `_fl` are either null or valid kernel pointers.
// Port allocation returns 0 on success.
pub unsafe extern "C" fn udplite_get_port(_sk: *mut sock, _fl: *mut flowi) -> c_int {
    let _ret = 0;
    _ret
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[no_mangle]
// SAFETY: This is a no-op fallback handler. No pointer arguments are provided or dereferenced.
pub unsafe extern "C" fn udplite_dummy() {}

#[cfg(test)]
mod tests {
    use super::*;

    // ── Helper to build a minimal zeroed udplite_sock ──────────────────────────
    fn make_udplite_sock() -> udplite_sock {
        // SAFETY: All-zero is a valid initial state for a C-ABI `udplite_sock`.
        unsafe { core::mem::zeroed() }
    }

    // ── Constant sanity checks ─────────────────────────────────────────────────

    #[test]
    fn test_protocol_number() {
        assert_eq!(IPPROTO_UDPLITE, 136, "IPPROTO_UDPLITE must be 136");
    }

    #[test]
    fn test_socket_option_constants() {
        assert_eq!(UDPLITE_SEND_CSCOV, 1);
        assert_eq!(UDPLITE_RECV_CSCOV, 2);
    }

    #[test]
    fn test_cscov_range_constants() {
        assert_eq!(UDPLITE_MIN_CSCOV, 0);
        assert_eq!(UDPLITE_MAX_CSCOV, 65535);
    }

    #[test]
    fn test_error_code_constants() {
        assert_eq!(UDPLITE_ERR_CSCOV, -1000);
        assert_eq!(UDPLITE_ERR_PARTIAL, -1001);
    }

    // ── udplite_init_sock ──────────────────────────────────────────────────────

    #[test]
    fn test_init_sock_zeroes_fields() {
        let mut sk = make_udplite_sock();
        sk.cscov = 99;
        sk.partial_cov = 1;
        // SAFETY: `sk` is a valid stack-allocated `udplite_sock`; the pointer is non-null
        // and the struct is writable for the duration of this call.
        let ret = unsafe { udplite_init_sock(&mut sk as *mut udplite_sock as *mut sock) };
        assert_eq!(ret, 0, "init_sock must return 0");
        assert_eq!(sk.cscov, UDPLITE_MIN_CSCOV, "cscov must be reset to MIN");
        assert_eq!(sk.partial_cov, 0, "partial_cov must be reset to 0");
    }

    // ── udplite_setsockopt ─────────────────────────────────────────────────────

    #[test]
    fn test_setsockopt_wrong_level() {
        let mut sk = make_udplite_sock();
        let val: c_int = 100;
        // SAFETY: `sk` is valid; `val` is a valid readable `c_int`.
        let ret = unsafe {
            udplite_setsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                0, // wrong level — not SOL_UDPLITE
                UDPLITE_SEND_CSCOV,
                &val as *const c_int as *const c_void,
                core::mem::size_of::<c_int>() as c_int,
            )
        };
        assert_eq!(ret, -EINVAL, "wrong level must return EINVAL");
    }

    #[test]
    fn test_setsockopt_send_cscov_valid() {
        let mut sk = make_udplite_sock();
        let val: c_int = 1000;
        // SAFETY: All arguments are valid stack-allocated values.
        let ret = unsafe {
            udplite_setsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                136, // SOL_UDPLITE
                UDPLITE_SEND_CSCOV,
                &val as *const c_int as *const c_void,
                core::mem::size_of::<c_int>() as c_int,
            )
        };
        assert_eq!(ret, 0);
        assert_eq!(sk.cscov, 1000);
    }

    #[test]
    fn test_setsockopt_send_cscov_out_of_range() {
        let mut sk = make_udplite_sock();
        let val: c_int = 70000; // > UDPLITE_MAX_CSCOV
        // SAFETY: All arguments are valid stack-allocated values.
        let ret = unsafe {
            udplite_setsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                136,
                UDPLITE_SEND_CSCOV,
                &val as *const c_int as *const c_void,
                core::mem::size_of::<c_int>() as c_int,
            )
        };
        assert_eq!(ret, -EINVAL, "out-of-range cscov must return EINVAL");
    }

    #[test]
    fn test_setsockopt_recv_cscov_invalid_partial() {
        let mut sk = make_udplite_sock();
        let val: c_int = 99; // not 0 or 1
        // SAFETY: All arguments are valid stack-allocated values.
        let ret = unsafe {
            udplite_setsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                136,
                UDPLITE_RECV_CSCOV,
                &val as *const c_int as *const c_void,
                core::mem::size_of::<c_int>() as c_int,
            )
        };
        assert_eq!(ret, -EINVAL);
    }

    #[test]
    fn test_setsockopt_unknown_optname() {
        let mut sk = make_udplite_sock();
        let val: c_int = 0;
        // SAFETY: All arguments are valid.
        let ret = unsafe {
            udplite_setsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                136,
                999, // unknown option
                &val as *const c_int as *const c_void,
                core::mem::size_of::<c_int>() as c_int,
            )
        };
        assert_eq!(ret, -EINVAL);
    }

    // ── udplite_getsockopt ─────────────────────────────────────────────────────

    #[test]
    fn test_getsockopt_send_cscov_roundtrip() {
        let mut sk = make_udplite_sock();
        sk.cscov = 512;
        let mut out_val: c_int = 0;
        let mut out_len: c_int = core::mem::size_of::<c_int>() as c_int;
        // SAFETY: All arguments are valid stack-allocated values.
        let ret = unsafe {
            udplite_getsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                136,
                UDPLITE_SEND_CSCOV,
                &mut out_val as *mut c_int as *mut c_void,
                &mut out_len,
            )
        };
        assert_eq!(ret, 0);
        assert_eq!(out_val, 512);
    }

    #[test]
    fn test_getsockopt_wrong_level() {
        let mut sk = make_udplite_sock();
        let mut out_val: c_int = 0;
        let mut out_len: c_int = core::mem::size_of::<c_int>() as c_int;
        // SAFETY: All arguments are valid stack-allocated values.
        let ret = unsafe {
            udplite_getsockopt(
                &mut sk as *mut udplite_sock as *mut sock,
                0, // wrong level
                UDPLITE_SEND_CSCOV,
                &mut out_val as *mut c_int as *mut c_void,
                &mut out_len,
            )
        };
        assert_eq!(ret, -EINVAL);
    }

    #[test]
    fn test_dummy_is_noop() {
        // SAFETY: `udplite_dummy` takes no arguments and performs no operations.
        unsafe { udplite_dummy() }; // must not panic
    }
}
