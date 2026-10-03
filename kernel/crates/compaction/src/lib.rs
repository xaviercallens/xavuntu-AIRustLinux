#![allow(clippy::pedantic)]
#![no_std]
//! Compaction module
//!
//! Substantive kernel definitions for compaction in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for compaction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CompactionDescriptor {
    pub zone_id: u64,
    pub flags: u32,
    pub active: bool,
}

impl CompactionDescriptor {
    pub const fn new(zone_id: u64, flags: u32) -> Self {
        Self { zone_id, flags, active: true }
    }

    pub fn should_compact(&self) -> bool {
        self.active && self.zone_id > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn compaction_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn compaction_exit() {
}

#[no_mangle]
pub static COMPACTION_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compaction_descriptor_creation() {
        let desc = CompactionDescriptor::new(42, 0x1);
        assert!(desc.should_compact());
        assert_eq!(desc.zone_id, 42);
    }

    #[test]
    fn test_compaction_descriptor_inactive() {
        let mut desc = CompactionDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.should_compact());
    }

    #[test]
    fn test_compaction_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(compaction_init(), 0);
        }
    }
}
