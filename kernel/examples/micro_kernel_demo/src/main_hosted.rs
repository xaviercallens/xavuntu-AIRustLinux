#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(target_os = "none", no_std)]
#![cfg_attr(target_os = "none", no_main)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]
use kernel_types::*;

#[cfg(not(target_os = "none"))]
pub fn from_ipv6(addr: std::net::Ipv6Addr) -> in6_addr {
    let bytes = addr.octets();
    in6_addr {
        in6_u: in6_addr_union { u6_addr8: bytes },
    }
}

#[cfg(not(target_os = "none"))]
fn main() {
    println!("Micro kernel demo - hosted version");

    // Example usage
    let localhost = std::net::Ipv6Addr::new(0, 0, 0, 0, 0, 0, 0, 1);
    let _addr = from_ipv6(localhost);

    println!("IPv6 localhost initialized successfully");
}

#[cfg(target_os = "none")]
fn main() {}

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
