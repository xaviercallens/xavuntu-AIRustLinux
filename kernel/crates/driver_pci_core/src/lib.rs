#![allow(clippy::all, clippy::pedantic)]
#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
//! PCI bus driver
//!
//! This module implements driver_pci_core functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel drivers/pci

use core::ffi::c_int;

/// Module initialization
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_core_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_core_exit() {
}

#[no_mangle]
pub static DRIVER_PCI_CORE_INITIALIZED: bool = false;

/// A source of PCI configuration-space dword reads, abstracting over
/// where those reads actually come from. `driver_pci_access::HardwareIo`
/// implements this against real I/O ports (`0xCF8`/`0xCFC`); test code
/// can implement it against a captured fixture instead, so
/// `driver_pci_probe::pci_enumerate`'s real bus-walk logic can be
/// exercised in CI without hardware access, using data genuinely
/// captured from real hardware rather than hand-written fixtures.
///
/// Generic (not `dyn`) dispatch is used everywhere this trait is
/// consumed, so implementors work in `#![no_std]` contexts (the kernel
/// boot path) without needing `alloc`.
pub trait PciConfigBackend {
    /// Read a 32-bit value from PCI configuration space at
    /// `bus:device.function`, offset `offset` (4-byte aligned).
    ///
    /// # Safety
    /// A real hardware-backed implementation requires the same
    /// preconditions as `driver_pci_access::pci_config_read32`
    /// (I/O-port access permitted). A replay/fixture-backed
    /// implementation has no such precondition, but still declares the
    /// method `unsafe` so generic code can call it uniformly without
    /// the backend's identity leaking into the caller's safety
    /// reasoning.
    unsafe fn read32(&self, bus: u8, device: u8, function: u8, offset: u8) -> u32;
}

/// A safe wrapper around raw `pci_dev` pointers.
#[repr(transparent)]
pub struct SafePciDevice(*mut core::ffi::c_void);

impl SafePciDevice {
    /// Creates a new `SafePciDevice` from a raw pointer.
    ///
    /// # Safety
    /// The caller must ensure that the pointer is valid and properly aligned.
    #[must_use]
    pub unsafe fn new(ptr: *mut core::ffi::c_void) -> Self {
        Self(ptr)
    }

    /// Returns the underlying raw pointer.
    #[must_use]
    pub fn as_ptr(&self) -> *mut core::ffi::c_void {
        self.0
    }
}

/// A PCI bus/device/function address triple, per the standard PCI
/// addressing scheme (256 buses x 32 devices x 8 functions).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PciAddress {
    pub bus: u8,
    pub device: u8,
    pub function: u8,
}

/// Identification and topology fields read directly out of a real
/// device's configuration-space header (offsets 0x00-0x0F), plus its
/// address. Genuinely populated by real bus enumeration -- see
/// `driver_pci_probe::pci_enumerate`.
#[derive(Debug, Clone, Copy)]
pub struct PciDeviceInfo {
    pub address: PciAddress,
    pub vendor_id: u16,
    pub device_id: u16,
    /// Base class code (offset 0x0B): e.g. 0x03 = display controller.
    pub class: u8,
    /// Sub-class code (offset 0x0A).
    pub subclass: u8,
    /// Header type (offset 0x0E, multi-function bit masked off).
    pub header_type: u8,
    pub multi_function: bool,
}

impl PciDeviceInfo {
    /// True if `class`/`subclass` match a display controller / 3D
    /// controller (the PCI class codes real GPUs, including NVIDIA
    /// RTX and T4 cards, report): class 0x03 covers VGA-compatible
    /// (subclass 0x00), XGA (0x01), 3D (0x02), and other (0x80)
    /// display controllers.
    #[must_use]
    pub fn is_display_controller(&self) -> bool {
        self.class == 0x03
    }
}

/// A known NVIDIA data-center or workstation GPU, identified purely by
/// its public PCI vendor/device ID -- for logging/recognition only,
/// never for driving the device. IDs are cited from the PCI ID
/// Repository (<https://pci-ids.ucw.cz>), the canonical public registry
/// pciutils/lspci itself ships and queries.
#[derive(Debug, Clone, Copy)]
pub struct KnownGpu {
    pub vendor_id: u16,
    pub device_id: u16,
    pub name: &'static str,
}

