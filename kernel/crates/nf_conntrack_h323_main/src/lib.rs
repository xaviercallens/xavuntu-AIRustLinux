#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
use kernel_types::*;
use core::{mem, ptr};

type ExpectFn = Option<extern "C" fn(*mut c_void, *mut c_void, *mut c_void) -> c_int>;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct h323_call_id { pub call_id: [c_char; 128], pub call_id_len: c_int }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct h323_call_signal {
    pub call_id: h323_call_id,
    pub setup: u8,
    pub connect: u8,
    pub release_complete: u8,
    pub call_type: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct h323_call {
    pub call_signal: h323_call_signal,
    pub src_addr: nf_inet_addr,
    pub dst_addr: nf_inet_addr,
    pub src_port: __be16,
    pub dst_port: __be16,
    pub protocol: c_int,
    pub af: c_int,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct h323_expect {
    pub call: h323_call,
    pub timeout: c_uint,
    pub flags: c_uint,
    pub master: *mut c_void,
    pub expectfn: ExpectFn,
    pub expect_data: *mut c_void,
}

#[no_mangle]
pub extern "C" fn h323_expect_create(
    call: *mut h323_call,
    timeout: c_uint,
    flags: c_uint,
    master: *mut c_void,
    expectfn: ExpectFn,
    expect_data: *mut c_void,
) -> *mut h323_expect {
    if call.is_null() {
        return ptr::null_mut();
    }

    let size = mem::size_of::<h323_expect>();
    let expect_ptr = unsafe { kmalloc(size, GFP_KERNEL) as *mut h323_expect };

    if expect_ptr.is_null() {
        return ptr::null_mut();
    }

    unsafe {
        ptr::write(expect_ptr, h323_expect {
            call: *call,
            timeout,
            flags,
            master,
            expectfn,
            expect_data,
        });
    }

    expect_ptr
}

#[no_mangle]
pub extern "C" fn h323_expect_destroy(expect: *mut h323_expect) {
    if !expect.is_null() {
        unsafe {
            ptr::drop_in_place(expect);
            kfree(expect as *mut c_void);
        }
    }
}

#[no_mangle]
pub extern "C" fn h323_expect_match(expect: *mut h323_expect, call: *mut h323_call) -> bool {
    if expect.is_null() || call.is_null() {
        return false;
    }

    unsafe {
        let expect_call = &(*expect).call;
        let match_call = &*call;

        if expect_call.call_signal.call_id.call_id_len != match_call.call_signal.call_id.call_id_len {
            return false;
        }

        let len = expect_call.call_signal.call_id.call_id_len;
        if len < 0 || len as usize > expect_call.call_signal.call_id.call_id.len() {
            return false;
        }

        for i in 0..(len as usize) {
            if expect_call.call_signal.call_id.call_id[i] != match_call.call_signal.call_id.call_id[i] {
                return false;
            }
        }

        if expect_call.src_addr.all != match_call.src_addr.all {
            return false;
        }

        if expect_call.dst_addr.all != match_call.dst_addr.all {
            return false;
        }

        if expect_call.src_port != match_call.src_port {
            return false;
        }

        if expect_call.dst_port != match_call.dst_port {
            return false;
        }

        if expect_call.protocol != match_call.protocol {
            return false;
        }

        if expect_call.af != match_call.af {
            return false;
        }

        true
    }
}

#[no_mangle]
pub extern "C" fn h323_expect_attach(expect: *mut h323_expect, skb: *mut sk_buff) -> c_int {
    if expect.is_null() || skb.is_null() {
        return -1;
    }

    unsafe {
        match (*expect).expectfn {
            Some(expectfn) => expectfn((*expect).master, skb as *mut c_void, (*expect).expect_data),
            None => 0,
        }
    }
}

#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
