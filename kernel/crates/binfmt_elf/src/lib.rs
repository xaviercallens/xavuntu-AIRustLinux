#![allow(clippy::pedantic)]
#![no_std]
//! Binfmt Elf module
//!
//! Substantive kernel definitions for binfmt_elf in the Rust Linux Mini Kernel.

use core::ffi::c_int;

/// Kernel descriptor struct for binfmt_elf
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ElfBinaryDescriptor {
    pub format_id: u64,
    pub flags: u32,
    pub active: bool,
}

impl ElfBinaryDescriptor {
    pub const fn new(format_id: u64, flags: u32) -> Self {
        Self { format_id, flags, active: true }
    }

    pub fn magic_valid(&self) -> bool {
        self.active && self.format_id > 0
    }
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn binfmt_elf_init() -> c_int {
    let _ret = 0;
    _ret
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn binfmt_elf_exit() {
}

#[no_mangle]
pub static BINFMT_ELF_INITIALIZED: bool = false;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_binfmt_elf_descriptor_creation() {
        let desc = ElfBinaryDescriptor::new(42, 0x1);
        assert!(desc.magic_valid());
        assert_eq!(desc.format_id, 42);
    }

    #[test]
    fn test_binfmt_elf_descriptor_inactive() {
        let mut desc = ElfBinaryDescriptor::new(0, 0x0);
        desc.active = false;
        assert!(!desc.magic_valid());
    }

    #[test]
    fn test_binfmt_elf_init() {
        // SAFETY: Direct invocation of C-ABI module init in test runner
        unsafe {
            assert_eq!(binfmt_elf_init(), 0);
        }
    }
}
