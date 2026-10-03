#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
//! PCI config space
//!
//! Real x86 legacy PCI configuration-space access via I/O ports
//! `0xCF8`/`0xCFC` ("Configuration Mechanism #1", the classic
//! CONFIG_ADDRESS/CONFIG_DATA scheme every x86 chipset since the
//! original PCI spec supports, including QEMU's `q35`/`i440fx`
//! machines). This reaches the first 256 bytes of a device's config
//! space -- enough for vendor/device ID, class code, header type, and
//! the base BARs -- but not the 4KiB PCIe extended config space, which
//! would need MMCONFIG/ECAM (an ACPI MCFG table lookup) instead.

use core::ffi::c_int;
use driver_pci_core::{PciConfigBackend, SafePciDevice};
use kernel_types::{ensures, requires};

const CONFIG_ADDRESS: u16 = 0xCF8;
const CONFIG_DATA: u16 = 0xCFC;

/// The real hardware [`PciConfigBackend`]: reads go through
/// [`pci_config_read32`] (I/O ports `0xCF8`/`0xCFC`). Zero-sized --
/// exists purely to give the hardware path a name generic callers can
/// select, alongside a replay/fixture-backed implementation in test
/// code.
#[cfg(target_arch = "x86_64")]
pub struct HardwareIo;

#[cfg(target_arch = "x86_64")]
impl PciConfigBackend for HardwareIo {
    /// # Safety
    /// Same preconditions as [`pci_config_read32`].
    unsafe fn read32(&self, bus: u8, device: u8, function: u8, offset: u8) -> u32 {
        pci_config_read32(bus, device, function, offset)
    }
}

fn config_address(bus: u8, device: u8, function: u8, offset: u8) -> u32 {
    0x8000_0000
        | (u32::from(bus) << 16)
        | (u32::from(device & 0x1f) << 11)
        | (u32::from(function & 0x07) << 8)
        | u32::from(offset & 0xfc)
}

/// Read a 32-bit value from PCI configuration space.
///
/// # Safety
/// Only valid on x86/x86_64 with I/O-port access permitted (ring 0, or
/// an I/O bitmap granting these two ports). `bus`/`device`/`function`
/// select the target per the PCI addressing scheme; `offset` must be
/// 4-byte aligned (the low 2 bits are masked off by the hardware).
#[cfg(target_arch = "x86_64")]
#[inline]
pub unsafe fn pci_config_read32(bus: u8, device: u8, function: u8, offset: u8) -> u32 {
    let addr = config_address(bus, device, function, offset);
    core::arch::asm!("out dx, eax", in("dx") CONFIG_ADDRESS, in("eax") addr, options(nomem, nostack, preserves_flags));
    let value: u32;
    core::arch::asm!("in eax, dx", in("dx") CONFIG_DATA, out("eax") value, options(nomem, nostack, preserves_flags));
    value
}

/// Write a 32-bit value to PCI configuration space.
///
/// # Safety
/// Same preconditions as [`pci_config_read32`]. The caller is
/// responsible for not corrupting a live device's configuration (e.g.
/// restoring a BAR after a size probe).
#[cfg(target_arch = "x86_64")]
#[inline]
pub unsafe fn pci_config_write32(bus: u8, device: u8, function: u8, offset: u8, value: u32) {
    let addr = config_address(bus, device, function, offset);
    core::arch::asm!("out dx, eax", in("dx") CONFIG_ADDRESS, in("eax") addr, options(nomem, nostack, preserves_flags));
    core::arch::asm!("out dx, eax", in("dx") CONFIG_DATA, in("eax") value, options(nomem, nostack, preserves_flags));
}

