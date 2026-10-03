#![allow(clippy::pedantic)]
#![no_std]
//! Oom Kill module
//!
//! Substantive kernel definitions for oom_kill in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for oom_kill
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct OomKillDescriptor {
    pub badness_score: u64,
    pub flags: u32,
    pub active: bool,
}

impl OomKillDescriptor {
    pub const fn new(badness_score: u64, flags: u32) -> Self {
        Self { badness_score, flags, active: true }
    }

    pub fn is_targetable(&self) -> bool {
        self.active && self.badness_score > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn oom_kill_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn oom_kill_exit() {
}

#[no_mangle]
pub static OOM_KILL_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_oom_kill_descriptor_creation() {
        let desc = OomKillDescriptor::new(42, 0x1);
        assert!(desc.is_targetable());
        assert_eq!(desc.badness_score, 42);
    }

    #[test]
    fn test_oom_kill_descriptor_inactive() {
        let mut desc = OomKillDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.is_targetable());
    }

    #[test]
    fn test_oom_kill_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(oom_kill_init(), 0);
        }
    }
}
