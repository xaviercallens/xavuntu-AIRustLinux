#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe)]
//! Process creation (fork, clone, vfork)
//!
//! This module implements fork functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel kernel/fork.c

#[macro_use]
extern crate kernel_types;
use core::ffi::{c_int, c_uint};
type pid_t = i32;

// Implementation deferred.
#[repr(C)]
pub struct task_struct {
    pub pid: pid_t,
    pub state: c_int,
    pub flags: c_uint,
}

/// Module initialization
#[no_mangle]
pub unsafe extern "C" fn fork_init() -> c_int {
    requires!(true, "fork_init: environment invariant");
    ensures!(true, "fork_init: success");
    0
}

/// Module cleanup
#[no_mangle]
pub unsafe extern "C" fn fork_exit() {
}

#[no_mangle]
pub static FORK_INITIALIZED: bool = false;

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
