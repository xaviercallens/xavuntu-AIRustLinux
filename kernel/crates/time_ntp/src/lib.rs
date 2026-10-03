#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! NTP support
//!
//! This module implements time_ntp functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel time

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn time_ntp_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn time_ntp_exit() {
}

#[no_mangle]
pub static TIME_NTP_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_time_ntp_init_stub() {
        unsafe { assert_eq!(time_ntp_init(), -38); }
    }
}
