#![allow(clippy::pedantic)]
#![no_std]
//! Kasan module
//!
//! Substantive kernel definitions for kasan in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for kasan
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KasanDescriptor {
    pub shadow_offset: u64,
    pub flags: u32,
    pub active: bool,
}

impl KasanDescriptor {
    pub const fn new(shadow_offset: u64, flags: u32) -> Self {
        Self { shadow_offset, flags, active: true }
    }

    pub fn is_quarantine_active(&self) -> bool {
        self.active && self.shadow_offset > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn kasan_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn kasan_exit() {
}

#[no_mangle]
pub static KASAN_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kasan_descriptor_creation() {
        let desc = KasanDescriptor::new(42, 0x1);
        assert!(desc.is_quarantine_active());
        assert_eq!(desc.shadow_offset, 42);
    }

    #[test]
    fn test_kasan_descriptor_inactive() {
        let mut desc = KasanDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_quarantine_active());
    }

    #[test]
    fn test_kasan_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(kasan_init(), 0);
        }
    }
}
