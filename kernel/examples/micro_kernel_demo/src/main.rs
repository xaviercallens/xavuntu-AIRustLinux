#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(target_os = "none", no_std)]
#![cfg_attr(target_os = "none", no_main)]
#[cfg(not(target_os = "none"))]
extern crate std;

#[cfg(not(target_os = "none"))]
use std::println;

use kernel_types::*;

/// Helper to safely initialize an IPv6 address from a 16-byte array
#[inline]
pub fn mk_in6_addr(bytes: [u8; 16]) -> in6_addr {
    in6_addr {
        in6_u: in6_addr_union { u6_addr8: bytes },
    }
}

#[cfg(not(target_os = "none"))]
fn main() {
    // Minimal kernel demo entry point
    let _test_addr = mk_in6_addr([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
    println!("Micro kernel initialized with IPv6 address");
}

#[cfg(target_os = "none")]
#[no_mangle]
pub extern "C" fn _start() -> ! {
    loop {}
}

#[cfg(target_os = "none")]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(target_os = "none")]
struct DummyAllocator;

#[cfg(target_os = "none")]
unsafe impl core::alloc::GlobalAlloc for DummyAllocator {
    unsafe fn alloc(&self, _layout: core::alloc::Layout) -> *mut u8 { core::ptr::null_mut() }
    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: core::alloc::Layout) {}
}

#[cfg(target_os = "none")]
#[global_allocator]
static ALLOCATOR: DummyAllocator = DummyAllocator;
