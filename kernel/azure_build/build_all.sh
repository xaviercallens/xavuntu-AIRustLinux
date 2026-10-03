#!/bin/bash
#
# Build All Rust Kernel Modules
# Azure-compatible build script with comprehensive error handling
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
BUILD_LOG="${BUILD_LOG:-/workspace/build_results.json}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           RUST KERNEL MODULE BUILD SYSTEM                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Workspace: $WORKSPACE_ROOT"
echo "Parallel jobs: $PARALLEL_JOBS"
echo "Build log: $BUILD_LOG"
echo ""

cd "$WORKSPACE_ROOT"

# Initialize results
cat > "$BUILD_LOG" << 'EOF'
{
  "build_start": "",
  "build_end": "",
  "total_modules": 0,
  "successful_builds": 0,
  "failed_builds": 0,
  "warnings": 0,
  "build_time_seconds": 0,
  "modules": []
}
EOF

BUILD_START=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg start "$BUILD_START" '.build_start = $start' "$BUILD_LOG" > "$BUILD_LOG.tmp" && mv "$BUILD_LOG.tmp" "$BUILD_LOG"

# Count modules
TOTAL_MODULES=$(find crates -maxdepth 1 -type d | tail -n +2 | wc -l)
jq --arg total "$TOTAL_MODULES" '.total_modules = ($total | tonumber)' "$BUILD_LOG" > "$BUILD_LOG.tmp" && mv "$BUILD_LOG.tmp" "$BUILD_LOG"

echo "Found $TOTAL_MODULES modules to build"
echo ""

# Build each module
SUCCESSFUL=0
FAILED=0
WARNINGS=0

build_module() {
    local module_name=$1
    local module_path="crates/$module_name"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Building: $module_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local start_time=$(date +%s)
    local output_file="/tmp/build_${module_name}.log"

    # Build the module
    if cargo build --package "$module_name" --release 2>&1 | tee "$output_file"; then
        local status="success"
        SUCCESSFUL=$((SUCCESSFUL + 1))
        echo "✅ $module_name: BUILD SUCCESS"
    else
        local status="failed"
        FAILED=$((FAILED + 1))
        echo "❌ $module_name: BUILD FAILED"
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Count warnings
    local warning_count=$(grep -c "warning:" "$output_file" || echo "0")
    WARNINGS=$((WARNINGS + warning_count))

    # Extract error messages
    local errors=$(grep "error\[E[0-9]*\]:" "$output_file" | head -5 | jq -R -s 'split("\n") | map(select(length > 0))' || echo '[]')

    # Add to results
    local module_result=$(jq -n \
        --arg name "$module_name" \
        --arg status "$status" \
        --arg duration "$duration" \
        --arg warnings "$warning_count" \
        --argjson errors "$errors" \
        '{
            name: $name,
            status: $status,
            build_time_seconds: ($duration | tonumber),
            warnings: ($warnings | tonumber),
            errors: $errors
        }')

    jq --argjson module "$module_result" '.modules += [$module]' "$BUILD_LOG" > "$BUILD_LOG.tmp" && mv "$BUILD_LOG.tmp" "$BUILD_LOG"

    rm -f "$output_file"
    echo ""
}

export -f build_module
export SUCCESSFUL FAILED WARNINGS BUILD_LOG

# Build modules in parallel
find crates -maxdepth 1 -type d | tail -n +2 | xargs -I {} basename {} | \
    xargs -P "$PARALLEL_JOBS" -I {} bash -c 'build_module "$@"' _ {}

# Update final statistics
BUILD_END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_TIME=$(($(date -d "$BUILD_END" +%s) - $(date -d "$BUILD_START" +%s)))

jq --arg end "$BUILD_END" \
   --arg time "$BUILD_TIME" \
   --arg success "$SUCCESSFUL" \
   --arg failed "$FAILED" \
   --arg warnings "$WARNINGS" \
   '.build_end = $end |
    .build_time_seconds = ($time | tonumber) |
    .successful_builds = ($success | tonumber) |
    .failed_builds = ($failed | tonumber) |
    .warnings = ($warnings | tonumber)' \
   "$BUILD_LOG" > "$BUILD_LOG.tmp" && mv "$BUILD_LOG.tmp" "$BUILD_LOG"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    BUILD SUMMARY                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Total modules:     $TOTAL_MODULES"
echo "Successful builds: $SUCCESSFUL"
echo "Failed builds:     $FAILED"
echo "Total warnings:    $WARNINGS"
echo "Build time:        ${BUILD_TIME}s"
echo "Success rate:      $(( SUCCESSFUL * 100 / TOTAL_MODULES ))%"
echo ""
echo "Detailed results: $BUILD_LOG"
echo ""

if [ "$FAILED" -gt 0 ]; then
    echo "⚠️  Some modules failed to build. Check $BUILD_LOG for details."
    exit 1
else
    echo "✅ All modules built successfully!"
    exit 0
fi
