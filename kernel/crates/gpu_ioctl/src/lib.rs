//! RunuX GPU Compute Subsystem - ioctl Gateway
//!
//! Provides the `/dev/dri/renderD128` ioctl interface to user-space
//! AI runtimes (e.g., Open Kernel Module compatible or AMD KFD).

#![no_std]
#![deny(clippy::all)]

use gpu_types::PageLocation;
use gpu_memory::HmmManager;
use drm_core::{DrmRingBuffer, DrmContext, GpuCommandPacket};

pub const DRM_IOCTL_BASE: u32 = 0x64;
pub const DRM_IOCTL_VERSION: u32 = (DRM_IOCTL_BASE << 8) | 0x00;
pub const DRM_IOCTL_GEM_CREATE: u32 = (DRM_IOCTL_BASE << 8) | 0x01;
pub const DRM_IOCTL_EXECBUFFER: u32 = (DRM_IOCTL_BASE << 8) | 0x02;
pub const DRM_IOCTL_SYNC_FENCE: u32 = (DRM_IOCTL_BASE << 8) | 0x03;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IoctlError {
    InvalidCommand,
    InvalidArguments,
    OutOfMemory,
    DeviceBusy,
    Timeout,
}

// Implementation deferred.
#[derive(Debug)]
pub struct RenderNode<'a, const RING_SIZE: usize> {
    hmm_manager: &'a mut HmmManager,
    ring_buffer: &'a mut DrmRingBuffer<RING_SIZE>,
    context: DrmContext,
}

impl<'a, const RING_SIZE: usize> RenderNode<'a, RING_SIZE> {
    pub fn new(
        hmm_manager: &'a mut HmmManager,
        ring_buffer: &'a mut DrmRingBuffer<RING_SIZE>,
        context_id: u32,
    ) -> Self {
        Self {
            hmm_manager,
            ring_buffer,
            context: DrmContext::new(context_id),
        }
    }

    /// Primary ioctl dispatch gateway.
    pub fn ioctl(&mut self, cmd: u32, arg_ptr: u64, arg_size: u64) -> Result<u64, IoctlError> {
        match cmd {
            DRM_IOCTL_VERSION => Ok(0x01000000), // Version 1.0.0

            DRM_IOCTL_GEM_CREATE => {
                // In a real implementation, we'd allocate physical memory dynamically.
                // Here we statically translate arg_ptr (vaddr) to a deterministic paddr.
                let paddr = arg_ptr.saturating_add(0x1000_0000); 
                self.hmm_manager
                    .map_page(arg_ptr, paddr, PageLocation::DeviceVram, true)
                    .map_err(|_| IoctlError::OutOfMemory)?;
                Ok(0)
            }

            DRM_IOCTL_EXECBUFFER => {
                let packet = GpuCommandPacket {
                    opcode: 0x01, // Exec
                    flags: 0x00,
                    payload_addr: arg_ptr,
                    payload_size: arg_size,
                };
                self.ring_buffer
                    .submit(packet)
                    .map_err(|_| IoctlError::DeviceBusy)?;
                Ok(self.context.emit_fence())
            }

            DRM_IOCTL_SYNC_FENCE => {
                let seqno = arg_ptr;
                if self.context.check_fence(seqno) {
                    Ok(0)
                } else {
                    Err(IoctlError::Timeout) // Would normally block/sleep
                }
            }

            _ => Err(IoctlError::InvalidCommand),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_node_ioctls() {
        let mut hmm = HmmManager::new();
        let mut ring = DrmRingBuffer::<4>::new().unwrap();
        let mut node = RenderNode::new(&mut hmm, &mut ring, 42);

        // Version check
        assert_eq!(node.ioctl(DRM_IOCTL_VERSION, 0, 0), Ok(0x01000000));

        // GEM Create (allocate memory)
        assert_eq!(node.ioctl(DRM_IOCTL_GEM_CREATE, 0x1000_0000, 4096), Ok(0));
        assert!(node.hmm_manager.translate(0x1000_0000).is_some());

        // Execbuffer (submit job)
        let fence_seq = node.ioctl(DRM_IOCTL_EXECBUFFER, 0x1000_0000, 1024).unwrap();
        assert_eq!(fence_seq, 1);
        assert!(node.context.check_fence(1));

        // Sync Fence
        assert_eq!(node.ioctl(DRM_IOCTL_SYNC_FENCE, 1, 0), Ok(0));
        
        // Invalid command
        assert_eq!(node.ioctl(0xFFFFFFFF, 0, 0), Err(IoctlError::InvalidCommand));
    }
}
