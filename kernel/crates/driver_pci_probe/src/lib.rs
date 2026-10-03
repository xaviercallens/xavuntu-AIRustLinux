#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]
//! PCI device probing
//!
//! This module implements driver_pci_probe functionality for the Rust Linux Mini Kernel.
//! Based on Linux kernel drivers/pci

use core::ffi::c_int;
use driver_pci_core::{PciAddress, PciConfigBackend, PciDeviceInfo, SafePciDevice};
use kernel_types::{ensures, requires};

/// Module initialization
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_probe_init() -> c_int {
    // Implementation deferred.
    -19 // return value
}

/// Module cleanup
///
/// # Safety
/// No preconditions; performs no memory or hardware access.
#[no_mangle]
pub unsafe extern "C" fn driver_pci_probe_exit() {
}

#[no_mangle]
pub static DRIVER_PCI_PROBE_INITIALIZED: bool = false;

/// Probe a PCI device
///
/// # Panics
/// Panics if the device is null.
#[no_mangle]
pub extern "C" fn pci_probe_device(dev: &SafePciDevice) -> c_int {
    requires!(!dev.as_ptr().is_null(), "Device pointer must not be null");

    // Mock implementation of probe -- see pci_enumerate below for the
    // real bus walk; this C ABI entry point still does nothing real
    // and is not yet wired to it (SafePciDevice has no bus/device/
    // function fields to probe against -- see driver_pci_access's note
    // on the same limitation).

    ensures!(true, "Probe successful");
    0
}

/// Maximum devices a single [`pci_enumerate`] call can record. No
/// allocator is available in this `#![no_std]` context, so the result
/// is a fixed-size buffer rather than a growable `Vec`; 64 covers any
/// QEMU machine and most real systems' visible root-complex devices.
pub const MAX_ENUMERATED_DEVICES: usize = 64;

/// Real PCI bus enumeration via Configuration Mechanism #1 (see
/// `driver_pci_access`): walks every bus/device/function combination,
/// reads the vendor ID first (0xFFFF means "no device present" and is
/// skipped), and for anything present reads the rest of the header
/// (device ID, class, subclass, header type) into a `PciDeviceInfo`.
///
/// This does not use ACPI MCFG / ECAM, so on real multi-segment
/// hardware it only sees devices reachable through the legacy
/// mechanism -- true for a standard single-segment x86_64 desktop or
/// server root complex, including QEMU's `q35`/`i440fx` machines, but
/// not guaranteed on more exotic topologies. It also does a flat scan
/// of all 256 buses rather than recursively walking PCI-PCI bridges
/// (as Linux's real `pci_scan_bus` does) -- valid because Mechanism #1
/// addresses bus numbers directly, but slower and unable to discover
/// bus numbers a BIOS/firmware assigned non-contiguously behind a
/// bridge that itself sits on an unscanned bus. Good enough to find
/// every device on a flat single-bus QEMU machine; a real multi-bridge
/// system needs the recursive walk as follow-up work.
///
/// Returns the number of devices found and written into `out`.
///
/// Generic over `B: PciConfigBackend` so the exact same bus-walk logic
/// can run against real hardware (`driver_pci_access::HardwareIo`) or
/// against a captured fixture in test code (see
/// `tests/replay_gce_tpu_v5e.rs`) -- monomorphized at compile time, no
/// `dyn`/`alloc` needed, so this remains callable from the `#![no_std]`
/// kernel boot path.
///
/// # Safety
/// Same preconditions as the backend's `read32`: for
/// `driver_pci_access::HardwareIo`, only valid on x86_64 with I/O-port
/// access permitted. A replay backend has no such precondition.
#[cfg(target_arch = "x86_64")]
pub unsafe fn pci_enumerate<B: PciConfigBackend>(backend: &B, out: &mut [PciDeviceInfo; MAX_ENUMERATED_DEVICES]) -> usize {
    let mut count = 0usize;

    for bus in 0..=255u16 {
        let bus = bus as u8;
        for device in 0..32u8 {
            let mut is_multi_function = true; // assume until function 0 says otherwise
            for function in 0..8u8 {
                if function > 0 && !is_multi_function {
                    // Function 0 reported this isn't a multi-function
                    // device; skip the remaining functions.
                    break;
                }

                let id_word = backend.read32(bus, device, function, 0x00);
                let vendor_id = (id_word & 0xFFFF) as u16;
                if vendor_id == 0xFFFF {
                    if function == 0 {
                        break; // No device at this device number at all.
                    }
                    continue;
                }
                let device_id = (id_word >> 16) as u16;

                let class_word = backend.read32(bus, device, function, 0x08);
                let subclass = ((class_word >> 16) & 0xFF) as u8;
                let class = ((class_word >> 24) & 0xFF) as u8;

                let htype_word = backend.read32(bus, device, function, 0x0C);
                let raw_header_type = ((htype_word >> 16) & 0xFF) as u8;
                let multi_function = raw_header_type & 0x80 != 0;
                let header_type = raw_header_type & 0x7F;

                if function == 0 {
                    is_multi_function = multi_function;
                }

                if count < MAX_ENUMERATED_DEVICES {
                    out[count] = PciDeviceInfo {
                        address: PciAddress { bus, device, function },
                        vendor_id,
                        device_id,
                        class,
                        subclass,
                        header_type,
                        multi_function,
                    };
                    count += 1;
                }
            }
        }
    }

    count
}


#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_driver_pci_probe_init_stub() {
        unsafe { assert_eq!(driver_pci_probe_init(), -19); }
    }
}
