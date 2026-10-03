#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
//! Platform setup (x86_64) - Rust Linux Mini Kernel

use core::sync::atomic::{AtomicBool, Ordering};
#[allow(non_camel_case_types)]
type c_int = i32;

/// Initialize architecture-specific setup (x86_64).
///
/// Disables interrupts to ensure a safe boot environment.
///
/// # Safety
///
/// - Uses inline assembly to disable interrupts
/// - Must be called early in boot process
/// - Assumes x86_64 architecture
#[no_mangle]
pub unsafe extern "C" fn arch_setup_init() -> c_int {
    #[cfg(all(any(target_arch = "x86", target_arch = "x86_64"), not(miri), not(test)))]
    core::arch::asm!("cli", options(nomem, nostack));
    0
}

/// Cleanup function for arch_setup subsystem.
///
/// # Safety
///
/// - Currently a no-op, safe to call at any time
#[no_mangle]
pub unsafe extern "C" fn arch_setup_exit() {}

#[no_mangle]
pub static ARCH_SETUP_INITIALIZED: AtomicBool = AtomicBool::new(false);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arch_setup_init() {
        unsafe {
            let result = arch_setup_init();
            assert_eq!(result, 0, "arch_setup_init should return 0");
        }
        // Note: The 'cli' instruction in the real implementation disables interrupts,
        // but in test mode (with std), this is just a no-op inline asm
    }

    #[test]
    fn test_arch_setup_exit_is_safe() {
        unsafe {
            arch_setup_exit(); // Should not panic
        }
    }

    #[test]
    fn test_arch_setup_initialized_flag() {
        let initial = ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed);
        ARCH_SETUP_INITIALIZED.store(true, Ordering::Relaxed);
        assert!(ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed));
        ARCH_SETUP_INITIALIZED.store(false, Ordering::Relaxed);
        assert!(!ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed));
        ARCH_SETUP_INITIALIZED.store(initial, Ordering::Relaxed); // Restore
    }

    #[test]
    fn test_arch_setup_multiple_calls() {
        unsafe {
            // Should be safe to call multiple times
            let result1 = arch_setup_init();
            let result2 = arch_setup_init();
            assert_eq!(result1, 0);
            assert_eq!(result2, 0);
        }
    }

    #[test]
    fn test_arch_setup_stress_100_calls() {
        unsafe {
            for _ in 0..100 {
                let result = arch_setup_init();
                assert_eq!(result, 0);
            }
        }
    }

    #[test]
    fn test_arch_setup_exit_multiple() {
        unsafe {
            for _ in 0..10 {
                arch_setup_exit();
            }
        }
    }

    #[test]
    fn test_arch_setup_init_exit_sequence() {
        unsafe {
            arch_setup_init();
            arch_setup_exit();
            arch_setup_init();
            arch_setup_exit();
        }
    }

    #[test]
    fn test_arch_setup_flag_state_changes() {
        let initial = ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed);

        ARCH_SETUP_INITIALIZED.store(true, Ordering::Relaxed);
        assert!(ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed));

        ARCH_SETUP_INITIALIZED.store(false, Ordering::Relaxed);
        assert!(!ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed));

        ARCH_SETUP_INITIALIZED.store(true, Ordering::Relaxed);
        assert!(ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed));

        ARCH_SETUP_INITIALIZED.store(initial, Ordering::Relaxed);
    }

    #[test]
    fn test_arch_setup_init_return_consistency() {
        unsafe {
            for _ in 0..50 {
                assert_eq!(arch_setup_init(), 0, "Should always return 0");
            }
        }
    }

    #[test]
    fn test_arch_setup_flag_default() {
        // Flag should start as false in most contexts
        let val = ARCH_SETUP_INITIALIZED.load(Ordering::Relaxed);
        ARCH_SETUP_INITIALIZED.store(val, Ordering::Relaxed); // Just verify we can access it
    }

    #[test]
    fn test_arch_setup_init_before_exit() {
        unsafe {
            let result = arch_setup_init();
            assert_eq!(result, 0);
            arch_setup_exit();
        }
    }

    #[test]
    fn test_arch_setup_exit_before_init() {
        unsafe {
            arch_setup_exit();
            let result = arch_setup_init();
            assert_eq!(result, 0);
        }
    }

    #[test]
    fn test_arch_setup_interleaved_calls() {
        unsafe {
            arch_setup_init();
            arch_setup_init();
            arch_setup_exit();
            arch_setup_init();
            arch_setup_exit();
            arch_setup_exit();
        }
    }
}