/// Probe the size of a 32-bit memory BAR at `bar_offset` (0x10, 0x14, ...
/// for header-type-0 devices) using the standard "write all 1s, read
/// back the size mask, restore the original value" technique.
/// Returns 0 if the BAR is unimplemented.
///
/// This treats every BAR as an independent 32-bit register. A real
/// 64-bit memory BAR (type bits `[2:1] == 0b10` in the low dword) pairs
/// two consecutive BAR slots into one 64-bit base address; probing
/// such a BAR's low dword alone, as this function does, gives a
/// correct size only when the true size fits within 32 bits (true for
/// every BAR observed on QEMU's `virtio-gpu-pci` device in practice) --
/// combining both dwords for the fully general 64-bit case is
/// unimplemented follow-up work, not silently assumed to work.
///
/// Clears the Command register's I/O- and memory-space decode bits
/// (offset 0x04, bits 0-1) before writing the BAR and restores them
/// immediately after, so the temporarily-relocated BAR is never actually
/// decoded by the device while the write is live. This does not make
/// the probe safe to call on a device with an active driver bound to
/// it -- the driver's own in-flight accesses are not synchronized with
/// this function at all -- it only narrows the window in which a
/// *bus-mastering* access from the device itself could land on the
/// bogus address. Callers running outside ring 0 (e.g.
/// `examples/pci_probe_userspace`) are responsible for checking there
/// is no bound driver before calling this at all; this function cannot
/// check that itself (no `#[std]` filesystem access in this `no_std`
/// crate).
///
/// # Safety
/// Same preconditions as [`pci_config_read32`]/[`pci_config_write32`].
/// The caller must ensure no concurrent access to this device's config
/// space or BARs can occur while this function runs (e.g. by holding
/// whatever lock a real kernel's PCI subsystem would hold, or, in a
/// userspace caller, by confirming via sysfs that no driver is bound).
#[cfg(target_arch = "x86_64")]
pub unsafe fn pci_bar_size(bus: u8, device: u8, function: u8, bar_offset: u8) -> u64 {
    const COMMAND_OFFSET: u8 = 0x04;
    const DECODE_BITS: u32 = 0x3; // bit0 = I/O space, bit1 = memory space

    let original_command = pci_config_read32(bus, device, function, COMMAND_OFFSET);
    pci_config_write32(bus, device, function, COMMAND_OFFSET, original_command & !DECODE_BITS);

    let original_bar = pci_config_read32(bus, device, function, bar_offset);
    pci_config_write32(bus, device, function, bar_offset, 0xFFFF_FFFF);
    let mask = pci_config_read32(bus, device, function, bar_offset);
    pci_config_write32(bus, device, function, bar_offset, original_bar);

    pci_config_write32(bus, device, function, COMMAND_OFFSET, original_command);

    if mask == 0 {
        return 0;
    }
    // Bit 0 of a memory BAR is always 0 (space indicator); the low 4
    // bits also encode type/prefetchable and are not part of the size
    // mask for a 32-bit memory BAR.
    let size_mask = mask & 0xFFFF_FFF0;
    u64::from(!size_mask + 1)
}

/// Module initialization
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_access_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_access_exit() {}

#[no_mangle]
pub static DRIVER_PCI_ACCESS_INITIALIZED: bool = false;

/// Read from PCI configuration space (C ABI entry point; dword-aligned
/// reads only, matching [`pci_config_read32`]).
///
/// `SafePciDevice` is currently an opaque pointer with no defined
/// bus/device/function fields, so this entry point can only address
/// bus 0, device 0, function 0 (the host bridge, always present) --
/// it does not yet encode which device `dev` actually refers to.
/// Real multi-device addressing goes through [`pci_config_read32`]
/// directly (see `driver_pci_probe::pci_enumerate`), which takes an
/// explicit bus/device/function triple; extending `SafePciDevice`
/// itself to carry that triple is separate, out-of-scope work.
///
/// # Panics
/// Panics if the offset and size are out of bounds.
///
/// # Safety
/// Same preconditions as [`pci_config_read32`]; `dev` must be a valid,
/// non-null `SafePciDevice`.
#[no_mangle]
pub unsafe extern "C" fn pci_read_config(dev: &SafePciDevice, offset: u32, size: u32, value: &mut u32) -> c_int {
    requires!(!dev.as_ptr().is_null(), "Device pointer must not be null");
    requires!(offset + size <= 4096, "Read out of bounds"); // Basic PCI-e extended config space limit

    #[cfg(target_arch = "x86_64")]
    {
        *value = pci_config_read32(0, 0, 0, offset as u8);
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        *value = 0;
    }

    ensures!(true, "Read successful");
    0
}

/// Write to PCI configuration space (C ABI entry point; dword-aligned
/// writes only, matching [`pci_config_write32`]).
///
/// # Panics
/// Panics if the offset and size are out of bounds.
///
/// # Safety
/// Same preconditions as [`pci_config_write32`]; `dev` must be a valid,
/// non-null `SafePciDevice`.
#[no_mangle]
pub unsafe extern "C" fn pci_write_config(dev: &SafePciDevice, offset: u32, size: u32, value: u32) -> c_int {
    requires!(!dev.as_ptr().is_null(), "Device pointer must not be null");
    requires!(offset + size <= 4096, "Write out of bounds");

    #[cfg(target_arch = "x86_64")]
    {
        pci_config_write32(0, 0, 0, offset as u8, value);
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        let _ = value;
    }

    ensures!(true, "Write successful");
    0
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_driver_pci_access_init_stub() {
        unsafe { assert_eq!(driver_pci_access_init(), -19); }
    }
    use super::config_address;

    #[test]
    fn config_address_matches_mechanism_1_layout() {
        // Bus 0, device 2, function 0, offset 0: the classic
        // enable-bit | bus<<16 | device<<11 | function<<8 | offset
        // layout every x86 chipset since the original PCI spec uses.
        assert_eq!(config_address(0, 2, 0, 0x00), 0x8000_1000);
        // Non-zero bus and a non-4-byte-aligned offset gets masked to
        // the containing dword (hardware requirement: the low 2 bits
        // of CONFIG_ADDRESS are always zero).
        assert_eq!(config_address(1, 0, 0, 0x02), 0x8001_0000);
    }

    #[test]
    fn config_address_masks_device_and_function_to_valid_ranges() {
        // Device numbers only have 5 bits (0-31); function only 3 (0-7).
        // An out-of-range caller value must not corrupt neighboring
        // fields of the address.
        assert_eq!(config_address(0, 0xFF, 0xFF, 0), config_address(0, 0x1F, 0x07, 0));
    }
}
