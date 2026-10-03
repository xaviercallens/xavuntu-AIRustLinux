#!/bin/bash

# Overnight Batch Monitor for Rust-Linux-Mini-Kernel
# Runs every 20 minutes: pulls updates, compiles, and generates a report.

REPORT_FILE="NIGHTLY_PROGRESS_REPORT.md"
WORKSPACE_DIR="/Volumes/MacCleanerStorage/xdev/xavux/rust-linux-mini-kernel"
INTERVAL=1200 # 20 minutes

echo "Starting overnight monitoring batch..."
echo "Monitoring interval: 20 minutes. Outputting to $REPORT_FILE."

cd "$WORKSPACE_DIR" || exit 1

# Initialize report
echo "# Overnight Compilation & Quality Report" > $REPORT_FILE
echo "**Started at:** $(date)" >> $REPORT_FILE
echo "" >> $REPORT_FILE

while true; do
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    echo "---" >> $REPORT_FILE
    echo "## Run at $TIMESTAMP" >> $REPORT_FILE
    
    # 1. Pull latest updates
    echo "Pulling latest updates..."
    git fetch origin master
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/master)
    
    if [ "$LOCAL" != "$REMOTE" ]; then
        git pull origin master
        echo "- **Git Status**: Pulled new updates from remote." >> $REPORT_FILE
    else
        echo "- **Git Status**: No new commits." >> $REPORT_FILE
    fi
    
    # 2. Run Cargo Check
    echo "Running compilation check..."
    cargo check --workspace --message-format=json > cargo_out.json 2>/dev/null
    cargo check --keep-going --workspace > cargo_stderr.txt 2>&1
    
    # Analyze errors
    TOTAL_ERRORS=$(grep -c "^error" cargo_stderr.txt)
    MISSING_TYPES=$(grep -c "cannot find type" cargo_stderr.txt)
    MISSING_MACROS=$(grep -c "cannot find macro" cargo_stderr.txt)
    NO_STD_PANICS=$(grep -c "panic_handler" cargo_stderr.txt)
    DUPLICATES=$(grep -c "already declared\|defined multiple times" cargo_stderr.txt)
    
    echo "### Compilation Statistics" >> $REPORT_FILE
    echo "- **Total Compiler Errors**: $TOTAL_ERRORS" >> $REPORT_FILE
    echo "- Missing Types/Values: $MISSING_TYPES" >> $REPORT_FILE
    echo "- Missing Macros (vec! etc.): $MISSING_MACROS" >> $REPORT_FILE
    echo "- No_std Panic Handler Missing: $NO_STD_PANICS" >> $REPORT_FILE
    echo "- Duplicate Definitions: $DUPLICATES" >> $REPORT_FILE
    
    # 3. Automated Analysis & Proposed Improvements
    echo "### Automated Analysis & Proposed Improvements" >> $REPORT_FILE
    if [ "$TOTAL_ERRORS" -eq 0 ]; then
        echo "✅ **SUCCESS:** The workspace is compiling cleanly! No further improvements needed." >> $REPORT_FILE
    else
        echo "⚠️ **ISSUES DETECTED. Proposed Fixes for the Codex Pipeline:**" >> $REPORT_FILE
        
        if [ "$MISSING_TYPES" -gt 0 ]; then
            echo "- **Type Resolution:** The LLM is failing to map C types to Rust. *Improvement: Update the Codex prompt to explicitly import \`libc::{c_int, c_char, size_t}\` in every module.*" >> $REPORT_FILE
        fi
        
        if [ "$MISSING_MACROS" -gt 0 ]; then
            echo "- **Macro Usage:** The LLM is trying to use \`vec!\` in a \`#![no_std]\` environment. *Improvement: Add a rule to the Codex prompt to prohibit heap allocations and use fixed arrays or custom allocators.*" >> $REPORT_FILE
        fi
        
        if [ "$DUPLICATES" -gt 0 ]; then
            echo "- **Namespace Conflicts:** The AI is repeatedly defining identical structs. *Improvement: Have the pipeline check for global definitions and import them from a shared \`core\` crate rather than duplicating them.*" >> $REPORT_FILE
        fi
        
        if [ "$NO_STD_PANICS" -gt 0 ]; then
            echo "- **Panic Handlers:** *Improvement: Ensure a central \`#[panic_handler]\` is provided in the root lib and \`panic = \"abort\"\` is in Cargo.toml profiles.*" >> $REPORT_FILE
        fi
    fi
    
    echo "Waiting 20 minutes for the next check..."
    sleep $INTERVAL
done
