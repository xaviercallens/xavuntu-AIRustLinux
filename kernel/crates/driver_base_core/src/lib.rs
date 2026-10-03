#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
//! Device model core
//!
//! This module implements driver_base_core functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel drivers/base

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn driver_base_core_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn driver_base_core_exit() {
}

#[no_mangle]
pub static DRIVER_BASE_CORE_INITIALIZED: bool = false;

/// A safe wrapper around raw device pointers.
#[repr(transparent)]
pub struct SafeDevice(*mut core::ffi::c_void);

impl SafeDevice {
    /// Creates a new `SafeDevice` from a raw pointer.
    ///
    /// # Safety
    /// The caller must ensure that the pointer is valid and properly aligned.
    #[must_use]
    pub unsafe fn new(ptr: *mut core::ffi::c_void) -> Self {
        Self(ptr)
    }

    /// Returns the underlying raw pointer.
    #[must_use]
    pub fn as_ptr(&self) -> *mut core::ffi::c_void {
        self.0
    }
}

/// A safe wrapper around raw kobject pointers.
#[repr(transparent)]
pub struct SafeKObject(*mut core::ffi::c_void);

impl SafeKObject {
    /// Creates a new `SafeKObject` from a raw pointer.
    ///
    /// # Safety
    /// The caller must ensure that the pointer is valid and properly aligned.
    #[must_use]
    pub unsafe fn new(ptr: *mut core::ffi::c_void) -> Self {
        Self(ptr)
    }

    /// Returns the underlying raw pointer.
    #[must_use]
    pub fn as_ptr(&self) -> *mut core::ffi::c_void {
        self.0
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_driver_base_core_init_stub() {
        unsafe { assert_eq!(driver_base_core_init(), -19); }
    }
}
