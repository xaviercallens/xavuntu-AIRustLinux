#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Clock sources
//!
//! This module implements time_clocksource functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel time

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn time_clocksource_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn time_clocksource_exit() {
}

#[no_mangle]
pub static TIME_CLOCKSOURCE_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_time_clocksource_init_stub() {
        unsafe { assert_eq!(time_clocksource_init(), -38); }
    }
}
