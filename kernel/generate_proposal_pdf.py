from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def create_pdf():
    doc = SimpleDocTemplate("paper/COLLABORATION_PROPOSAL.pdf", pagesize=letter,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        spaceAfter=14,
        alignment=1 # Center
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Heading2'],
        fontName='Helvetica-Oblique',
        fontSize=14,
        spaceAfter=20,
        alignment=1
    )
    
    heading_style = styles['Heading2']
    body_style = styles['BodyText']
    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['BodyText'],
        fontName='Courier',
        fontSize=10,
        leftIndent=20,
        textColor=colors.darkblue
    )

    story = []

    # Title
    story.append(Paragraph("Minimum Viable Kernel (MVK)", title_style))
    story.append(Paragraph("Collaboration & Reproducibility Proposal", subtitle_style))
    
    # Intro
    story.append(Paragraph("The Minimum Viable Kernel (MVK) project has successfully demonstrated that it is possible to mathematically eliminate spatial and temporal memory vulnerabilities in a bare-metal architecture using Rust and Lean 4 formal verification. As we prepare for the <b>v9.0 Security Hardening Release</b>, we are officially opening the repository for community collaboration, peer review, and academic reproduction.", body_style))
    story.append(Spacer(1, 12))

    # Section 1
    story.append(Paragraph("<b>1. How to Reproduce the MVK Empirical Results</b>", heading_style))
    story.append(Paragraph("We strongly encourage independent security researchers and systems engineers to reproduce our benchmarks and formal verification proofs. All infrastructure relies on open-source toolchains.", body_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>Prerequisites:</b><br/>• Rust Toolchain: nightly-2026-05-15 (required for no_std and Miri).<br/>• Lean 4: v4.29.1 (for formal verification proofs).<br/>• Hardware: An x86_64 virtualization environment (QEMU) or a bare-metal instance.", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("<b>Reproduction Steps:</b>", body_style))
    story.append(Paragraph("1. Clone the Repository:", body_style))
    story.append(Paragraph("git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git", code_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("2. Verify the Lean 4 Mathematical Proofs:", body_style))
    story.append(Paragraph("cd specs/lean4<br/>lake build", code_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("3. Run the Dynamic Undefined Behavior (UB) Interpreter:", body_style))
    story.append(Paragraph("cargo miri test", code_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("4. Execute the Bare-Metal Kernel in QEMU:", body_style))
    story.append(Paragraph("cargo run --release", code_style))
    story.append(Spacer(1, 12))

    # Section 2
    story.append(Paragraph("<b>2. Proposed Improvements & Next Steps (v9.0)</b>", heading_style))
    story.append(Paragraph("The foundation built on Rust's Ownership Model provides absolute temporal and spatial safety. However, the architectural design must evolve to mitigate logical flaws and hardware-level exploitation.", body_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>A. Hardware-Boundary Fuzzing (libFuzzer)</b><br/>We need contributors to write rigorous cargo-fuzz targets to stress-test the entry and exit points of unsafe abstractions.", body_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>B. Microkernel Privilege De-escalation</b><br/>Refactor device drivers to execute in Ring-3 user space. We invite OS architects to help design a high-throughput, zero-copy IPC mechanism utilizing our new RcuPointer.", body_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>C. Advanced Exploit Mitigations</b><br/>Implement Kernel Address Space Layout Randomization (KASLR) and Kernel Control-Flow Integrity (kCFI).", body_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>D. Extending Lean 4 Formal Verification</b><br/>We need mathematical logicians to help write Lean 4 algebraic models for the Virtual File System (VFS) and the asynchronous packet ingress pathways.", body_style))
    story.append(Spacer(1, 12))

    # Section 3
    story.append(Paragraph("<b>3. How to Contribute</b>", heading_style))
    story.append(Paragraph("1. Review the open issues labeled <i>good first issue</i> or <i>security</i>.<br/>2. Fork the repository and create a feature branch.<br/>3. Ensure your branch passes the GitHub Actions CI/CD pipeline (Miri and cargo-audit).<br/>4. Submit a Pull Request.", body_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<i>We look forward to collaborating with you to build the most secure operating system in the world.</i>", body_style))

    doc.build(story)

if __name__ == "__main__":
    create_pdf()
    print("PDF generated successfully: paper/COLLABORATION_PROPOSAL.pdf")
