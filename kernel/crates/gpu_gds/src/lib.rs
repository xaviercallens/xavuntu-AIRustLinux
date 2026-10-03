//! RunuX GPU Compute Subsystem - GPUDirect Storage (GDS)
//!
//! Provides Peer-to-Peer (P2P) DMA capabilities for direct NVMe to VRAM transfers,
//! bypassing Host RAM (Zero-Copy architecture).

#![no_std]
#![deny(clippy::all)]

use gpu_types::SafeDmaFence;

pub const PAGE_SIZE: u64 = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GdsError {
    InvalidAddress,
    MisalignedTransfer,
    DmaBusy,
}

/// GPUDirect Storage P2P DMA Engine
#[derive(Debug)]
pub struct GdsP2pEngine {
    is_busy: bool,
}

impl GdsP2pEngine {
    pub const fn new() -> Self {
        Self { is_busy: false }
    }

    /// Submits a Peer-to-Peer DMA transaction directly from NVMe BAR to GPU VRAM.
    pub fn submit_nvme_to_vram_dma(
        &mut self,
        nvme_pci_bar: u64,
        vram_paddr: u64,
        size_bytes: u64,
        fence: &SafeDmaFence,
    ) -> Result<(), GdsError> {
        if self.is_busy {
            return Err(GdsError::DmaBusy);
        }

        if nvme_pci_bar % PAGE_SIZE != 0 || vram_paddr % PAGE_SIZE != 0 || size_bytes % PAGE_SIZE != 0 {
            return Err(GdsError::MisalignedTransfer);
        }

        if size_bytes == 0 {
            return Ok(());
        }

        // Simulate hardware DMA submission lock
        self.is_busy = true;

        // In a real bare-metal implementation:
        // We program the NVMe controller's PRP/SGL (Scatter Gather List) 
        // to point directly to the GPU's VRAM BAR addresses exposed via PCIe ReBAR.
        // The PCIe switch then routes the DMA TLPs directly without touching Host RAM.

        // Simulate DMA completion interrupt
        fence.signal_next();
        self.is_busy = false;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gds_p2p_transfer() {
        let mut gds = GdsP2pEngine::new();
        let fence = SafeDmaFence::new(10, 0);

        // Valid 4K aligned transfer
        assert!(gds
            .submit_nvme_to_vram_dma(0xA000_0000, 0xC000_0000, 4096, &fence)
            .is_ok());
        
        assert!(fence.is_completed(1));

        // Unaligned size
        assert_eq!(
            gds.submit_nvme_to_vram_dma(0xA000_0000, 0xC000_0000, 1024, &fence),
            Err(GdsError::MisalignedTransfer)
        );

        // Unaligned NVMe base
        assert_eq!(
            gds.submit_nvme_to_vram_dma(0xA000_1024, 0xC000_0000, 4096, &fence),
            Err(GdsError::MisalignedTransfer)
        );
    }
}
