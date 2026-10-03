# RunuX RISC-V Target: Banana Pi BPI-F3

## Hardware Specification

| Component | Specification |
|---|---|
| **CPU** | SpacemiT K1 — 8-core RISC-V (X60, RVA22, 1.6GHz) |
| **AI** | 2.0 TOPS RISC-V AI accelerator |
| **RAM** | 4GB LPDDR4 (supports up to 8GB) |
| **Storage** | 16GB eMMC (optional), 4M SPI NOR, 32M SPI NAND |
| **SD Card** | MicroSD slot (256MB+) |
| **Wireless** | Wi-Fi 2.4G/5G, Bluetooth 4.2 |
| **Ethernet** | 2× Gigabit Ethernet (PoE compatible) |
| **HDMI** | 1× Full HDMI 1.4 (up to 1080p@60fps) |
| **Audio** | Speaker, Microphone, Headphones |
| **Camera** | MIPI-CSI, dual camera support |
| **USB** | 4× USB 3.0 Type-A, 1× USB 2.0 Type-C OTG |
| **PCIe** | PCIe 2.1: 2-lane ×2 (M.2 KEY M for NVMe/SATA), 1-lane MINI PCIe |
| **GPIO** | 26-pin header (Raspberry Pi compatible) |
| **Buttons** | Reset, Power, Burn |
| **IR** | IR receiver |
| **Power** | DC input + USB Type-C |
| **Dimensions** | 148 × 100 mm, 200g |
| **OS** | Bianbu Linux, Armbian |

## Target RISC-V ISA Profile

- **Base**: RV64GC (RV64IMAFDC)
- **Profile**: RVA22 (SpacemiT K1)
- **Extensions**: Integer (I), Multiply (M), Atomic (A), Float (F), Double (D), Compressed (C)
- **Privilege**: Machine (M), Supervisor (S), User (U)
- **Virtual Memory**: Sv39 (39-bit virtual, 3-level page table)

## Kernel Subsystem Mapping

### Phase 1 — Boot (QEMU virt, then BPI-F3)

| RunuX Module | RISC-V Component | Status |
|---|---|---|
| `arch_entry` | `_start`, trap vector setup | 🔧 Needs RISC-V stub |
| `arch_setup` | Device tree parsing, HART detection | 🔧 Needs RISC-V stub |
| `arch_cpu` | CSR access (mstatus, sstatus, etc.) | 🔧 Needs RISC-V stub |
| `arch_irq` | PLIC interrupt controller | 🔧 Needs RISC-V stub |
| `arch_pgtable` | Sv39 page table (3-level) | 🔧 Needs RISC-V stub |
| `printk` | UART 16550 serial output | ✅ Portable |

### Phase 2 — Networking (Dual GbE)

| RunuX Module | BPI-F3 Hardware | Status |
|---|---|---|
| `af_inet` / `af_inet6` | Socket layer | ✅ Portable |
| `tcp_ipv4` / `tcp_ipv6` | TCP stack | ✅ Portable |
| `udp` | UDP stack | ✅ Portable |
| `route` | FIB routing table | ✅ Portable |
| `nf_conntrack_core` | Connection tracking | ✅ Portable |
| `nf_nat_core` | NAT | ✅ Portable |
| `netlink` | Netlink sockets | ✅ Portable |
| Ethernet driver | 2× GbE via SpacemiT K1 MAC | 🔧 New driver needed |

### Phase 3 — Storage (NVMe via PCIe)

| RunuX Module | BPI-F3 Hardware | Status |
|---|---|---|
| `driver_pci_core` | PCIe 2.1 bus | ✅ Portable (fixed libc) |
| `driver_pci_access` | Config space read/write | ✅ Portable (fixed libc) |
| `driver_nvme` | NVMe over M.2 KEY M | ✅ Portable |
| `driver_block_core` | Block device layer | ✅ Portable (fixed libc) |
| `ext4_file` / `ext4_super` | Filesystem | ✅ Portable |

### Phase 4 — Full Linux OS Features

| Feature | RunuX Modules | Notes |
|---|---|---|
| Process management | `sched_core`, `sched_fair`, `fork`, `exit` | ✅ Portable |
| Memory management | `page_alloc`, `slab`, `mmap`, `vmalloc` | ✅ Portable |
| User-space syscalls | `arch_syscall` | 🔧 RISC-V `ecall` handler |
| Signals | `signal`, `arch_signal` | 🔧 RISC-V signal frame |
| TTY/Console | `driver_tty_core`, `driver_tty_console` | ✅ Portable (fixed libc) |
| USB 3.0 | xHCI driver | 🔧 New driver needed |
| Wi-Fi | Wireless driver | 🔧 New driver needed |
| AI NPU | 2.0 TOPS accelerator | 🔧 New driver needed |

## Bill of Materials

| Item | Estimated Cost |
|---|---|
| Banana Pi BPI-F3 (4GB) | $70–80 |
| NVMe SSD 128GB (M.2) | $20 |
| MicroSD 64GB (boot) | $8 |
| USB-C PD charger (45W) | $10 |
| Ethernet cables (×2) | $5 |
| Serial debug cable (USB-UART) | $5 |
| **Total** | **~$118–128** |
