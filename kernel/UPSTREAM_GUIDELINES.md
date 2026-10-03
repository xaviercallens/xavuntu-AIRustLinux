# Rust for Linux Upstreaming Guidelines

This document provides a comprehensive framework and technical specification for upstreaming the **Minimum Viable Kernel (MVK)** modular crates to the official **Rust for Linux** project. It details the module mappings, architectural alignments, coding standards, and safety standards necessary for successful upstream integration.

---

## 1. Architectural Alignment and Core Principles

To collaborate with and contribute to the upstream **Rust for Linux** project, MVK components must strictly adhere to the kernel's core architectural paradigms:

### `#![no_std]` and Allocation Safety
*   **No Standard Library**: All upstreamed components must compile under `#![no_std]`.
*   **OOM Handling**: The standard Rust `alloc` library panics on Out-Of-Memory (OOM) conditions, which is unacceptable in the kernel. MVK crates must use the upstream kernel's `kernel::alloc` module (which provides fallible allocation APIs like `Box::try_new` and `Vec::try_push` returning `Result<T, AllocError>`).

### Safe Abstraction Boundaries
*   **Separation of Concerns**: Keep unsafe FFI bindings (in `rust/bindings/`) strictly separated from the safe, idiomatic Rust abstractions (in `rust/kernel/`).
*   **The `SAFETY` Comment Rule**: Every single `unsafe` block must be preceded by a `// SAFETY:` comment clearly explaining why the operation is safe, which invariants are maintained, and how undefined behavior is avoided.

### Object Lifetime and Pinning
*   **Pin-Initialization**: Kernel structures (such as lists, locks, and work items) often contain self-referential pointers and must be pinned in memory. MVK modules must utilize the kernel's `PinInit` and `pin_init!` frameworks to construct structures in-place.

---

## 2. Upstream Module Mapping Registry

The following registry maps **50+ permissive helper and protocol modules** from MVK to their corresponding targets and directories in the upstream Linux kernel tree.

