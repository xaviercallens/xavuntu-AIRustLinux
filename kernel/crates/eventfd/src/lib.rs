#![allow(clippy::pedantic)]
#![no_std]
//! Eventfd module
//!
//! Substantive kernel definitions for eventfd in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for eventfd
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EventfdDescriptor {
    pub event_count: u64,
    pub flags: u32,
    pub active: bool,
}

impl EventfdDescriptor {
    pub const fn new(event_count: u64, flags: u32) -> Self {
        Self { event_count, flags, active: true }
    }

    pub fn has_capacity(&self) -> bool {
        self.active && self.event_count > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn eventfd_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn eventfd_exit() {
}

#[no_mangle]
pub static EVENTFD_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_eventfd_descriptor_creation() {
        let desc = EventfdDescriptor::new(42, 0x1);
        assert!(desc.has_capacity());
        assert_eq!(desc.event_count, 42);
    }

    #[test]
    fn test_eventfd_descriptor_inactive() {
        let mut desc = EventfdDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.has_capacity());
    }

    #[test]
    fn test_eventfd_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(eventfd_init(), 0);
        }
    }
}
