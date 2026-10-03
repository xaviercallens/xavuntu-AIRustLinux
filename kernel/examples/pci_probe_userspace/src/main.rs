//! Runs RunuX's real `driver_pci_probe::pci_enumerate` -- the exact same
//! function `examples/x86_64_qemu_harness` calls at boot -- as a
//! privileged Linux userspace binary instead of inside a custom kernel.
//!
//! Why this exists: verifying the bare-metal PCI code against a real
//! (non-QEMU) hypervisor's PCI presentation would normally need a full
//! custom kernel boot on a cloud VM, which needs bootloader/serial-console
//! plumbing that is separate work. Linux lets a root process call
//! `iopl(3)` to grant itself the same raw port-I/O access ring 0 code
//! has, so the same `in`/`out`-instruction-based config-space reads this
//! project's kernel code performs can run here, unmodified, against a
//! real hypervisor -- a real cross-check, not a simulation of one.
//!
//! # Safety design (read this before changing the default mode)
//!
//! An earlier version of this tool defaulted to probing every BAR's size
//! via the standard write-0xFFFFFFFF/read-back/restore technique. That is
//! unsafe from userspace on a live system for two independent reasons:
//!
//! 1. `0xCF8`/`0xCFC` access is a two-step, non-atomic protocol. The
//!    Linux kernel serializes its own config-space accesses with an
//!    internal lock; a userspace `iopl` process has no way to take that
//!    lock, so an unlucky interleaving can corrupt either side's read or
//!    write.
//! 2. Sizing a BAR temporarily relocates it to `0xFFFFFFFF`. If the
//!    device has a bound Linux driver actively using that BAR (e.g. the
//!    network interface carrying the very SSH session running this
//!    tool), that driver's in-flight MMIO accesses go to garbage for the
//!    duration -- a real, if usually brief, disruption risk, not a
//!    theoretical one.
//!
//! Requires root (`CAP_SYS_RAWIO`). Not meant to run outside a
//! disposable VM: `iopl(3)` grants this process unrestricted hardware
//! I/O port access for its lifetime.
//!
//! Default mode is **read-only**: enumerate and read identity/config
//! bytes only, never write. `--bar-size-unbound` additionally sizes BARs,
//! but only on functions with no driver currently bound in sysfs
//! (`/sys/bus/pci/devices/<bdf>/driver` absent) -- checked before every
//! single BAR write, not just once at startup.

use std::io::Read;
use std::time::Instant;

fn bdf_string(addr: &driver_pci_core::PciAddress) -> String {
    format!("0000:{:02x}:{:02x}.{:x}", addr.bus, addr.device, addr.function)
}

/// True if sysfs shows no driver bound to this function. Checked fresh
/// before every BAR-sizing write, not cached, since driver binding can
/// change while this tool runs.
fn is_driver_unbound(addr: &driver_pci_core::PciAddress) -> bool {
    let path = format!("/sys/bus/pci/devices/{}/driver", bdf_string(addr));
    !std::path::Path::new(&path).exists()
}

/// Read a function's declared class/subclass out of sysfs, as an
/// independent cross-check source separate from RunuX's own config-space
/// read of the same fields.
fn sysfs_class(addr: &driver_pci_core::PciAddress) -> Option<(u8, u8)> {
    let path = format!("/sys/bus/pci/devices/{}/class", bdf_string(addr));
    let mut s = String::new();
    std::fs::File::open(path).ok()?.read_to_string(&mut s).ok()?;
    let s = s.trim().trim_start_matches("0x");
    if s.len() < 6 {
        return None;
    }
    let class = u8::from_str_radix(&s[0..2], 16).ok()?;
    let subclass = u8::from_str_radix(&s[2..4], 16).ok()?;
    Some((class, subclass))
}

