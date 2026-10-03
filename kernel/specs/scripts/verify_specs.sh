#!/bin/bash
# Verify Lean 4 specifications for MVK v9.3.1
# Usage: ./verify_specs.sh [--verbose]

set -e

VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

echo "========================================"
echo "  MVK v9.3.1 Formal Verification"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Lean 4 is installed
if ! command -v lean &> /dev/null; then
    log_error "Lean 4 is not installed!"
    echo ""
    echo "Install Lean 4 using elan:"
    echo "  curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh"
    echo "  source ~/.elan/env"
    exit 1
fi

log_info "Lean version: $(lean --version)"
echo ""

# Navigate to specifications directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPECS_DIR="$(dirname "$SCRIPT_DIR")/lean4"

if [ ! -d "$SPECS_DIR" ]; then
    log_error "Specifications directory not found: $SPECS_DIR"
    exit 1
fi

cd "$SPECS_DIR"
log_info "Working directory: $(pwd)"
echo ""

# Step 1: Build specifications
log_info "Step 1/5: Building Lean specifications..."
if $VERBOSE; then
    lake build
else
    lake build > /dev/null 2>&1
fi

if [ $? -eq 0 ]; then
    log_success "Build successful"
else
    log_error "Build failed"
    exit 1
fi
echo ""

# Step 2: Type check specifications
log_info "Step 2/5: Type checking specifications..."
if lake env lean MVK.lean > /dev/null 2>&1; then
    log_success "Type checking passed"
else
    log_error "Type checking failed"
    exit 1
fi
echo ""

# Step 3: Check individual specification files
log_info "Step 3/5: Checking individual modules..."

# Auto-discovered from the tree rather than hand-maintained: a hardcoded
# list here previously missed 16 existing .lean files (Phase5-13,
# QuantumLTN, etc.), which silently undercounted total sorry/axiom stats.
# See docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md WS0 item 3.
mapfile -t MODULES < <(cd "$SPECS_DIR" && find MVK -name '*.lean' | sort)

# Modules that are declared "complete" (must have zero sorry). Verified by
# grep against docs/roadmap/metrics/metrics.baseline.json at commit
# 041622e. Adding a file here that still has sorry, or letting a listed
# file regress, fails the build -- this is the "anti-weakening" gate for
# the parts of the spec we already claim are done. Everything else is
# tracked (via metrics.py) but not yet gated per-file.
COMPLETE_MODULES=(
    "MVK/RunuxDefenses.lean"
    "MVK/Phase13/GpuCompute.lean"
    "MVK/Phase9/Memory.lean"
    "MVK/Phase12/GCP_Drivers.lean"
    "MVK/Phase4/UDP.lean"
    "MVK/Phase4/ICMP.lean"
    "MVK/Phase3/ConntrackTCP.lean"
    "MVK/Phase4/IPv4IPv6/Tcpv6.lean"
    "MVK/Phase11/Hardware.lean"
    "MVK/Phase8/Scheduling.lean"
    "MVK/Phase7/Sockets.lean"
    "MVK/Phase7/Netfilter.lean"
    "MVK/Phase6/Routing.lean"
    "MVK/QuantumLTN/PolarQuant.lean"
    "MVK/QuantumLTN/FuzzyLogic.lean"
    "MVK/Phase2/Compatibility.lean"
    "MVK/Audit/SpecDefects.lean"
)

PASSED=0
FAILED=0

for module in "${MODULES[@]}"; do
    if [ ! -f "$module" ]; then
        log_warning "Module not found: $module"
        continue
    fi

    echo -n "  Checking $module... "
    if lake env lean "$module" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗${NC}"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
log_info "Results: $PASSED passed, $FAILED failed"
echo ""

# Step 4: Count proof obligations
log_info "Step 4/5: Analyzing proof obligations..."

REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

count_sorry() {
    local file=$1
    # Delegate to scripts/lean_tools.py (the counter metrics.py uses) so the
    # two can never disagree. grep-based counting false-positived twice:
    # on a `--` comment in GpuCompute.lean and on a `/- -/` docstring in
    # Audit/SpecDefects.lean.
    python3 - "$file" "$REPO_ROOT/scripts" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from lean_tools import analyze_file
print(analyze_file(Path(sys.argv[1])).sorry)
PY
}

count_axiom() {
    local file=$1
    grep "^axiom" "$file" 2>/dev/null | wc -l | tr -d ' '
}

count_theorem() {
    local file=$1
    grep "^theorem" "$file" 2>/dev/null | wc -l | tr -d ' '
}

TOTAL_SORRY=0
TOTAL_AXIOMS=0
TOTAL_THEOREMS=0
COMPLETE_REGRESSIONS=()

echo ""
echo "Proof Status by Module:"
echo "────────────────────────────────────────"

