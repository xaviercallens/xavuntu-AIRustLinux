#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]

use core::ffi::c_int;

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    loop {}
}

#[cfg(not(test))]
#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {}

pub const IPPROTO_ROUTING: c_int = 43;
pub const IPPROTO_DSTOPTS: c_int = 44;
pub const INET6_PROTO_GSO_EXTHDR: c_int = 0x0001;

#[repr(C)]
pub struct NetOffload { pub flags: c_int }

static RTHDR_OFFLOAD: NetOffload = NetOffload {
    flags: INET6_PROTO_GSO_EXTHDR,
};

static DSTOPT_OFFLOAD: NetOffload = NetOffload {
    flags: INET6_PROTO_GSO_EXTHDR,
};

unsafe extern "C" {
    fn inet6_add_offload(offload: *const NetOffload, proto: c_int) -> c_int;
    fn inet6_del_offload(offload: *const NetOffload, proto: c_int);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ipv6_exthdrs_offload_init() -> c_int {
    let mut ret = unsafe { inet6_add_offload(&RTHDR_OFFLOAD, IPPROTO_ROUTING) };
    if ret != 0 {
        return ret;
    }

    ret = unsafe { inet6_add_offload(&DSTOPT_OFFLOAD, IPPROTO_DSTOPTS) };
    if ret != 0 {
        // SAFETY: RTHDR_OFFLOAD is still valid and IPPROTO_ROUTING is a valid protocol
        inet6_del_offload(&RTHDR_OFFLOAD, IPPROTO_ROUTING);
        return ret;
    }

    0
}

#[cfg(test)]
mod tests {
    // No tests for this simple module
}