/// NVIDIA vendor ID (10de), per <https://pci-ids.ucw.cz/read/PC/10de>.
pub const NVIDIA_VENDOR_ID: u16 = 0x10de;
/// Red Hat / Qumranet virtio vendor ID (1af4), per
/// <https://pci-ids.ucw.cz/read/PC/1af4> -- used by QEMU's `virtio-gpu-pci`.
pub const VIRTIO_VENDOR_ID: u16 = 0x1af4;
/// Google, Inc. PCI vendor ID (1ae0), per
/// <https://pci-ids.ucw.cz/read/PC/1ae0> (checked directly against the
/// live database 2026-09-27, not assumed) -- this vendor ID is public
/// and well-established, not a new discovery. That database lists
/// device `0042` ("Compute Engine Virtual Ethernet [gVNIC]") and `001f`
/// (an NVMe device) under this vendor, both observed and matched on a
/// real GCP `v5litepod-1` TPU VM (2026-09-27). It does **not** list
/// device `0063` -- the accelerator device also observed on that same
/// VM (class `ff00`, vendor-specific) -- as of the same check; whether
/// that specific device ID is genuinely undocumented publicly or simply
/// not yet added to this registry is not established either way. See
/// `docs/roadmap/GPU_REAL_HARDWARE_TELEMETRY.md` for the full record,
/// including the caveat that this was observed through a hypervisor's
/// PCI presentation to a guest, not confirmed as physical silicon.
pub const GOOGLE_VENDOR_ID: u16 = 0x1ae0;

/// A small, non-exhaustive table of real NVIDIA GPU PCI IDs relevant to
/// standard AI-computing hardware, each individually verified against
/// <https://pci-ids.ucw.cz> at the time this table was written (2026-09-27):
/// - 10de:1eb8 "TU104GL [Tesla T4]" -- the data-center inference/training
///   card named in this crate's test plan.
/// - 10de:2684 "AD102 [GeForce RTX 4090]" -- a current RTX desktop card.
///
/// This table exists to let real enumeration output a human-readable
/// name when it sees one of these IDs; it implies nothing about being
/// able to drive the device (see `docs/roadmap/STANDARD_HARDWARE_AI_GPU_PLAN.md`).
pub const KNOWN_NVIDIA_GPUS: &[KnownGpu] = &[
    KnownGpu { vendor_id: NVIDIA_VENDOR_ID, device_id: 0x1eb8, name: "NVIDIA Tesla T4 (TU104GL)" },
    KnownGpu { vendor_id: NVIDIA_VENDOR_ID, device_id: 0x2684, name: "NVIDIA GeForce RTX 4090 (AD102)" },
];

/// QEMU's virtio-gpu PCI device ID, per
/// <https://www.qemu.org/docs/master/specs/pci-ids.html> (modern
/// virtio 1.0 device IDs are `0x1040 + virtio_device_id`; virtio-gpu's
/// device id is 16, giving 0x1050).
pub const VIRTIO_GPU_DEVICE_ID: u16 = 0x1050;

/// Look up a known-GPU name for a vendor/device ID pair, if any.
#[must_use]
pub fn known_gpu_name(vendor_id: u16, device_id: u16) -> Option<&'static str> {
    if vendor_id == VIRTIO_VENDOR_ID && device_id == VIRTIO_GPU_DEVICE_ID {
        return Some("QEMU virtio-gpu (virtio 1.0)");
    }
    KNOWN_NVIDIA_GPUS
        .iter()
        .find(|g| g.vendor_id == vendor_id && g.device_id == device_id)
        .map(|g| g.name)
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_driver_pci_core_init_stub() {
        unsafe { assert_eq!(driver_pci_core_init(), -19); }
    }
    use super::{known_gpu_name, PciAddress, PciDeviceInfo};

    #[test]
    fn recognizes_virtio_gpu() {
        assert_eq!(known_gpu_name(0x1af4, 0x1050), Some("QEMU virtio-gpu (virtio 1.0)"));
    }

    #[test]
    fn recognizes_tesla_t4() {
        assert_eq!(known_gpu_name(0x10de, 0x1eb8), Some("NVIDIA Tesla T4 (TU104GL)"));
    }

    #[test]
    fn recognizes_rtx_4090() {
        assert_eq!(known_gpu_name(0x10de, 0x2684), Some("NVIDIA GeForce RTX 4090 (AD102)"));
    }

    #[test]
    fn unknown_vendor_device_is_not_recognized() {
        assert_eq!(known_gpu_name(0xFFFF, 0xFFFF), None);
        // A real, unrelated device (Intel 440FX host bridge) must not
        // false-positive as a known GPU.
        assert_eq!(known_gpu_name(0x8086, 0x1237), None);
    }

    #[test]
    fn is_display_controller_matches_class_0x03_only() {
        let base = PciDeviceInfo {
            address: PciAddress { bus: 0, device: 2, function: 0 },
            vendor_id: 0x1af4,
            device_id: 0x1050,
            class: 0x03,
            subclass: 0x80,
            header_type: 0,
            multi_function: false,
        };
        assert!(base.is_display_controller());

        let bridge = PciDeviceInfo { class: 0x06, ..base };
        assert!(!bridge.is_display_controller());
    }
}