for module in "${MODULES[@]}"; do
    if [ ! -f "$module" ]; then
        continue
    fi

    MODULE_NAME=$(basename "$module" .lean)
    SORRY_COUNT=$(count_sorry "$module")
    AXIOM_COUNT=$(count_axiom "$module")
    THEOREM_COUNT=$(count_theorem "$module")

    TOTAL_SORRY=$((TOTAL_SORRY + SORRY_COUNT))
    TOTAL_AXIOMS=$((TOTAL_AXIOMS + AXIOM_COUNT))
    TOTAL_THEOREMS=$((TOTAL_THEOREMS + THEOREM_COUNT))

    printf "  %-15s Theorems: %2d  Axioms: %2d  Sorry: %2d\n" \
        "$MODULE_NAME" "$THEOREM_COUNT" "$AXIOM_COUNT" "$SORRY_COUNT"

    for complete_module in "${COMPLETE_MODULES[@]}"; do
        if [ "$module" == "$complete_module" ] && [ "$SORRY_COUNT" -gt 0 ]; then
            COMPLETE_REGRESSIONS+=("$module ($SORRY_COUNT sorry)")
        fi
    done
done

echo "────────────────────────────────────────"
printf "  %-15s Theorems: %2d  Axioms: %2d  Sorry: %2d\n" \
    "TOTAL" "$TOTAL_THEOREMS" "$TOTAL_AXIOMS" "$TOTAL_SORRY"
echo ""

# Calculate completion percentage
TOTAL_OBLIGATIONS=$((TOTAL_THEOREMS + TOTAL_AXIOMS))
COMPLETED=$((TOTAL_THEOREMS - TOTAL_SORRY))
PERCENTAGE=0
if [ $TOTAL_OBLIGATIONS -gt 0 ]; then
    PERCENTAGE=$((COMPLETED * 100 / TOTAL_OBLIGATIONS))
fi

log_info "Proof completion: $PERCENTAGE% ($COMPLETED/$TOTAL_OBLIGATIONS)"
echo ""

# Step 5: Generate proof obligations report
log_info "Step 5/5: Generating reports..."

REPORT_FILE="$SPECS_DIR/../PROOF_STATUS_REPORT.md"

cat > "$REPORT_FILE" << EOF
# MVK v9.3.1 Proof Status Report

**Generated:** $(date)
**Lean Version:** $(lean --version)

## Summary

- **Total Theorems:** $TOTAL_THEOREMS
- **Total Axioms:** $TOTAL_AXIOMS
- **Total Obligations:** $TOTAL_OBLIGATIONS
- **Completed Proofs:** $COMPLETED
- **Incomplete (sorry):** $TOTAL_SORRY
- **Completion:** $PERCENTAGE%

## Module Breakdown

| Module | Theorems | Axioms | Sorry | Status |
|--------|----------|--------|-------|--------|
EOF

for module in "${MODULES[@]}"; do
    if [ ! -f "$module" ]; then
        continue
    fi

    MODULE_NAME=$(basename "$module" .lean)
    SORRY_COUNT=$(count_sorry "$module")
    AXIOM_COUNT=$(count_axiom "$module")
    THEOREM_COUNT=$(count_theorem "$module")

    if [ $SORRY_COUNT -eq 0 ]; then
        STATUS="✅ Complete"
    else
        STATUS="⏳ In Progress"
    fi

    echo "| $MODULE_NAME | $THEOREM_COUNT | $AXIOM_COUNT | $SORRY_COUNT | $STATUS |" >> "$REPORT_FILE"
done

cat >> "$REPORT_FILE" << EOF

## Next Steps

1. Complete proofs marked with \`sorry\`
2. Convert axioms to proven theorems where possible
3. Add more specifications for Phase 2 modules

## Files

- Specifications: \`specs/lean4/\`
- Proof obligations: \`specs/PROOF_OBLIGATIONS.md\`
- Full documentation: \`specs/SPECIFICATIONS.md\`

---

*This report is automatically generated by \`verify_specs.sh\`*
EOF

log_success "Report generated: $REPORT_FILE"
echo ""

# Final summary
echo "========================================"
echo "  Verification Complete"
echo "========================================"
echo ""
log_info "Specifications are type-correct"
log_info "Proof completion: $PERCENTAGE%"

if [ $TOTAL_SORRY -gt 0 ]; then
    log_warning "$TOTAL_SORRY proof(s) remaining (marked 'sorry')"
fi

if [ $FAILED -gt 0 ]; then
    log_warning "$FAILED module(s) failed type checking"
    exit 1
fi

if [ ${#COMPLETE_REGRESSIONS[@]} -gt 0 ]; then
    log_error "Module(s) listed as COMPLETE regressed to containing 'sorry':"
    for r in "${COMPLETE_REGRESSIONS[@]}"; do
        echo "    - $r"
    done
    log_error "Either finish the proof, or remove the module from COMPLETE_MODULES in this script (and from the completion claim in docs/roadmap)."
    exit 1
fi

log_success "All checks passed!"
log_info "$TOTAL_SORRY total 'sorry' remain outside the COMPLETE_MODULES set -- see scripts/metrics.py for the tracked count and docs/roadmap/RUNUX_V12_VERIFIED_CORE_PLAN.md WS1 for the burn-down plan."
exit 0