| # | MVK Module Crate | Target Upstream Path | Description / Integration Role |
|---|------------------|----------------------|--------------------------------|
| **I** | **Core Kernel & Utility Layer** | | |
| 1 | `kernel_types` | `rust/kernel/types.rs` | Standard bare-metal definitions, FFI structures, and alignment bounds. |
| 2 | `printk` | `rust/kernel/print.rs` | Kernel console formatting, logs level wrappers (`pr_info!`, `pr_err!`). |
| 3 | `panic` | `rust/kernel/panic.rs` | Bare-metal panic handlers and diagnostic dump wrappers. |
| 4 | `string` | `rust/kernel/str.rs` | Custom safe string and byte-slice helpers compatible with C-strings. |
| 5 | `ctype` | `rust/kernel/ctype.rs` | Core character classification helpers for parsing command lines. |
| 6 | `vsprintf` | `rust/kernel/vsprintf.rs` | Core string formatting wrappers bridging to the kernel's formatting engine. |
| 7 | `cmdline` | `rust/kernel/cmdline.rs` | Safe kernel boot command line arguments parsing and extraction. |
| 8 | `crc32` | `lib/crc32.rs` | Upstream optimized cyclic redundancy check helpers. |
| 9 | `notifier` | `rust/kernel/notifier.rs` | Safe atomic/blocking notifier chains interface for kernel events. |
| 10 | `kfifo` | `rust/kernel/kfifo.rs` | Lock-free queue/FIFO data structure wrappers. |
| 11 | `kobject` | `rust/kernel/kobject.rs` | Unified device-model reference-counted objects abstraction. |
| 12 | `kref` | `rust/kernel/kref.rs` | Safe reference counting atomic primitives. |
| 13 | `klist` | `rust/kernel/klist.rs` | Thread-safe doubly linked list implementation for device trees. |
| 14 | `idr` | `rust/kernel/idr.rs` | Safe ID allocation and map subsystem. |
| 15 | `radix_tree` | `rust/kernel/radix.rs` | High-efficiency key-value dictionary and page cache trees. |
| 16 | `rbtree` | `rust/kernel/rbtree.rs` | Safe intrusive Red-Black Tree implementation for task schedulers. |
| 17 | `bitmap` | `rust/kernel/bitmap.rs` | Dynamic CPU/node and IRQ bitmask trackers. |
| **II**| **Memory Management (MM) Subsystem** | | |
| 18 | `page_alloc` | `rust/kernel/mm/page.rs` | Page frame allocator wrappers (Buddy System) for physical allocation. |
| 19 | `slab` | `rust/kernel/mm/slab.rs` | Interface to slab caches (`kmalloc` / `kfree` safe wrappers). |
| 20 | `slub` | `rust/kernel/mm/slub.rs` | Highly optimized SLUB allocator wrappers with lock-free path support. |
| 21 | `vmalloc` | `rust/kernel/mm/vmalloc.rs` | Non-contiguous virtual memory allocation wrappers. |
| 22 | `page_table` | `rust/kernel/mm/pgtable.rs` | Page table entry modification and safe CPU translation abstractions. |
| 23 | `mmap` | `rust/kernel/mm/mmap.rs` | Safe process address space layout mapping interfaces. |
| 24 | `mprotect` | `rust/kernel/mm/mprotect.rs` | Page protection flags management interface (read/write/execute). |
| 25 | `mremap` | `rust/kernel/mm/mremap.rs` | Virtual page remapping and address table moving wrappers. |
| 26 | `mlock` | `rust/kernel/mm/mlock.rs` | Memory locking interfaces to prevent page eviction. |
| 27 | `munmap` | `rust/kernel/mm/munmap.rs` | Virtual memory page unmapping and TLB flush trigger wrappers. |
| 28 | `mempool` | `rust/kernel/mm/mempool.rs` | Guaranteed allocation reserve memory pool wrappers for block IO. |
| 29 | `percpu` | `rust/kernel/mm/percpu.rs` | Thread-safe Per-CPU variable wrappers for high concurrency. |
| 30 | `swap` | `rust/kernel/mm/swap.rs` | Memory swapping framework controls and page replacement wrappers. |
| 31 | `kasan` | `rust/kernel/mm/kasan.rs` | Kernel Address Sanitizer validation checks for out-of-bounds safety. |
| 32 | `rmap` | `rust/kernel/mm/rmap.rs` | Reverse mapping trackers from physical pages to process virtual addresses. |
| 33 | `compaction` | `rust/kernel/mm/compact.rs` | Memory fragmentation cleanup and page migration interfaces. |
| **III**| **Process & Scheduling Subsystem** | | |
| 34 | `fork` | `rust/kernel/sched/fork.rs` | Process replication interfaces wrapping `copy_process`. |
| 35 | `sched_core` | `rust/kernel/sched/core.rs` | Process scheduler interface, runqueue, and context switch helpers. |
| 36 | `sched_fair` | `rust/kernel/sched/fair.rs` | Completely Fair Scheduler (CFS) parameters and priority queues. |
| 37 | `sched_wait` | `rust/kernel/sched/wait.rs` | Wait queue primitives (`wait_queue_head_t` wrappers). |
| 38 | `exit` | `rust/kernel/sched/exit.rs` | Process termination wrappers, cleaning registers, and reaping resources. |
| 39 | `signal` | `rust/kernel/sched/signal.rs` | Software interrupts and signals delivery mechanics. |
| 40 | `exec` | `rust/kernel/sched/exec.rs` | Binary loading and image execution hooks. |
| 41 | `kthread` | `rust/kernel/kthread.rs` | Safe kernel-space threads spawning and management. |
| 42 | `workqueue` | `rust/kernel/workqueue.rs` | Asynchronous deferred execution context interfaces. |
| 43 | `cgroup` | `rust/kernel/cgroup.rs` | Control Groups interfaces for resource restriction and sandboxing. |
| **IV**| **Virtual Filesystem (VFS) & Ext4** | | |
| 44 | `vfs_inode` | `rust/kernel/fs/inode.rs` | Safe VFS inode representations and file metadata trackers. |
| 45 | `vfs_dcache` | `rust/kernel/fs/dentry.rs` | Directory entry cache wrappers for high-speed file path lookups. |
| 46 | `vfs_file` | `rust/kernel/fs/file.rs` | Descriptor tables and active file operations abstractions. |
| 47 | `vfs_super` | `rust/kernel/fs/super.rs` | Superblock structures representing mounted filesystems. |
| 48 | `ext4_super` | `fs/ext4/rust/super.rs` | Safe Ext4 superblock parsing, mounting, and option checkers. |
| 49 | `ext4_inode` | `fs/ext4/rust/inode.rs` | Ext4 inode on-disk structure decoder and validator. |
| 50 | `ext4_balloc` | `fs/ext4/rust/balloc.rs` | Ext4 block allocator and free block allocation trackers. |
| **V** | **Networking Subsystem** | | |
| 51 | `nf_conntrack_core` | `net/netfilter/rust/core.rs` | Core connection tracking table logic and hash algorithms. |
| 52 | `nf_conntrack_proto_tcp` | `net/netfilter/rust/tcp.rs` | TCP connection state tracking machine and sequence validators. |
| 53 | `nf_conntrack_proto_udp` | `net/netfilter/rust/udp.rs` | UDP connection state tracking and timeout counters. |
| 54 | `nf_conntrack_proto_icmp` | `net/netfilter/rust/icmp.rs` | ICMP request/reply pairing and echo sequence trackers. |
| 55 | `ip6_flowlabel` | `net/ipv6/rust/flowlabel.rs`| IPv6 flow label extraction, routing, and header checks. |

