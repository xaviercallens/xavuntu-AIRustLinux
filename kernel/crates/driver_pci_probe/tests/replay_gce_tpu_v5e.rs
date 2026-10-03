//! Replays `driver_pci_probe::pci_enumerate` against a fixture captured
//! from a *real* GCP Cloud TPU v5e VM (see
//! `docs/roadmap/GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md` for the full n=30,
//! independently-oracle-checked campaign this fixture is one run from).
//! This re-verifies that exact real-hardware result on every CI run,
//! with no cloud access needed, using genuinely captured config-space
//! bytes rather than a hand-written approximation of what a device
//! "should" look like.

use driver_pci_core::{PciAddress, PciConfigBackend, PciDeviceInfo};
use std::collections::HashMap;

const FIXTURE: &str = include_str!("fixtures/gce_tpu_v5e_us-west4-a_2026-09-27.txt");

/// Serves PCI config-space reads from a captured fixture instead of real
/// hardware. Rejects any offset not covered by the captured 256 bytes
/// (this fixture only has the first 256 bytes -- legacy config space,
/// not the 4KiB PCIe extended space).
struct ReplayBackend {
    /// (bus, device, function) -> 256 raw config-space bytes.
    devices: HashMap<(u8, u8, u8), Vec<u8>>,
}

impl ReplayBackend {
    fn from_fixture(text: &str) -> Self {
        let mut devices = HashMap::new();
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let parts: Vec<&str> = line.splitn(4, ',').collect();
            assert_eq!(parts.len(), 4, "malformed fixture line: {line}");
            let bus: u8 = parts[0].parse().expect("bus");
            let device: u8 = parts[1].parse().expect("device");
            let function: u8 = parts[2].parse().expect("function");
            let hex = parts[3];
            assert_eq!(hex.len(), 512, "expected 256 bytes (512 hex chars) of config space, got {} for {bus}:{device}.{function}", hex.len());
            let bytes: Vec<u8> = (0..hex.len())
                .step_by(2)
                .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).expect("hex byte"))
                .collect();
            devices.insert((bus, device, function), bytes);
        }
        assert!(!devices.is_empty(), "fixture parsed to zero devices -- format regression");
        Self { devices }
    }
}

impl PciConfigBackend for ReplayBackend {
    /// # Safety
    /// No real precondition (no hardware access) -- `unsafe` only to
    /// satisfy the trait signature, which real backends do need.
    unsafe fn read32(&self, bus: u8, device: u8, function: u8, offset: u8) -> u32 {
        let Some(bytes) = self.devices.get(&(bus, device, function)) else {
            return 0xFFFF_FFFF; // "no device present", matching real hardware's response
        };
        let off = offset as usize;
        if off + 4 > bytes.len() {
            return 0;
        }
        u32::from_le_bytes([bytes[off], bytes[off + 1], bytes[off + 2], bytes[off + 3]])
    }
}

#[test]
fn replay_finds_exactly_the_devices_the_real_tpu_vm_had() {
    let backend = ReplayBackend::from_fixture(FIXTURE);

    let mut out = [PciDeviceInfo {
        address: PciAddress { bus: 0, device: 0, function: 0 },
        vendor_id: 0,
        device_id: 0,
        class: 0,
        subclass: 0,
        header_type: 0,
        multi_function: false,
    }; driver_pci_probe::MAX_ENUMERATED_DEVICES];

    // SAFETY: ReplayBackend has no hardware precondition.
    let count = unsafe { driver_pci_probe::pci_enumerate(&backend, &mut out) };

    assert_eq!(count, 8, "expected exactly the 8 devices captured on the real TPU VM");

    let expect = |bus: u8, device: u8, function: u8, vendor: u16, dev_id: u16, class: u8, subclass: u8| {
        let found = out[..count]
            .iter()
            .find(|d| d.address == PciAddress { bus, device, function })
            .unwrap_or_else(|| panic!("device {bus:02x}:{device:02x}.{function:x} missing from replay result"));
        assert_eq!(found.vendor_id, vendor, "vendor mismatch at {bus:02x}:{device:02x}.{function:x}");
        assert_eq!(found.device_id, dev_id, "device mismatch at {bus:02x}:{device:02x}.{function:x}");
        assert_eq!(found.class, class, "class mismatch at {bus:02x}:{device:02x}.{function:x}");
        assert_eq!(found.subclass, subclass, "subclass mismatch at {bus:02x}:{device:02x}.{function:x}");
    };

    // Every field below is copied from the real, independently-verified
    // GCE_TPU_PCI_TOPOLOGY_TELEMETRY.md campaign result, not invented.
    expect(0x00, 0x00, 0x0, 0x8086, 0x1237, 0x06, 0x00); // Intel 440FX host bridge
    expect(0x00, 0x01, 0x0, 0x8086, 0x7110, 0x06, 0x01); // Intel PIIX4 ISA bridge
    expect(0x00, 0x01, 0x3, 0x8086, 0x7113, 0x06, 0x80); // Intel PIIX4 ACPI
    expect(0x00, 0x03, 0x0, 0x1022, 0x164f, 0x08, 0x06); // AMD-Vi IOMMU (vfio-pci passthrough infra)
    expect(0x00, 0x04, 0x0, 0x1af4, 0x1004, 0x00, 0x00); // Red Hat Virtio SCSI
    expect(0x00, 0x05, 0x0, 0x1ae0, 0x0063, 0xff, 0x00); // Google accelerator (vfio-pci-bound)
    expect(0x00, 0x06, 0x0, 0x1ae0, 0x0042, 0x02, 0x00); // Google gVNIC
    expect(0x00, 0x07, 0x0, 0x1af4, 0x1005, 0x00, 0xff); // Red Hat Virtio RNG
}

#[test]
fn replay_backend_returns_all_ones_for_absent_devices() {
    let backend = ReplayBackend::from_fixture(FIXTURE);
    // SAFETY: no hardware precondition.
    let val = unsafe { backend.read32(0, 31, 7, 0) }; // a slot never present in the fixture
    assert_eq!(val, 0xFFFF_FFFF, "absent device must read back as vendor 0xFFFF, matching real hardware");
}
