#![allow(clippy::all, clippy::pedantic)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]
//! Memory subsystem integration for Phase 2
//!
//! This module integrates page and slab allocators into the boot sequence

use core::ffi::c_int;

extern "C" {
    fn page_alloc_init() -> c_int;
    fn slab_init() -> c_int;
    fn printk_str(s: *const u8, len: usize);
}

/// Initialize memory subsystem
///
/// # Safety
/// Must be called during kernel boot, after printk_init
pub unsafe fn memory_init() -> c_int {
    print(b"Initializing memory subsystem...\n");

    // Initialize page allocator
    print(b"  - Page allocator... ");
    let result = page_alloc_init();
    if result != 0 {
        print(b"FAILED\n");
        return result;
    }
    print(b"OK\n");

    // Initialize SLAB allocator
    print(b"  - SLAB allocator... ");
    let result = slab_init();
    if result != 0 {
        print(b"FAILED\n");
        return result;
    }
    print(b"OK\n");

    print(b"Memory subsystem initialized\n");
    0
}

#[inline]
unsafe fn print(msg: &[u8]) {
    printk_str(msg.as_ptr(), msg.len());
}