---

## 3. Rust for Linux Coding Standards

### C FFI Interface Wrappers
When interacting with C-defined kernel objects, write an idiomatic Rust wrapper that manages lifetime constraints automatically via the `Drop` trait.

```rust
// Example: Safe wrapper for a C mutex
pub struct Mutex<T: ?Sized> {
    raw: bindings::mutex,
    data: UnsafeCell<T>,
}

// SAFETY: Mutex guarantees mutual exclusion for multi-threaded access
unsafe impl<T: ?Sized + Send> Sync for Mutex<T> {}
```

### Module Registration Macro
Every loadable module in the Rust for Linux project must use the official `module!` declaration macro to announce authorship, description, and module parameters.

```rust
use kernel::prelude::*;

module! {
    type: MyConnectionTracker,
    name: "nf_conntrack_rust_mini",
    author: "Linux Kernel Contributors",
    description: "Rust paravirtualized network connection tracker",
    license: "GPL",
}

struct MyConnectionTracker;

impl kernel::Module for MyConnectionTracker {
    fn init(_module: &'static ThisModule) -> Result<Self> {
        pr_info!("Rust Mini Conntrack Module Loaded\n");
        Ok(MyConnectionTracker)
    }
}

impl Drop for MyConnectionTracker {
    fn drop(&mut self) {
        pr_info!("Rust Mini Conntrack Module Unloaded\n");
    }
}
```

---

## 4. Safety and Verification Checklists

Before submiting any MVK module upstream, verify it against the following checklists:

1.  **FFI Assertions**: Ensure that any type mapped from a C header has a matching compilation assert checking its structural size and alignment.
2.  **Panics**: Ensure there are zero occurrences of `panic!`, `unwrap()`, or `expect()` in the module's release paths. Use fallible methods and proper `Result` propagation.
3.  **Data Races**: Mark thread-unsafe pointers as `*mut c_void` and wrap them inside safe synchronization primitives implementing `Send` and `Sync`.
4.  **Static Checking**: The module must compile with zero compiler warnings under target `x86_64-unknown-none` and pass `cargo clippy` checks successfully.
