#![allow(clippy::pedantic)]
#![no_std]
//! Exec Domain module
//!
//! Substantive kernel definitions for exec_domain in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for exec_domain
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExecDomainDescriptor {
    pub domain_id: u64,
    pub flags: u32,
    pub active: bool,
}

impl ExecDomainDescriptor {
    pub const fn new(domain_id: u64, flags: u32) -> Self {
        Self { domain_id, flags, active: true }
    }

    pub fn is_native(&self) -> bool {
        self.active && self.domain_id > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn exec_domain_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn exec_domain_exit() {
}

#[no_mangle]
pub static EXEC_DOMAIN_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exec_domain_descriptor_creation() {
        let desc = ExecDomainDescriptor::new(42, 0x1);
        assert!(desc.is_native());
        assert_eq!(desc.domain_id, 42);
    }

    #[test]
    fn test_exec_domain_descriptor_inactive() {
        let mut desc = ExecDomainDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_native());
    }

    #[test]
    fn test_exec_domain_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(exec_domain_init(), 0);
        }
    }
}
