//! RunuX GPU Compute Subsystem - Multi-Tenancy MIG Scheduler
//!
//! Provides strict hardware isolation via Multi-Instance GPU (MIG) partitioning.
//! Implements Lean 4 Theorem 13.8 (`mig_tenant_isolation`).

#![no_std]
#![deny(clippy::all)]

use gpu_types::GpuPartitionSlice;

pub const MAX_PARTITIONS: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchedulerError {
    PartitionOverlap,
    OutOfPartitions,
    AccessDenied,
}

/// Multi-Instance GPU Scheduler
#[derive(Debug)]
pub struct MigScheduler {
    partitions: [Option<GpuPartitionSlice>; MAX_PARTITIONS],
    partition_count: usize,
}

impl MigScheduler {
    pub const fn new() -> Self {
        Self {
            partitions: [None; MAX_PARTITIONS],
            partition_count: 0,
        }
    }

    /// Allocates a new hardware partition for a tenant.
    pub fn allocate_partition(
        &mut self,
        tenant_id: u32,
        compute_slice_id: u32,
        vram_base: u64,
        vram_size: u64,
    ) -> Result<(), SchedulerError> {
        let new_slice = GpuPartitionSlice::new(tenant_id, compute_slice_id, vram_base, vram_size);

        // Enforce strict disjointness
        for slice in self.partitions.iter().flatten() {
            if !slice.is_disjoint(&new_slice) {
                return Err(SchedulerError::PartitionOverlap);
            }
        }

        for slot in self.partitions.iter_mut() {
            if slot.is_none() {
                *slot = Some(new_slice);
                self.partition_count += 1;
                return Ok(());
            }
        }

        Err(SchedulerError::OutOfPartitions)
    }

    /// Validates an access request against the tenant's partitions.
    pub fn validate_access(
        &self,
        tenant_id: u32,
        slice_id: u32,
        addr: u64,
    ) -> Result<(), SchedulerError> {
        for slice in self.partitions.iter().flatten() {
            if slice.tenant_id == tenant_id && slice.authorizes_access(addr, slice_id) {
                return Ok(());
            }
        }
        Err(SchedulerError::AccessDenied)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mig_scheduler_isolation() {
        let mut sched = MigScheduler::new();

        // Tenant 10, Slice 0, [0x1000..0x2000]
        assert!(sched.allocate_partition(10, 0, 0x1000, 0x1000).is_ok());
        
        // Tenant 20, Slice 1, [0x2000..0x3000] (Disjoint)
        assert!(sched.allocate_partition(20, 1, 0x2000, 0x1000).is_ok());

        // Overlapping VRAM with Tenant 10
        assert_eq!(
            sched.allocate_partition(30, 2, 0x1800, 0x1000),
            Err(SchedulerError::PartitionOverlap)
        );

        // Overlapping Compute Slice with Tenant 20
        assert_eq!(
            sched.allocate_partition(30, 1, 0x3000, 0x1000),
            Err(SchedulerError::PartitionOverlap)
        );

        // Authorized access
        assert_eq!(sched.validate_access(10, 0, 0x1500), Ok(()));
        
        // Unauthorized access (wrong tenant)
        assert_eq!(sched.validate_access(20, 0, 0x1500), Err(SchedulerError::AccessDenied));
        
        // Unauthorized access (wrong slice)
        assert_eq!(sched.validate_access(10, 1, 0x1500), Err(SchedulerError::AccessDenied));
        
        // Unauthorized access (out of bounds)
        assert_eq!(sched.validate_access(10, 0, 0x2500), Err(SchedulerError::AccessDenied));
    }
}
