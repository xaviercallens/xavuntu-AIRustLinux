#![allow(clippy::all, clippy::pedantic)]
#![no_std]
//! Alarm timers
//!
//! This module implements time_alarmtimer functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel time

use core::ffi::c_int;

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn time_alarmtimer_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn time_alarmtimer_exit() {
}

#[no_mangle]
pub static TIME_ALARMTIMER_INITIALIZED: bool = false;


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_time_alarmtimer_init_stub() {
        unsafe { assert_eq!(time_alarmtimer_init(), -38); }
    }
}
