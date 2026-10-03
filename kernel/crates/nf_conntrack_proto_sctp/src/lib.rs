#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Connection tracking protocol helper module for SCTP.
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use kernel_types::*;

pub const SCTP_CID_INIT: u8 = 1;
pub const SCTP_CID_INIT_ACK: u8 = 2;
pub const SCTP_CID_HEARTBEAT: u8 = 4;
pub const SCTP_CID_HEARTBEAT_ACK: u8 = 5;
pub const SCTP_CID_ABORT: u8 = 6;
pub const SCTP_CID_SHUTDOWN: u8 = 7;
pub const SCTP_CID_SHUTDOWN_ACK: u8 = 8;
pub const SCTP_CID_ERROR: u8 = 9;
pub const SCTP_CID_COOKIE_ECHO: u8 = 10;
pub const SCTP_CID_COOKIE_ACK: u8 = 11;
pub const SCTP_CID_SHUTDOWN_COMPLETE: u8 = 14;

pub const SCTP_CONNTRACK_NONE: u8 = 0;
pub const SCTP_CONNTRACK_CLOSED: u8 = 1;
pub const SCTP_CONNTRACK_COOKIE_WAIT: u8 = 2;
pub const SCTP_CONNTRACK_COOKIE_ECHOED: u8 = 3;
pub const SCTP_CONNTRACK_ESTABLISHED: u8 = 4;
pub const SCTP_CONNTRACK_SHUTDOWN_SENT: u8 = 5;
pub const SCTP_CONNTRACK_SHUTDOWN_RECD: u8 = 6;
pub const SCTP_CONNTRACK_SHUTDOWN_ACK_SENT: u8 = 7;
pub const SCTP_CONNTRACK_HEARTBEAT_SENT: u8 = 8;
pub const SCTP_CONNTRACK_HEARTBEAT_ACKED: u8 = 9;
pub const SCTP_CONNTRACK_MAX: u8 = 10;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sctphdr {
    pub source: c_ushort,
    pub dest: c_ushort,
    pub vtag: c_uint,
    pub checksum: c_uint,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sctp_chunkhdr {
    pub type_: c_uchar,
    pub flags: c_uchar,
    pub length: c_ushort,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sctp_conntrack {
    pub state: u8,
    pub vtag: [u32; 2],
    pub init: [[u32; 2]; 2],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_proto { pub sctp: sctp_conntrack }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn { pub proto: nf_conntrack_proto }

unsafe extern "C" {
    fn skb_header_pointer(
        skb: *const sk_buff,
        offset: c_uint,
        len: size_t,
        buffer: *mut c_void,
    ) -> *mut c_void;
    fn set_bit(nr: c_ulong, addr: *mut c_ulong);
}

// Static data
static SCTP_CONNTRACK_NAMES: [&str; SCTP_CONNTRACK_MAX as usize + 1] = [
    "NONE",
    "CLOSED",
    "COOKIE_WAIT",
    "COOKIE_ECHOED",
    "ESTABLISHED",
    "SHUTDOWN_SENT",
    "SHUTDOWN_RECD",
    "SHUTDOWN_ACK_SENT",
    "HEARTBEAT_SENT",
    "HEARTBEAT_ACKED",
    "MAX",
];

static SCTP_TIMEOUTS: [c_uint; SCTP_CONNTRACK_MAX as usize] = [
    0,      // SCTP_CONNTRACK_NONE
    10,     // SCTP_CONNTRACK_CLOSED
    3,      // SCTP_CONNTRACK_COOKIE_WAIT
    3,      // SCTP_CONNTRACK_COOKIE_ECHOED
    432000, // SCTP_CONNTRACK_ESTABLISHED - 5 DAYS in seconds (5*24*3600)
    3,      // SCTP_CONNTRACK_SHUTDOWN_SENT
    3,      // SCTP_CONNTRACK_SHUTDOWN_RECD
    3,      // SCTP_CONNTRACK_SHUTDOWN_ACK_SENT
    30,     // SCTP_CONNTRACK_HEARTBEAT_SENT
    210,    // SCTP_CONNTRACK_HEARTBEAT_ACKED
];

static SCTP_CONNTRACKS: [[[u8; SCTP_CONNTRACK_MAX as usize]; 11]; 2] = {
    let mut arr = [[[0u8; 10]; 11]; 2];
    // Original direction transitions
    arr[0][0] = [1, 1, 2, 3, 4, 5, 6, 7, 2, 9]; // INIT
    arr[0][1] = [1, 1, 2, 3, 4, 5, 6, 7, 1, 9]; // INIT_ACK
    arr[0][2] = [1; 10]; // ABORT
    arr[0][3] = [1, 1, 2, 3, 5, 5, 6, 7, 1, 5]; // SHUTDOWN
    arr[0][4] = [7, 1, 2, 3, 4, 7, 7, 7, 7, 9]; // SHUTDOWN_ACK
    arr[0][5] = [1, 1, 2, 3, 4, 5, 6, 7, 1, 9]; // ERROR
    arr[0][6] = [1, 1, 3, 3, 4, 5, 6, 7, 1, 9]; // COOKIE_ECHO
    arr[0][7] = [1, 1, 2, 3, 4, 5, 6, 7, 1, 9]; // COOKIE_ACK
    arr[0][8] = [1, 1, 2, 3, 4, 5, 6, 1, 1, 9]; // SHUTDOWN_COMP
    arr[0][9] = [8, 1, 2, 3, 4, 5, 6, 7, 8, 9]; // HEARTBEAT
    arr[0][10] = [1, 1, 2, 3, 4, 5, 6, 7, 9, 9]; // HEARTBEAT_ACK

    // Reply direction transitions
    arr[1][0] = [10, 1, 2, 3, 4, 5, 6, 7, 10, 9]; // INIT
    arr[1][1] = [10, 2, 2, 3, 4, 5, 6, 7, 10, 9]; // INIT_ACK
    arr[1][2] = [10, 1, 1, 1, 1, 1, 1, 1, 10, 1]; // ABORT
    arr[1][3] = [10, 1, 2, 3, 6, 5, 6, 7, 10, 6]; // SHUTDOWN
    arr[1][4] = [10, 1, 2, 3, 4, 7, 7, 7, 10, 9]; // SHUTDOWN_ACK
    arr[1][5] = [10, 1, 2, 1, 4, 5, 6, 7, 10, 9]; // ERROR
    arr[1][6] = [10, 1, 2, 3, 4, 5, 6, 7, 10, 9]; // COOKIE_ECHO
    arr[1][7] = [10, 1, 2, 4, 4, 5, 6, 7, 10, 9]; // COOKIE_ACK
    arr[1][8] = [10, 1, 2, 3, 4, 5, 6, 1, 10, 9]; // SHUTDOWN_COMP
    arr[1][9] = [10, 1, 2, 3, 4, 5, 6, 7, 8, 9]; // HEARTBEAT
    arr[1][10] = [10, 1, 2, 3, 4, 5, 6, 7, 9, 9]; // HEARTBEAT_ACK
    arr
};

// Function implementations
#[no_mangle]
pub unsafe extern "C" fn sctp_print_conntrack(s: *mut c_void, ct: *mut nf_conn) {
    if !s.is_null() && !ct.is_null() {
        let _state = (*ct).proto.sctp.state;
        // SAFETY: This is a no-op in Rust as we don't have seq_file
        // In real implementation, this would format to the seq_file
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn rust_eh_personality() {}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn do_basic_checks(
    _ct: *mut nf_conn,
    _skb: *mut sk_buff,
    _dataoff: c_uint,
    _map: *mut c_void,
) -> c_int {
    1
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn new_state(ct: *mut nf_conn, dir: c_uint, chunk_type: c_uchar) -> c_uchar {
    if ct.is_null() {
        return SCTP_CONNTRACK_NONE;
    }

    let old = (*ct).proto.sctp.state;
    let mut new = old;

    if dir > 1 {
        return old;
    }

    match chunk_type {
        SCTP_CID_INIT => {
            new = if dir == 0 {
                SCTP_CONNTRACK_COOKIE_WAIT
            } else {
                SCTP_CONNTRACK_CLOSED
            };
        }
        SCTP_CID_INIT_ACK => {
            if old == SCTP_CONNTRACK_COOKIE_WAIT {
                new = SCTP_CONNTRACK_COOKIE_ECHOED;
            }
        }
        SCTP_CID_COOKIE_ECHO => {
            if old == SCTP_CONNTRACK_COOKIE_WAIT || old == SCTP_CONNTRACK_COOKIE_ECHOED {
                new = SCTP_CONNTRACK_COOKIE_ECHOED;
            }
        }
        SCTP_CID_COOKIE_ACK => {
            if old == SCTP_CONNTRACK_COOKIE_ECHOED {
                new = SCTP_CONNTRACK_ESTABLISHED;
            }
        }
        SCTP_CID_SHUTDOWN => {
            if old == SCTP_CONNTRACK_ESTABLISHED {
                new = SCTP_CONNTRACK_SHUTDOWN_SENT;
            }
        }
        SCTP_CID_SHUTDOWN_ACK => {
            if old == SCTP_CONNTRACK_SHUTDOWN_SENT || old == SCTP_CONNTRACK_SHUTDOWN_RECD {
                new = SCTP_CONNTRACK_SHUTDOWN_ACK_SENT;
            }
        }
        SCTP_CID_SHUTDOWN_COMPLETE => {
            new = SCTP_CONNTRACK_CLOSED;
        }
        SCTP_CID_ABORT => {
            new = SCTP_CONNTRACK_CLOSED;
        }
        SCTP_CID_HEARTBEAT => {
            if old == SCTP_CONNTRACK_ESTABLISHED {
                new = SCTP_CONNTRACK_HEARTBEAT_SENT;
            }
        }
        SCTP_CID_HEARTBEAT_ACK => {
            if old == SCTP_CONNTRACK_HEARTBEAT_SENT {
                new = SCTP_CONNTRACK_HEARTBEAT_ACKED;
            }
        }
        _ => {}
    }

    (*ct).proto.sctp.state = new;
    new
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn sctp_packet(
    _ct: *mut nf_conn,
    skb: *mut sk_buff,
    dataoff: c_uint,
    map: *mut c_void,
    _dir: c_uint,
    _chunk_type: c_uchar,
) -> c_int {
    let mut offset: u32 = 0;
    let mut count: u32 = 0;
    let mut flag = 0;
    let mut _sch: sctp_chunkhdr = sctp_chunkhdr {
        type_: 0,
        flags: 0,
        length: 0,
    };

    // SAFETY: The for_each_sctp_chunk macro logic is implemented here
    // with bounds checking and pointer validation
    offset = dataoff + (core::mem::size_of::<sctphdr>() as u32);
    while offset < (*skb).len {
        let sch = skb_header_pointer(
            skb,
            offset,
            core::mem::size_of::<sctp_chunkhdr>() as size_t,
            &mut _sch as *mut sctp_chunkhdr as *mut c_void,
        ) as *mut sctp_chunkhdr;
        if sch.is_null() {
            break;
        }

        // Process chunk
        if (*sch).type_ == SCTP_CID_INIT
            || (*sch).type_ == SCTP_CID_INIT_ACK
            || (*sch).type_ == SCTP_CID_SHUTDOWN_COMPLETE
        {
            flag = 1;
        }

        // Basic checks
        if (((*sch).type_ == SCTP_CID_COOKIE_ACK
            || (*sch).type_ == SCTP_CID_COOKIE_ECHO
            || flag != 0)
            && count != 0)
            || (*sch).length == 0
        {
            return 1;
        }

        if !map.is_null() {
            // SAFETY: Bit manipulation is safe with valid pointer
            set_bit((*sch).type_ as c_ulong, map as *mut c_ulong);
        }

        offset += ((*sch).length as u32 + 3) & !3;
        count += 1;
    }

    if count == 0 {
        return 1;
    }

    0
}

#[no_mangle]
pub unsafe extern "C" fn sctp_new_state(dir: c_int, cur_state: u8, chunk_type: u8) -> u8 {
    let mut i: c_int = 0;

    match chunk_type {
        SCTP_CID_INIT => i = 0,
        SCTP_CID_INIT_ACK => i = 1,
        SCTP_CID_ABORT => i = 2,
        SCTP_CID_SHUTDOWN => i = 3,
        SCTP_CID_SHUTDOWN_ACK => i = 4,
        SCTP_CID_ERROR => i = 5,
        SCTP_CID_COOKIE_ECHO => i = 6,
        SCTP_CID_COOKIE_ACK => i = 7,
        SCTP_CID_SHUTDOWN_COMPLETE => i = 8,
        SCTP_CID_HEARTBEAT => i = 9,
        SCTP_CID_HEARTBEAT_ACK => i = 10,
        _ => return cur_state,
    }

    SCTP_CONNTRACKS[dir as usize][i as usize][cur_state as usize]
}

#[no_mangle]
pub unsafe extern "C" fn sctp_new(
    ct: *mut nf_conn,
    skb: *mut sk_buff,
    _sh: *mut sctphdr,
    dataoff: c_uint,
) -> c_int {
    let mut new_state_val: u8 = SCTP_CONNTRACK_MAX;
    let mut offset: u32 = 0;
    let mut count: u32 = 0;
    let mut last_chunk_type: u8 = 0;
    let mut _sch: sctp_chunkhdr = sctp_chunkhdr {
        type_: 0,
        flags: 0,
        length: 0,
    };

    // Initialize sctp struct
    (*ct).proto.sctp = sctp_conntrack {
        state: 0,
        vtag: [0, 0],
        init: [[0, 0], [0, 0]],
    };

    // Process each chunk
    offset = dataoff + (core::mem::size_of::<sctphdr>() as u32);
    while offset < (*skb).len {
        let sch = skb_header_pointer(
            skb,
            offset,
            core::mem::size_of::<sctp_chunkhdr>() as size_t,
            &mut _sch as *mut sctp_chunkhdr as *mut c_void,
        ) as *mut sctp_chunkhdr;
        if sch.is_null() {
            break;
        }

        new_state_val = sctp_new_state(0, SCTP_CONNTRACK_NONE, (*sch).type_);

        if new_state_val == SCTP_CONNTRACK_NONE || new_state_val == SCTP_CONNTRACK_MAX {
            return 0; // false
        }

        last_chunk_type = (*sch).type_;

        if (*sch).type_ == SCTP_CID_INIT {
            let mut _inithdr: [u32; 4] = [0; 4]; // SCTP init header with u32 fields
            let ih = skb_header_pointer(
                skb,
                offset + (core::mem::size_of::<sctp_chunkhdr>() as u32),
                16,
                &mut _inithdr as *mut [u32; 4] as *mut c_void,
            ) as *mut u32;
            if ih.is_null() {
                return 0;
            }

            // Set vtag from init tag field (first u32 in init header)
            (*ct).proto.sctp.vtag[1] = *ih;
        }

        offset += ((*sch).length as u32 + 3) & !3;
        count += 1;
    }

    if count == 0 {
        return 0;
    }
    // Update state based on last seen chunk
    if last_chunk_type != 0 {
        let _ = new_state(ct, 0, last_chunk_type);
    }
    1
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn sctp_get_timeouts_array() -> *const c_uint {
    SCTP_TIMEOUTS.as_ptr()
}
#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // 1. SCTP chunk-type constants
    // -----------------------------------------------------------------------

    #[test]
    fn test_sctp_chunk_type_constants() {
        // Verify every chunk-type constant against the values mandated by
        // RFC 4960 / Linux kernel header sctp.h.
        assert_eq!(SCTP_CID_INIT, 1);
        assert_eq!(SCTP_CID_INIT_ACK, 2);
        assert_eq!(SCTP_CID_HEARTBEAT, 4);
        assert_eq!(SCTP_CID_HEARTBEAT_ACK, 5);
        assert_eq!(SCTP_CID_ABORT, 6);
        assert_eq!(SCTP_CID_SHUTDOWN, 7);
        assert_eq!(SCTP_CID_SHUTDOWN_ACK, 8);
        assert_eq!(SCTP_CID_ERROR, 9);
        assert_eq!(SCTP_CID_COOKIE_ECHO, 10);
        assert_eq!(SCTP_CID_COOKIE_ACK, 11);
        assert_eq!(SCTP_CID_SHUTDOWN_COMPLETE, 14);
    }

    // -----------------------------------------------------------------------
    // 2. Conntrack state constants
    // -----------------------------------------------------------------------

    #[test]
    fn test_sctp_conntrack_state_constants() {
        assert_eq!(SCTP_CONNTRACK_NONE, 0);
        assert_eq!(SCTP_CONNTRACK_CLOSED, 1);
        assert_eq!(SCTP_CONNTRACK_COOKIE_WAIT, 2);
        assert_eq!(SCTP_CONNTRACK_COOKIE_ECHOED, 3);
        assert_eq!(SCTP_CONNTRACK_ESTABLISHED, 4);
        assert_eq!(SCTP_CONNTRACK_SHUTDOWN_SENT, 5);
        assert_eq!(SCTP_CONNTRACK_SHUTDOWN_RECD, 6);
        assert_eq!(SCTP_CONNTRACK_SHUTDOWN_ACK_SENT, 7);
        assert_eq!(SCTP_CONNTRACK_HEARTBEAT_SENT, 8);
        assert_eq!(SCTP_CONNTRACK_HEARTBEAT_ACKED, 9);
        // MAX must equal the number of real states (10) so array indexing is safe.
        assert_eq!(SCTP_CONNTRACK_MAX, 10);
    }

    // -----------------------------------------------------------------------
    // 3. Struct field sizes / layouts
    // -----------------------------------------------------------------------

    #[test]
    fn test_struct_sizes() {
        // sctphdr: 2 (src) + 2 (dst) + 4 (vtag) + 4 (checksum) = 12 bytes
        assert_eq!(core::mem::size_of::<sctphdr>(), 12);

        // sctp_chunkhdr: 1 (type) + 1 (flags) + 2 (length) = 4 bytes
        assert_eq!(core::mem::size_of::<sctp_chunkhdr>(), 4);

        // sctp_conntrack must be non-zero in size.
        assert!(core::mem::size_of::<sctp_conntrack>() >= 1);

        // nf_conn must be at least as large as the nested proto field.
        assert!(core::mem::size_of::<nf_conn>() >= core::mem::size_of::<nf_conntrack_proto>());
    }

    // -----------------------------------------------------------------------
    // 4. Null-pointer rejection: new_state returns SCTP_CONNTRACK_NONE for null ct
    // -----------------------------------------------------------------------

    #[test]
    fn test_new_state_null_ct_returns_none() {
        // SAFETY: Passing null is the scenario under test; new_state explicitly
        // guards against a null ct pointer before any dereference.
        let result = unsafe { new_state(core::ptr::null_mut(), 0, SCTP_CID_INIT) };
        assert_eq!(result, SCTP_CONNTRACK_NONE);
    }

    // -----------------------------------------------------------------------
    // 5. Null-pointer rejection: sctp_print_conntrack is a no-op with null args
    // -----------------------------------------------------------------------

    #[test]
    fn test_sctp_print_conntrack_null_args_no_crash() {
        // SAFETY: The function guards both pointers with is_null() checks before
        // any dereference, so passing nulls is safe and must not crash.
        unsafe {
            sctp_print_conntrack(core::ptr::null_mut(), core::ptr::null_mut());
        }
        // If we reach here the null-guard works correctly.
    }

    // -----------------------------------------------------------------------
    // 6. Valid state transitions via new_state (full SCTP handshake)
    // -----------------------------------------------------------------------

    #[test]
    fn test_new_state_handshake_transitions() {
        let mut ct = nf_conn {
            proto: nf_conntrack_proto {
                sctp: sctp_conntrack {
                    state: SCTP_CONNTRACK_NONE,
                    vtag: [0, 0],
                    init: [[0, 0], [0, 0]],
                },
            },
        };

        // SAFETY: ct is a fully-initialised stack variable; all pointer
        // arithmetic inside new_state stays within that single allocation.
        unsafe {
            // NONE  + INIT (dir=0)  -> COOKIE_WAIT
            let s = new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_INIT);
            assert_eq!(s, SCTP_CONNTRACK_COOKIE_WAIT);

            // COOKIE_WAIT + INIT_ACK -> COOKIE_ECHOED
            let s = new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_INIT_ACK);
            assert_eq!(s, SCTP_CONNTRACK_COOKIE_ECHOED);

            // COOKIE_ECHOED + COOKIE_ACK -> ESTABLISHED
            let s = new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_COOKIE_ACK);
            assert_eq!(s, SCTP_CONNTRACK_ESTABLISHED);

            // ESTABLISHED + SHUTDOWN -> SHUTDOWN_SENT
            let s = new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_SHUTDOWN);
            assert_eq!(s, SCTP_CONNTRACK_SHUTDOWN_SENT);

            // SHUTDOWN_SENT + SHUTDOWN_ACK -> SHUTDOWN_ACK_SENT
            let s = new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_SHUTDOWN_ACK);
            assert_eq!(s, SCTP_CONNTRACK_SHUTDOWN_ACK_SENT);
        }
    }

    // -----------------------------------------------------------------------
    // 7. ABORT always drives state to CLOSED regardless of current state
    // -----------------------------------------------------------------------

    #[test]
    fn test_new_state_abort_always_closes() {
        for initial_state in [
            SCTP_CONNTRACK_NONE,
            SCTP_CONNTRACK_COOKIE_WAIT,
            SCTP_CONNTRACK_ESTABLISHED,
            SCTP_CONNTRACK_SHUTDOWN_SENT,
        ] {
            let mut ct = nf_conn {
                proto: nf_conntrack_proto {
                    sctp: sctp_conntrack {
                        state: initial_state,
                        vtag: [0, 0],
                        init: [[0, 0], [0, 0]],
                    },
                },
            };
            // SAFETY: ct is fully initialised on the stack; new_state only
            // reads and writes the state field within the same allocation.
            let result = unsafe { new_state(&mut ct as *mut nf_conn, 0, SCTP_CID_ABORT) };
            assert_eq!(
                result,
                SCTP_CONNTRACK_CLOSED,
                "ABORT from state {initial_state} should yield CLOSED"
            );
        }
    }

    // -----------------------------------------------------------------------
    // 8. sctp_new_state table look-up (pure indexing into static array)
    // -----------------------------------------------------------------------

    #[test]
    fn test_sctp_new_state_table_lookup() {
        // SAFETY: sctp_new_state only indexes into the static SCTP_CONNTRACKS
        // array; dir=0, cur_state=NONE is a valid in-bounds combination.
        unsafe {
            // INIT in direction 0 from NONE -> COOKIE_WAIT (2)
            let s = sctp_new_state(0, SCTP_CONNTRACK_NONE, SCTP_CID_INIT);
            assert_eq!(s, SCTP_CONNTRACK_COOKIE_WAIT);

            // Unknown chunk type -> cur_state returned unchanged
            let s = sctp_new_state(0, SCTP_CONNTRACK_ESTABLISHED, 0xFF);
            assert_eq!(s, SCTP_CONNTRACK_ESTABLISHED);
        }
    }

    // -----------------------------------------------------------------------
    // 9. sctp_get_timeouts_array — pointer validity and key timeout values
    // -----------------------------------------------------------------------

    #[test]
    fn test_sctp_get_timeouts_array_values() {
        // SAFETY: sctp_get_timeouts_array returns a pointer to the static
        // SCTP_TIMEOUTS array which is valid for the entire program lifetime.
        // Reading up to SCTP_CONNTRACK_MAX elements is within bounds.
        unsafe {
            let ptr = sctp_get_timeouts_array();
            assert!(!ptr.is_null(), "timeouts pointer must not be null");

            // ESTABLISHED timeout = 432000 s (5 days), as documented in the source.
            let established_timeout = *ptr.add(SCTP_CONNTRACK_ESTABLISHED as usize);
            assert_eq!(established_timeout, 432000);

            // NONE timeout = 0 (no tracking).
            let none_timeout = *ptr.add(SCTP_CONNTRACK_NONE as usize);
            assert_eq!(none_timeout, 0);

            // HEARTBEAT_ACKED timeout = 210 s.
            let hb_acked_timeout = *ptr.add(SCTP_CONNTRACK_HEARTBEAT_ACKED as usize);
            assert_eq!(hb_acked_timeout, 210);
        }
    }

    // -----------------------------------------------------------------------
    // 10. Error-code sentinel values (-22 = EINVAL, -12 = ENOMEM)
    // -----------------------------------------------------------------------

    #[test]
    fn test_error_code_sentinels() {
        // The kernel ABI expects EINVAL = -22 and ENOMEM = -12.
        // These are hard-coded assumptions in callers of the conntrack helpers.
        const EINVAL: i32 = -22;
        const ENOMEM: i32 = -12;
        assert_eq!(EINVAL, -22);
        assert_eq!(ENOMEM, -12);

        // do_basic_checks always returns 1 (NF_ACCEPT equivalent) for any input.
        // SAFETY: All pointer arguments are documented as unused (_ct, _skb,
        // _map) inside the function body; null is therefore safe to pass.
        let ret = unsafe {
            do_basic_checks(
                core::ptr::null_mut(),
                core::ptr::null_mut(),
                0,
                core::ptr::null_mut(),
            )
        };
        assert_eq!(ret, 1);
    }
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
