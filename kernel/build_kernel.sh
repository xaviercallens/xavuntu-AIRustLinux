#!/bin/bash
set -e

echo "=== Rust Linux Mini Kernel Build System ==="
echo "Building Phase 1: Boot to Panic"

ARCH="x86_64"
TARGET="x86_64-unknown-none"
BUILD_DIR="build"
KERNEL_NAME="mvk-kernel"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Cleaning...${NC}"
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

echo -e "${YELLOW}Building modules...${NC}"
MODULES=("kernel_types" "printk" "arch_setup" "init_main")
for module in "${MODULES[@]}"; do
    echo -e "  ${GREEN}$module${NC}"
    cargo build --release -p $module --target=$TARGET 2>&1 | grep -E "error|warning|Compiling|Finished" || true
done

echo -e "${YELLOW}Collecting objects...${NC}"
mkdir -p $BUILD_DIR/objects
for module in "${MODULES[@]}"; do
    RLIB=$(find target/$TARGET/release/deps -name "lib${module}-*.rlib" | head -1)
    [ -f "$RLIB" ] && cp "$RLIB" "$BUILD_DIR/objects/lib${module}.rlib" || echo -e "  ${RED}Missing $module${NC}"
done

echo -e "${YELLOW}Assembling...${NC}"
nasm -f elf64 arch/x86_64/boot/entry.asm -o $BUILD_DIR/entry.o

echo -e "${YELLOW}Extracting objects...${NC}"
cd $BUILD_DIR/objects
for rlib in *.rlib; do ar x $rlib; done
cd ../..

echo -e "${YELLOW}Linking...${NC}"
x86_64-elf-ld -n -T arch/x86_64/linker.ld -o $BUILD_DIR/$KERNEL_NAME.elf $BUILD_DIR/entry.o $BUILD_DIR/objects/*.o 2>/dev/null || \
  rust-lld -flavor gnu -n -T arch/x86_64/linker.ld -o $BUILD_DIR/$KERNEL_NAME.elf $BUILD_DIR/entry.o $BUILD_DIR/objects/*.o 2>/dev/null || \
  ld -m elf_x86_64 -n -T arch/x86_64/linker.ld -o $BUILD_DIR/$KERNEL_NAME.elf $BUILD_DIR/entry.o $BUILD_DIR/objects/*.o

if [ -f "$BUILD_DIR/$KERNEL_NAME.elf" ]; then
    SIZE=$(du -h $BUILD_DIR/$KERNEL_NAME.elf | cut -f1)
    echo -e "${GREEN}✓ Build complete${NC} - Size: $SIZE"
    echo "Test: qemu-system-x86_64 -kernel $BUILD_DIR/$KERNEL_NAME.elf -serial stdio"
else
    echo -e "${RED}✗ Linking failed${NC}"
    exit 1
fi
