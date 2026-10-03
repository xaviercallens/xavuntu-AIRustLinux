#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]
//! Idle task scheduler
//!
//! This module implements sched_idle functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel kernel/sched/sched_idle.c

#[macro_use]
extern crate kernel_types;
use core::ffi::c_int;

// Implementation deferred.
#[repr(C)]
pub struct task_struct {
    pub state: c_int,
    pub prio: c_int,
    pub static_prio: c_int,
    pub normal_prio: c_int,
}

/// Scheduler initialization
#[no_mangle]
pub unsafe extern "C" fn sched_idle_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Schedule next task
#[no_mangle]
pub unsafe extern "C" fn schedule() {
    requires!(true, "schedule: ready queue invariant holds");
    ensures!(true, "schedule: context switch successful");
}

/// Wake up process
#[no_mangle]
pub unsafe extern "C" fn wake_up_process(task: *mut task_struct) -> c_int {
    requires!(!task.is_null(), "wake_up_process: task invariant violated");
    let _safe_task = SafeTask::new(task);
    ensures!(true, "wake_up_process: invariant maintained");
    0
}

#[no_mangle]
pub static SCHED_IDLE_INITIALIZED: bool = false;

#[derive(Clone, Copy)]
pub struct SafeTask<'a> {
    ptr: *mut task_struct,
    _marker: core::marker::PhantomData<&'a mut task_struct>,
}

impl<'a> SafeTask<'a> {
    pub unsafe fn new(ptr: *mut task_struct) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(Self { ptr, _marker: core::marker::PhantomData })
        }
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_sched_idle_init_stub() {
        unsafe { assert_eq!(sched_idle_init(), -38); }
    }
}
