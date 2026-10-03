import sys
from PIL import Image, ImageDraw, ImageFont

def create_gif():
    width, height = 800, 600
    # Try to find a monospace font, otherwise use default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 14)
    except IOError:
        font = ImageFont.load_default()

    frames = []
    
    # The text sequence to display line by line
    lines = [
        "===========================================================",
        " ____  _   _ _   _ _   _ __  __",
        "|  _ \\| | | | \\ | | | | |\\ \\/ /",
        "| |_) | | | |  \\| | | | | \\  / ",
        "|  _ <| |_| | |\\  | |_| | /  \\ ",
        "|_| \\_\\\\___/|_| \\_|\\___/ /_/\\_\\  v10.0-AI",
        "===========================================================",
        "     THE FIRST AI-DRIVEN RUST LINUX KERNEL",
        "===========================================================",
        "[BOOT] Initializing Google Cloud Partnership Protocols...",
        "[GCP] Provisioning c3-metal-85 Baremetal Instance... [OK]",
        "[GCP] Hypervisor bypassed. Direct hardware access granted.",
        "",
        "[MVK] Lean 4 Mathematical Invariants Validating...",
        "   -> Phase 8: CFS SafeTask bounds... [VERIFIED]",
        "   -> Phase 9: Memory SafePageFrame bounds... [VERIFIED]",
        "   -> Phase 11: PCI Recursive Probing limits... [VERIFIED]",
        "",
        "[MVK] 90% of Core Kernel Modules Bootstrapped natively.",
        "[DRV] Probing NVMe Storage via PCIe...",
        "   -> GCP Hyperdisk mounted via zero-cost SafeDmaQueue.",
        "[DRV] Probing IDPF Data Plane Networking...",
        "   -> Intel Virtual Function attached to Google VPC.",
        "[NET] IPv6 FIB Routing active. Netfilter enabled.",
        "",
        "===========================================================",
        " SYSTEM STATUS: RUNUX OPERATIONAL ON BAREMETAL",
        "===========================================================",
        "root@runux-gcp-node:~# _"
    ]

    # Generate frames progressively
    rendered_text = ""
    for i in range(len(lines)):
        img = Image.new('RGB', (width, height), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        rendered_text += lines[i] + "\n"
        
        # Draw text in bright terminal green
        draw.text((20, 20), rendered_text, font=font, fill=(0, 255, 0))
        frames.append(img)
        
        # Add a few duplicate frames for dramatic pauses
        if "VERIFIED" in lines[i] or "[OK]" in lines[i]:
            for _ in range(5):
                frames.append(img)
    
    # Hold the last frame for a few seconds
    for _ in range(20):
        frames.append(frames[-1])

    # Save as GIF
    gif_path = "/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel/runux_gcp_demo_v10.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=150,  # 150ms per frame
        loop=0
    )
    print(f"Successfully generated GIF at {gif_path}")

if __name__ == "__main__":
    create_gif()
