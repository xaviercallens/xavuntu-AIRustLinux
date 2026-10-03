# Kernel Integration Guide

This guide explains how to integrate and validate the compiled Rust modules from `rust-linux-mini-kernel` within an actual Linux kernel environment.

## 1. Prerequisites
- **Linux Kernel Source**: You will need a compatible version of the Linux kernel source tree (target: 5.10 LTS).
- **Rust Toolchain**: `rustc`, `cargo`, and the `rust-src` component.
- **QEMU**: For safely testing the compiled kernel.
- **Clang/LLVM**: Required by the Rust-for-Linux framework for bindgen.

## 2. Compilation and Preparation

Before integrating, ensure that the modules you want to test compile successfully as static libraries (`.a`) or object files (`.o`).
The project is built around `cargo build --release`. 

By default, the modules are compiled as standard Rust libraries (`rlib`), but for kernel integration they must be linked appropriately. The `azure_build` pipeline produces compatible object files if correctly configured.

## 3. Integrating with a Custom Linux Kernel (Using QEMU)

### Step 3.1: Download and Extract Kernel Source
Download the Linux 5.10 LTS source code:
```bash
wget https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-5.10.210.tar.xz
tar -xf linux-5.10.210.tar.xz
cd linux-5.10.210
```

### Step 3.2: Configure the Kernel
Generate a minimal config for testing (e.g., `make defconfig` or `make kvm_guest.config`), and ensure module support is enabled (`CONFIG_MODULES=y`).

### Step 3.3: Replace/Add the Rust Module
If you are testing the `tunnel6` module, you must replace or disable the native C implementation in the kernel source (`net/ipv6/tunnel6.c`) to avoid symbol collisions.

Link the compiled Rust object file (`libtunnel6.a` or similar) into the kernel's Kbuild system. Create a `Kbuild` or `Makefile` entry that instructs the kernel build system to link your compiled Rust artifact.

Example `net/ipv6/Makefile` modification:
```makefile
# Disable the C version
# obj-$(CONFIG_IPV6_TUNNEL) += tunnel6.o

# Point to the Rust implementation
obj-$(CONFIG_IPV6_TUNNEL) += /path/to/rust-linux-mini-kernel/target/release/libtunnel6.a
```
*(Note: Real-world integration via the Rust-for-Linux Kbuild integration is more complex, but this serves as a conceptual starting point.)*

### Step 3.4: Build the Kernel
```bash
make -j$(nproc) bzImage
```

### Step 3.5: Run in QEMU
Boot your compiled kernel using QEMU to test for panics or crashes during initialization:
```bash
qemu-system-x86_64 -kernel arch/x86/boot/bzImage -append "console=ttyS0" -nographic
```

## 4. Validating the Modules

Once the kernel boots, validate the module functionality:
- **dmesg**: Check the kernel logs using `dmesg` to see if your Rust module's initialization function executed without errors.
- **Networking Tests**: If testing a network module (e.g., `af_inet`), use `ping`, `ip link`, or `nc` inside the VM to trigger the code paths handled by your Rust implementation.

## 5. Debugging
If a Rust module panics, the kernel will oops or panic (since we use `panic="abort"`). 
- To trace errors, ensure you compile with debug symbols (`opt-level = 1` or `debug = true` in `Cargo.toml`).
- You can attach `gdb` to QEMU:
  ```bash
  qemu-system-x86_64 -s -S -kernel arch/x86/boot/bzImage
  ```
  Then in another terminal:
  ```bash
  gdb vmlinux
  (gdb) target remote localhost:1234
  (gdb) continue
  ```

## 6. Call for Contributions
Kernel integration is the final, most crucial step of this project. If you successfully boot and test one of these modules in a real kernel, please open a PR updating this guide with your specific Kbuild modifications and test scripts!
