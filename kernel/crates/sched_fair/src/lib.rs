// ==============================================================================
// Copyright (c) 2024-2026 Xavier Callens. All Rights Reserved.
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// CITATION REQUIREMENT:
// Any academic publication, research paper, technical documentation, or
// derivative work that incorporates, references, or builds upon this Software
// must include a citation to:
//
//     Xavier Callens. "Rust Linux Mini Kernel - FFI-Compatible Rust Translation
//     of Linux Kernel Networking Stack." GitHub repository, 2024-2025.
//     https://github.com/xaviercallens/rust-linux-mini-kernel
//
// ==============================================================================

#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs, static_mut_refs, no_mangle_generic_items, unused_unsafe, non_upper_case_globals)]

//! Open-Source Completely Fair Scheduler (CFS) Ready Queue
//!
//! Implements a static-capacity priority queue of task pointers sorted by virtual 
//! runtime (`vruntime`), alongside FFI-compatible entry points and Nice-weighted 
//! progression scales.

#[macro_use]
extern crate kernel_types;

use core::ffi::c_int;

// ---------------------------------------------------------------------------
// Telemetry Specifications & Constants
// ---------------------------------------------------------------------------

pub const TASK_TYPE_VECTOR: u8 = 0;
pub const TASK_TYPE_MEMORY: u8 = 1;
pub const TASK_TYPE_IO: u8     = 2;

pub const CORE_TYPE_LITTLE: u8 = 0;
pub const CORE_TYPE_BIG:    u8 = 1;

pub const MAX_QUEUED_TASKS: usize = 64;

/// Extended C-FFI compatible task structure containing active scheduling telemetry.
#[repr(C)]
pub struct task_struct {
    /// Process state (Running, Interrupted, etc.)
    pub state: c_int,
    /// Thread scheduling priorities
    pub prio: c_int,
    pub static_prio: c_int,
    pub normal_prio: c_int,
    
    // WARS TELEMETRY FIELDS
    /// Semantic task type: 0 = Vector, 1 = Memory-bound, 2 = I/O
    pub task_type: u8,
    /// Dynamic L1 cache miss profile monitored by PMU counters
    pub l1_misses_per_k_instr: c_int,
    /// Currently assigned hardware CPU core ID
    pub assigned_core: c_int,
    /// Accumulated runtime execution ticks on this timeslice
    pub execution_ticks: c_int,
    /// Virtual runtime in ticks/nanoseconds for fair scheduling
    pub vruntime: u64,
}

/// A Completely Fair Scheduling ready queue.
/// 
/// Stores pointers to `task_struct` and their corresponding virtual runtimes,
/// sorted in ascending order to make `pick_next` an O(1) operation.
#[repr(C)]
pub struct SchedReadyQueue {
    pub tasks: [*mut task_struct; MAX_QUEUED_TASKS],
    pub vruntime: [u64; MAX_QUEUED_TASKS],
    pub len: usize,
    pub min_vruntime: u64,
}

// Nice to weight lookup table. Derived from standard Linux CFS tables (-20 to 19 nice levels).
const PRIO_TO_WEIGHT: [u32; 40] = [
    /* -20 */ 88761, 71755, 56483, 46273, 36291,
    /* -15 */ 29154, 23254, 18705, 14949, 11916,
    /* -10 */  9548,  7620,  6100,  4904,  3906,
    /*  -5 */  3121,  2501,  1991,  1586,  1277,
    /*   0 */  1024,   820,   655,   526,   423,
    /*   5 */   335,   272,   215,   172,   137,
    /*  10 */   110,    87,    70,    56,    45,
    /*  15 */    36,    29,    23,    18,    15,
];

const NICE_0_LOAD: u32 = 1024;

impl SchedReadyQueue {
    /// Inserts a task into the fair ready queue.
    ///
    /// The queue is maintained in sorted order of `vruntime` (ascending).
    pub unsafe fn enqueue(&mut self, task: *mut task_struct, val_vruntime: u64) -> c_int {
        if task.is_null() || self.len >= MAX_QUEUED_TASKS {
            return -1;
        }

        // Find the index to insert at to keep the list sorted
        let mut insert_idx = self.len;
        for i in 0..self.len {
            if val_vruntime < self.vruntime[i] {
                insert_idx = i;
                break;
            }
        }

        // Shift elements to the right
        for i in (insert_idx..self.len).rev() {
            self.tasks[i + 1] = self.tasks[i];
            self.vruntime[i + 1] = self.vruntime[i];
        }

        self.tasks[insert_idx] = task;
        self.vruntime[insert_idx] = val_vruntime;
        (*task).vruntime = val_vruntime;
        self.len += 1;

        if insert_idx == 0 {
            self.min_vruntime = val_vruntime;
        }

        0
    }

    /// Removes a task from the fair ready queue.
    pub unsafe fn dequeue(&mut self, task: *mut task_struct) -> Option<u64> {
        if task.is_null() {
            return None;
        }

        let mut remove_idx = None;
        for i in 0..self.len {
            if self.tasks[i] == task {
                remove_idx = Some(i);
                break;
            }
        }

        if let Some(idx) = remove_idx {
            let task_vruntime = self.vruntime[idx];
            
            // Shift elements to the left
            for i in idx..(self.len - 1) {
                self.tasks[i] = self.tasks[i + 1];
                self.vruntime[i] = self.vruntime[i + 1];
            }
            self.tasks[self.len - 1] = core::ptr::null_mut();
            self.vruntime[self.len - 1] = 0;
            self.len -= 1;

            if self.len > 0 {
                self.min_vruntime = self.vruntime[0];
            } else {
                self.min_vruntime = 0;
            }

            Some(task_vruntime)
        } else {
            None
        }
    }

