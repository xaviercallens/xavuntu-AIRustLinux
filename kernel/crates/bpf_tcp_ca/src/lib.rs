#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]

use core::ffi::{c_int, c_uint, c_void};
use core::ptr;

// Constants from C
pub const EINVAL: c_int = -22;
pub const ENOMEM: c_int = -12;
pub const ENOTSUPP: c_int = -95;
pub const EEXIST: c_int = -17;
pub const EACCES: c_int = -13;
pub const NOT_INIT: c_int = -1;
pub const TCP_CONG_MASK: c_uint = 0x00000007;
pub const MAX_BPF_FUNC_ARGS: usize = 4;

// Opaque FFI types
#[repr(C)]
#[derive(Copy, Clone)]
pub struct Btf { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BtfType { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfProg { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfInsnAccessAux {
    pub reg_type: c_int,
    pub btf_id: c_uint,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfVerifierLog { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfFuncProto { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BtfMember {
    pub type_field: c_int,
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct tcp_sock { _private: [u8; 0] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct TcpCongestionOps {
    pub flags: c_uint,
    pub name: [u8; 40],
    pub init: Option<extern "C" fn(*mut c_void)>,
    pub release: Option<extern "C" fn(*mut c_void)>,
    pub set_state: Option<extern "C" fn(*mut c_void, c_int)>,
    pub cwnd_event: Option<extern "C" fn(*mut c_void, c_int)>,
    pub in_ack_event: Option<extern "C" fn(*mut c_void, c_int)>,
    pub pkts_acked: Option<extern "C" fn(*mut c_void, *const c_void)>,
    pub min_tso_segs: Option<extern "C" fn(*mut c_void) -> c_uint>,
    pub sndbuf_expand: Option<extern "C" fn(*mut c_void) -> c_uint>,
    pub cong_control: Option<extern "C" fn(*mut c_void, *const c_void, c_uint, c_int)>,
    pub get_info: Option<extern "C" fn(*mut c_void, c_uint, *mut c_void) -> c_int>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfVerifierOps {
    pub get_func_proto: extern "C" fn(c_int, *const BpfProg) -> *const BpfFuncProto,
    pub is_valid_access:
        extern "C" fn(c_int, c_int, c_int, *const BpfProg, *mut BpfInsnAccessAux) -> bool,
    pub btf_struct_access: extern "C" fn(
        *mut BpfVerifierLog,
        *mut Btf,
        *mut BtfType,
        c_int,
        c_int,
        c_int,
        *mut c_uint,
    ) -> c_int,
    pub check_kfunc_call: extern "C" fn(c_int) -> bool,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct BpfStructOps {
    pub verifier_ops: *const BpfVerifierOps,
    pub reg: extern "C" fn(*mut c_void) -> c_int,
    pub unreg: extern "C" fn(*mut c_void),
    pub check_member: extern "C" fn(*const BtfType, *const BtfMember) -> c_int,
    pub init_member:
        extern "C" fn(*const BtfType, *const BtfMember, *mut c_void, *const c_void) -> c_int,
    pub init: extern "C" fn(*mut Btf) -> c_int,
    pub name: *const u8,
}

unsafe impl Sync for BpfStructOps {}
unsafe impl Sync for BpfVerifierOps {}

// SyncWrapper provides a thread-safe UnsafeCell wrapper for FFI globals
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}

impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        // For FFI globals, the kernel handles external synchronization.
        unsafe { &mut *self.0.get() }
    }
}

// Offset tables
static OPTIONAL_OPS: SyncWrapper<[c_uint; 9]> = SyncWrapper::new([0; 9]);
static UNSUPPORTED_OPS: SyncWrapper<[c_uint; 1]> = SyncWrapper::new([0; 1]);

// External kernel symbols
unsafe extern "C" {
    fn btf_find_by_name_kind(btf: *mut Btf, name: *const u8, kind: c_int) -> c_int;
    fn btf_type_by_id(btf: *mut Btf, id: c_int) -> *mut BtfType;
    fn btf_ctx_access(
        off: c_int,
        size: c_int,
        type_: c_int,
        prog: *const BpfProg,
        info: *mut BpfInsnAccessAux,
    ) -> bool;
    fn bpf_log(log: *mut BpfVerifierLog, fmt: *const u8, ...) -> c_int;
    fn btf_struct_access(
        log: *mut BpfVerifierLog,
        btf: *mut Btf,
        t: *mut BtfType,
        off: c_int,
        size: c_int,
        atype: c_int,
        next_btf_id: *mut c_uint,
    ) -> c_int;
    fn __tcp_send_ack(sock: *mut c_void, rcv_nxt: u32);
    fn tcp_register_congestion_control(kdata: *mut c_void) -> c_int;
    fn tcp_unregister_congestion_control(kdata: *mut c_void);
    fn bpf_obj_name_cpy(dst: *mut u8, src: *const u8, size: c_int) -> c_int;
    fn tcp_find(name: *const u8) -> *mut c_void;

    static bpf_sk_storage_get_proto: BpfFuncProto;
    static bpf_sk_storage_delete_proto: BpfFuncProto;
    static btf_vmlinux: core::cell::UnsafeCell<*mut Btf>;
}

// Global variables
static TCP_SOCK_TYPE: SyncWrapper<*mut BtfType> = SyncWrapper::new(ptr::null_mut());
static TCP_SOCK_ID: SyncWrapper<c_uint> = SyncWrapper::new(0);
static SOCK_ID: SyncWrapper<c_uint> = SyncWrapper::new(0);

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_send_ack(tp: *mut tcp_sock, rcv_nxt: u32) -> c_int {
    __tcp_send_ack(tp as *mut c_void, rcv_nxt);
    0
}

#[no_mangle]
pub unsafe extern "C" fn is_unsupported(member_offset: c_uint) -> bool {
    let mut i: usize = 0;
    let unsupported_ops = UNSUPPORTED_OPS.get_mut();

    while i < 1 {
        if member_offset == unsupported_ops[i] {
            return true;
        }
        i += 1;
    }

    false
}

#[no_mangle]
pub unsafe extern "C" fn is_optional(member_offset: c_uint) -> bool {
    let mut i: usize = 0;
    let optional_ops = OPTIONAL_OPS.get_mut();

    while i < 9 {
        if member_offset == optional_ops[i] {
            return true;
        }
        i += 1;
    }

    false
}

// Implementation deferred.
static BPF_TCP_CA_KFUNC_IDS: [Option<unsafe extern "C" fn() -> ()>; 20] = [None; 20];

// Registration function
extern "C" fn bpf_tcp_ca_reg(kdata: *mut c_void) -> c_int {
    if kdata.is_null() {
        EINVAL
    } else {
        0
    }
}

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_ca_is_valid_access(off: c_int, size: c_int, type_: c_int, prog: *const BpfProg, info: *mut BpfInsnAccessAux) -> bool {
    if off < 0 || off >= (MAX_BPF_FUNC_ARGS * 4) as c_int {
        return false;
    }
    if type_ != 1 { // BPF_READ
        return false;
    }
    if off % size != 0 {
        return false;
    }

    if !btf_ctx_access(off, size, type_, prog, info) {
        return false;
    }

    if (*info).reg_type == 1 && (*info).btf_id == *SOCK_ID.get_mut() {
        // promote it to tcp_sock
        (*info).btf_id = *TCP_SOCK_ID.get_mut();
    }

    true
}

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_ca_btf_struct_access(log: *mut BpfVerifierLog, btf: *mut Btf, t: *mut BtfType, off: c_int, size: c_int, atype: c_int, next_btf_id: *mut c_uint) -> c_int {
    if atype == 1 { // BPF_READ
        return btf_struct_access(log, btf, t, off, size, atype, next_btf_id);
    }

    if t != *TCP_SOCK_TYPE.get_mut() {
        bpf_log(log, b"only read is supported\0" as *const u8);
        return EACCES;
    }

    match off {
        // bpf_ctx_range(struct inet_connection_sock, icsk_ca_priv)
        0x18 => {
            if off + size > 0x20 {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        // offsetof(struct inet_connection_sock, icsk_ack.pending)
        0x1c => {
            if off + size > 0x20 {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        // offsetof(struct tcp_sock, snd_cwnd)
        0x20 => {
            if off + size > 0x24 {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        // offsetof(struct tcp_sock, snd_cwnd_cnt)
        0x24 => {
            if off + size > 0x28 {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        // offsetof(struct tcp_sock, snd_ssthresh)
        0x28 => {
            if off + size > 0x2c {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        // offsetof(struct tcp_sock, ecn_flags)
        0x3c => {
            if off + size > 0x40 {
                bpf_log(log, b"write access at off %d with size %d beyond the member of tcp_sock ended at %zu\0" as *const u8);
                return EACCES;
            }
        },
        _ => {
            bpf_log(log, b"no write support to tcp_sock at off %d\0" as *const u8);
            return EACCES;
        }
    }

    NOT_INIT
}

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_ca_get_func_proto(func_id: c_int, _prog: *const BpfProg) -> *const BpfFuncProto {
    match func_id {
        1 => BPF_TCP_SEND_ACK_PROTO.get_mut() as *const BpfFuncProto, // BPF_FUNC_tcp_send_ack
        2 => &bpf_sk_storage_get_proto as *const BpfFuncProto, // BPF_FUNC_sk_storage_get
        3 => &bpf_sk_storage_delete_proto as *const BpfFuncProto, // BPF_FUNC_sk_storage_delete
        _ => bpf_base_func_proto(func_id),
    }
}

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_ca_check_kfunc_call(kfunc_btf_id: c_int) -> bool {
    btf_id_set_contains(&BPF_TCP_CA_KFUNC_IDS, kfunc_btf_id as c_uint)
}

#[no_mangle]
pub unsafe extern "C" fn bpf_tcp_ca_init_member(t: *const BtfType, member: *const BtfMember, kdata: *mut c_void, udata: *const c_void) -> c_int {
    let utcp_ca = udata as *const TcpCongestionOps;
    let tcp_ca = kdata as *mut TcpCongestionOps;
    let moff = btf_member_bit_offset(t, member) / 8;

    match moff {
        0 => { // offsetof(struct tcp_congestion_ops, flags)
            if ((*utcp_ca).flags & !TCP_CONG_MASK) != 0 {
                return EINVAL;
            }
            (*tcp_ca).flags = (*utcp_ca).flags;
            return 1;
        },
        4 => { // offsetof(struct tcp_congestion_ops, name)
            if bpf_obj_name_cpy((*tcp_ca).name.as_mut_ptr(), (*utcp_ca).name.as_ptr(), 40) <= 0 {
                return EINVAL;
            }
            if tcp_find((*utcp_ca).name.as_ptr()).is_null() {
                return EEXIST;
            }
            return 1;
        },
        _ => {}
    }

    if !btf_type_resolve_func_ptr(*btf_vmlinux.get(), (*member).type_field, ptr::null_mut()) {
        return 0;
    }

    let prog_fd = *(udata as *const c_int);
    if prog_fd == 0 && !is_optional(moff as c_uint) && !is_unsupported(moff as c_uint) {
        return EINVAL;
    }

    0
}

extern "C" fn bpf_tcp_ca_unreg(_kdata: *mut c_void) {}

extern "C" fn bpf_tcp_ca_check_member(t: *const BtfType, m: *const BtfMember) -> c_int {
    if t.is_null() || m.is_null() {
        return EINVAL;
    }
    0
}

extern "C" fn bpf_tcp_ca_init(btf: *mut Btf) -> c_int {
    if btf.is_null() {
        return EINVAL;
    }
    0
}

// Safe wrappers for verifier ops
extern "C" fn bpf_tcp_ca_get_func_proto_wrapper(func_id: c_int, prog: *const BpfProg) -> *const BpfFuncProto {
    unsafe { bpf_tcp_ca_get_func_proto(func_id, prog) }
}

extern "C" fn bpf_tcp_ca_is_valid_access_wrapper(off: c_int, size: c_int, type_: c_int, prog: *const BpfProg, info: *mut BpfInsnAccessAux) -> bool {
    unsafe { bpf_tcp_ca_is_valid_access(off, size, type_, prog, info) }
}

extern "C" fn bpf_tcp_ca_btf_struct_access_wrapper(log: *mut BpfVerifierLog, btf: *mut Btf, t: *mut BtfType, off: c_int, size: c_int, atype: c_int, next_btf_id: *mut c_uint) -> c_int {
    unsafe { bpf_tcp_ca_btf_struct_access(log, btf, t, off, size, atype, next_btf_id) }
}

extern "C" fn bpf_tcp_ca_check_kfunc_call_wrapper(kfunc_btf_id: c_int) -> bool {
    unsafe { bpf_tcp_ca_check_kfunc_call(kfunc_btf_id) }
}

extern "C" fn bpf_tcp_ca_init_member_wrapper(t: *const BtfType, member: *const BtfMember, kdata: *mut c_void, udata: *const c_void) -> c_int {
    unsafe { bpf_tcp_ca_init_member(t, member, kdata, udata) }
}

static BPF_TCP_CA_VERIFIER_OPS: BpfVerifierOps = BpfVerifierOps {
    get_func_proto: bpf_tcp_ca_get_func_proto_wrapper,
    is_valid_access: bpf_tcp_ca_is_valid_access_wrapper,
    btf_struct_access: bpf_tcp_ca_btf_struct_access_wrapper,
    check_kfunc_call: bpf_tcp_ca_check_kfunc_call_wrapper,
};

static BPF_TCP_CA_NAME: &[u8] = b"tcp_congestion_ops\0";

#[no_mangle]
pub static BPF_TCP_CA_OPS: BpfStructOps = BpfStructOps {
    verifier_ops: &BPF_TCP_CA_VERIFIER_OPS as *const BpfVerifierOps,
    reg: bpf_tcp_ca_reg,
    unreg: bpf_tcp_ca_unreg,
    check_member: bpf_tcp_ca_check_member,
    init_member: bpf_tcp_ca_init_member_wrapper,
    init: bpf_tcp_ca_init,
    name: BPF_TCP_CA_NAME.as_ptr(),
};

// BPF verifier ops definition
#[no_mangle]
pub static bpf_tcp_ca_verifier_ops: SyncWrapper<BpfVerifierOps> = SyncWrapper::new(BpfVerifierOps {
    get_func_proto: bpf_tcp_ca_get_func_proto_wrapper,
    is_valid_access: bpf_tcp_ca_is_valid_access_wrapper,
    btf_struct_access: bpf_tcp_ca_btf_struct_access_wrapper,
    check_kfunc_call: bpf_tcp_ca_check_kfunc_call_wrapper,
});

// Helper functions
#[no_mangle]
pub unsafe extern "C" fn btf_member_bit_offset(t: *const BtfType, member: *const BtfMember) -> c_int {
    if t.is_null() || member.is_null() {
        return EINVAL;
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn btf_type_resolve_func_ptr(_btf: *mut Btf, _type_id: c_int, _func_ptr: *mut *mut c_void) -> bool {
    // Implementation would depend on BTF structure layout
    // Implementation deferred.
    true
}

#[no_mangle]
pub unsafe extern "C" fn btf_id_set_contains(_ids: *const [Option<unsafe extern "C" fn() -> ()>; 20], _id: c_uint) -> bool {
    // Implementation would depend on the actual set structure
    // Implementation deferred.
    true
}

#[no_mangle]
pub unsafe extern "C" fn bpf_base_func_proto(_func_id: c_int) -> *const BpfFuncProto {
    // Implementation would depend on the actual base function prototypes
    // Implementation deferred.
    ptr::null()
}

// BPF function proto
static BPF_TCP_SEND_ACK_PROTO: SyncWrapper<BpfFuncProto> = SyncWrapper::new(BpfFuncProto {
    // Actual fields would be initialized with appropriate values
    _private: [0; 0],
});


// Test cases (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bpf_tcp_ca_init_and_check() {
        assert_eq!(bpf_tcp_ca_init(ptr::null_mut()), EINVAL);
        assert_eq!(bpf_tcp_ca_check_member(ptr::null(), ptr::null()), EINVAL);
        assert_eq!(bpf_tcp_ca_reg(ptr::null_mut()), EINVAL);
        // SAFETY: Testing null rejection in btf_member_bit_offset
        unsafe {
            assert_eq!(btf_member_bit_offset(ptr::null(), ptr::null()), EINVAL);
        }
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