fn print_json_escaped(s: &str) {
    print!("\"");
    for c in s.chars() {
        match c {
            '"' | '\\' => {
                print!("\\{c}");
            }
            _ => print!("{c}"),
        }
    }
    print!("\"");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let bar_size_unbound = args.iter().any(|a| a == "--bar-size-unbound");
    let json = args.iter().any(|a| a == "--json");
    let dump_config = args.iter().any(|a| a == "--dump-config");

    let start = Instant::now();
    // SAFETY: iopl(3) is a well-defined Linux syscall; failure is
    // reported via errno and checked below. This process must be root.
    let iopl_rc = unsafe { libc::iopl(3) };
    let iopl_errno = std::io::Error::last_os_error();
    if iopl_rc != 0 {
        if json {
            println!("{{\"iopl_ok\":false,\"iopl_errno\":\"{iopl_errno}\"}}");
        } else {
            eprintln!("iopl(3) failed ({iopl_errno}) -- must run as root (and not under Secure Boot lockdown).");
        }
        std::process::exit(1);
    }

    let mut devices = [driver_pci_core::PciDeviceInfo {
        address: driver_pci_core::PciAddress { bus: 0, device: 0, function: 0 },
        vendor_id: 0,
        device_id: 0,
        class: 0,
        subclass: 0,
        header_type: 0,
        multi_function: false,
    }; driver_pci_probe::MAX_ENUMERATED_DEVICES];

    // SAFETY: iopl(3) above granted this process full I/O port access,
    // satisfying pci_enumerate's precondition; called once, synchronously.
    let count = unsafe { driver_pci_probe::pci_enumerate(&driver_pci_access::HardwareIo, &mut devices) };
    let enum_wall_ns = start.elapsed().as_nanos();

    if json {
        println!("{{");
        println!("  \"iopl_ok\": true,");
        println!("  \"enum_wall_ns\": {enum_wall_ns},");
        println!("  \"device_count\": {count},");
        println!("  \"devices\": [");
        for (i, dev) in devices[..count].iter().enumerate() {
            let bdf = bdf_string(&dev.address);
            let sysfs = sysfs_class(&dev.address);
            let sysfs_matches = sysfs == Some((dev.class, dev.subclass));
            print!("    {{\"bdf\": ");
            print_json_escaped(&bdf);
            print!(", \"vendor\": \"{:04x}\", \"device\": \"{:04x}\", \"class\": \"{:02x}\", \"subclass\": \"{:02x}\", \"header_type\": \"{:02x}\", \"multi_function\": {}, \"driver_bound\": {}, \"sysfs_class_matches\": {}",
                dev.vendor_id, dev.device_id, dev.class, dev.subclass, dev.header_type, dev.multi_function,
                !is_driver_unbound(&dev.address), sysfs_matches);

            let known = driver_pci_core::known_gpu_name(dev.vendor_id, dev.device_id);
            if let Some(name) = known {
                print!(", \"known_name\": ");
                print_json_escaped(name);
            } else {
                print!(", \"known_name\": null");
            }

            if dump_config {
                print!(", \"config_bytes_hex\": \"");
                for off in (0u8..=0xfc).step_by(4) {
                    // SAFETY: same iopl(3) grant as above; read-only.
                    let word = unsafe {
                        driver_pci_access::pci_config_read32(dev.address.bus, dev.address.device, dev.address.function, off)
                    };
                    print!("{:08x}", word.swap_bytes());
                }
                print!("\"");
            }

            print!(", \"bars\": [");
            if bar_size_unbound && dev.is_display_controller() && is_driver_unbound(&dev.address) {
                let mut first = true;
                for (i, bar_offset) in [0x10u8, 0x14, 0x18, 0x1C, 0x20, 0x24].iter().enumerate() {
                    if !is_driver_unbound(&dev.address) {
                        break; // re-check every iteration: binding can change concurrently
                    }
                    // SAFETY: driver-unbound re-checked immediately above;
                    // this function saves/clears/restores the Command
                    // register's decode bits around the size probe.
                    let size = unsafe {
                        driver_pci_access::pci_bar_size(dev.address.bus, dev.address.device, dev.address.function, *bar_offset)
                    };
                    if size > 0 {
                        if !first {
                            print!(", ");
                        }
                        print!("{{\"index\": {i}, \"size_bytes\": {size}}}");
                        first = false;
                    }
                }
            }
            print!("]}}");
            if i + 1 < count {
                println!(",");
            } else {
                println!();
            }
        }
        println!("  ]");
        println!("}}");
        return;
    }

    println!("RunuX driver_pci_probe::pci_enumerate found {count} real PCI device(s) in {enum_wall_ns}ns (read-only mode{}):",
        if bar_size_unbound { ", BAR sizing enabled for unbound display controllers only" } else { "" });
    for dev in &devices[..count] {
        let bdf = bdf_string(&dev.address);
        let sysfs = sysfs_class(&dev.address);
        let sysfs_note = match sysfs {
            Some(s) if s == (dev.class, dev.subclass) => "sysfs class: match",
            Some(_) => "sysfs class: MISMATCH",
            None => "sysfs class: unavailable",
        };
        print!(
            "  {bdf} vendor={:04x} device={:04x} class={:02x} subclass={:02x} [{sysfs_note}]",
            dev.vendor_id, dev.device_id, dev.class, dev.subclass,
        );
        if let Some(name) = driver_pci_core::known_gpu_name(dev.vendor_id, dev.device_id) {
            print!(" -- {name}");
        } else if dev.vendor_id == driver_pci_core::GOOGLE_VENDOR_ID {
            print!(" -- Google, Inc. device (see lspci -nn for the specific accelerator/NIC name)");
        }
        println!();

        if bar_size_unbound && dev.is_display_controller() {
            if is_driver_unbound(&dev.address) {
                for (i, bar_offset) in [0x10u8, 0x14, 0x18, 0x1C, 0x20, 0x24].iter().enumerate() {
                    if !is_driver_unbound(&dev.address) {
                        println!("    (driver bound mid-scan, aborting remaining BAR probes for this device)");
                        break;
                    }
                    // SAFETY: driver-unbound re-checked immediately above.
                    let size = unsafe {
                        driver_pci_access::pci_bar_size(dev.address.bus, dev.address.device, dev.address.function, *bar_offset)
                    };
                    if size > 0 {
                        println!("    BAR{i} size=0x{size:08x} bytes");
                    }
                }
            } else {
                println!("    (skipped BAR sizing: a driver is bound to this function)");
            }
        }
    }
}