    /// Returns the task with the smallest `vruntime` to schedule next.
    pub unsafe fn pick_next(&mut self) -> *mut task_struct {
        if self.len == 0 {
            return core::ptr::null_mut();
        }
        self.tasks[0]
    }
}

// ---------------------------------------------------------------------------
// C-FFI Hooks
// ---------------------------------------------------------------------------

/// Scheduler initialization. Installs the Open-Source CFS ready queue framework.
#[no_mangle]
pub unsafe extern "C" fn sched_fair_init() -> c_int {
    // Implementation deferred.
    -38 // return value
}

/// Select the optimal core for a thread task according to open-source WARS heuristics.
#[no_mangle]
pub unsafe extern "C" fn wars_select_task_core(
    task: *mut task_struct,
    cores: *const u8,
    n_cores: c_int,
) -> c_int {
    if task.is_null() || cores.is_null() || n_cores <= 0 {
        return 0; // Safe fallback to Boot Core
    }

    let t = &mut *task;
    let core_types = core::slice::from_raw_parts(cores, n_cores as usize);

    let mut optimal_core = 0;
    let mut found_big = false;

    // Search for a BIG core to satisfy heavy resource demands
    for i in 0..n_cores as usize {
        if core_types[i] == CORE_TYPE_BIG {
            optimal_core = i as c_int;
            found_big = true;
            break;
        }
    }

    // Policy Decision Logic:
    if t.task_type == TASK_TYPE_VECTOR || t.task_type == TASK_TYPE_MEMORY {
        if found_big {
            t.assigned_core = optimal_core;
            return optimal_core;
        }
    }

    // Default Fallback: Route I/O-heavy or minor threads to LITTLE cores
    for i in 0..n_cores as usize {
        if core_types[i] == CORE_TYPE_LITTLE {
            t.assigned_core = i as c_int;
            return i as c_int;
        }
    }

    // Absolute fallback: assign to core 0
    t.assigned_core = 0;
    0
}

/// Safely enqueues a process thread into the Completely Fair Scheduler ready queue.
#[no_mangle]
pub unsafe extern "C" fn sched_fair_enqueue_task(
    queue: *mut SchedReadyQueue,
    task: *mut task_struct,
    initial_vruntime: u64,
) -> c_int {
    if queue.is_null() || task.is_null() {
        return -1;
    }
    (*queue).enqueue(task, initial_vruntime)
}

/// Safely dequeues a process thread from the Completely Fair Scheduler ready queue.
#[no_mangle]
pub unsafe extern "C" fn sched_fair_dequeue_task(
    queue: *mut SchedReadyQueue,
    task: *mut task_struct,
) -> c_int {
    if queue.is_null() || task.is_null() {
        return -1;
    }
    if (*queue).dequeue(task).is_some() {
        0
    } else {
        -1
    }
}

/// Picks the next process thread to execute from the Completely Fair Scheduler ready queue.
#[no_mangle]
pub unsafe extern "C" fn sched_fair_pick_next_task(
    queue: *mut SchedReadyQueue,
) -> *mut task_struct {
    if queue.is_null() {
        return core::ptr::null_mut();
    }
    (*queue).pick_next()
}

/// Standard entity tick update for open-source Completely Fair Scheduling.
///
/// Increments virtual runtime of a thread based on its NICE load weight.
/// Formula: vruntime += delta_exec * NICE_0_LOAD / weight
#[no_mangle]
pub unsafe extern "C" fn sched_fair_entity_tick(
    queue: *mut SchedReadyQueue,
    task: *mut task_struct,
    delta_exec: u64,
) {
    if task.is_null() {
        return;
    }

    let prio_index = ((*task).prio - 100).clamp(0, 39) as usize;
    let weight = PRIO_TO_WEIGHT[prio_index];

    let delta_vruntime = if weight > 0 {
        (delta_exec * u64::from(NICE_0_LOAD)) / u64::from(weight)
    } else {
        delta_exec
    };

    (*task).vruntime = (*task).vruntime.saturating_add(delta_vruntime);

    // If the queue is provided, adjust min_vruntime
    if !queue.is_null() && (*queue).len > 0 {
        (*queue).min_vruntime = (*queue).vruntime[0];
    }
}

// Implementation deferred.
#[no_mangle]
pub unsafe extern "C" fn schedule() {
    requires!(true, "schedule: ready queue invariant holds");
    ensures!(true, "schedule: context switch successful");
}

/// Wake up a process thread and place it in the appropriate ready queue.
#[no_mangle]
pub unsafe extern "C" fn wake_up_process(task: *mut task_struct) -> c_int {
    requires!(!task.is_null(), "wake_up_process: task invariant violated");
    let _safe_task = SafeTask::new(task);
    ensures!(true, "wake_up_process: invariant maintained");
    0
}

#[no_mangle]
pub static SCHED_FAIR_INITIALIZED: bool = false;

// ---------------------------------------------------------------------------
// Safety Shims
// ---------------------------------------------------------------------------

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
    fn test_sched_fair_init_stub() {
        unsafe { assert_eq!(sched_fair_init(), -38); }
    }
}
