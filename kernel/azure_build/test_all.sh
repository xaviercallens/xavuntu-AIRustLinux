#!/bin/bash
#
# Test All Rust Kernel Modules
# FFI compatibility, safety, and correctness testing
#

set -euo pipefail

WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
TEST_LOG="${TEST_LOG:-/workspace/test_results.json}"
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           RUST KERNEL MODULE TEST SYSTEM                      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cd "$WORKSPACE_ROOT"

# Initialize results
cat > "$TEST_LOG" << 'EOF'
{
  "test_start": "",
  "test_end": "",
  "total_modules": 0,
  "passed_tests": 0,
  "failed_tests": 0,
  "skipped_tests": 0,
  "test_time_seconds": 0,
  "modules": []
}
EOF

TEST_START=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg start "$TEST_START" '.test_start = $start' "$TEST_LOG" > "$TEST_LOG.tmp" && mv "$TEST_LOG.tmp" "$TEST_LOG"

TOTAL_MODULES=$(find crates -maxdepth 1 -type d | tail -n +2 | wc -l)
jq --arg total "$TOTAL_MODULES" '.total_modules = ($total | tonumber)' "$TEST_LOG" > "$TEST_LOG.tmp" && mv "$TEST_LOG.tmp" "$TEST_LOG"

echo "Testing $TOTAL_MODULES modules"
echo ""

PASSED=0
FAILED=0
SKIPPED=0

test_module() {
    local module_name=$1
    local module_path="crates/$module_name"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Testing: $module_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local start_time=$(date +%s)
    local output_file="/tmp/test_${module_name}.log"

    # Run cargo test
    if cargo test --package "$module_name" 2>&1 | tee "$output_file"; then
        local test_count=$(grep -E "test result: (ok|FAILED)" "$output_file" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo "0")

        if [ "$test_count" -gt 0 ]; then
            local status="passed"
            PASSED=$((PASSED + 1))
            echo "✅ $module_name: $test_count tests passed"
        else
            local status="skipped"
            SKIPPED=$((SKIPPED + 1))
            echo "⚠️  $module_name: No tests found"
        fi
    else
        local status="failed"
        local test_count=0
        FAILED=$((FAILED + 1))
        echo "❌ $module_name: Tests failed"
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Run clippy for linting
    local clippy_warnings=0
    if cargo clippy --package "$module_name" 2>&1 | tee "${output_file}.clippy"; then
        clippy_warnings=$(grep -c "warning:" "${output_file}.clippy" || echo "0")
    fi

    # Check FFI compatibility
    local ffi_check="passed"
    if ! grep -q "#\[repr(C)\]" "$module_path/src/lib.rs"; then
        ffi_check="missing_repr_c"
    fi
    if ! grep -q "extern \"C\"" "$module_path/src/lib.rs"; then
        ffi_check="missing_extern_c"
    fi

    local module_result=$(jq -n \
        --arg name "$module_name" \
        --arg status "$status" \
        --arg duration "$duration" \
        --arg tests "$test_count" \
        --arg clippy "$clippy_warnings" \
        --arg ffi "$ffi_check" \
        '{
            name: $name,
            status: $status,
            test_time_seconds: ($duration | tonumber),
            tests_passed: ($tests | tonumber),
            clippy_warnings: ($clippy | tonumber),
            ffi_compatibility: $ffi
        }')

    jq --argjson module "$module_result" '.modules += [$module]' "$TEST_LOG" > "$TEST_LOG.tmp" && mv "$TEST_LOG.tmp" "$TEST_LOG"

    rm -f "$output_file" "${output_file}.clippy"
    echo ""
}

export -f test_module
export PASSED FAILED SKIPPED TEST_LOG

# Test modules in parallel
find crates -maxdepth 1 -type d | tail -n +2 | xargs -I {} basename {} | \
    xargs -P "$PARALLEL_JOBS" -I {} bash -c 'test_module "$@"' _ {}

# Update final statistics
TEST_END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TEST_TIME=$(($(date -d "$TEST_END" +%s) - $(date -d "$TEST_START" +%s)))

jq --arg end "$TEST_END" \
   --arg time "$TEST_TIME" \
   --arg passed "$PASSED" \
   --arg failed "$FAILED" \
   --arg skipped "$SKIPPED" \
   '.test_end = $end |
    .test_time_seconds = ($time | tonumber) |
    .passed_tests = ($passed | tonumber) |
    .failed_tests = ($failed | tonumber) |
    .skipped_tests = ($skipped | tonumber)' \
   "$TEST_LOG" > "$TEST_LOG.tmp" && mv "$TEST_LOG.tmp" "$TEST_LOG"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    TEST SUMMARY                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Total modules:  $TOTAL_MODULES"
echo "Tests passed:   $PASSED"
echo "Tests failed:   $FAILED"
echo "Tests skipped:  $SKIPPED"
echo "Test time:      ${TEST_TIME}s"
echo ""
echo "Detailed results: $TEST_LOG"
echo ""

if [ "$FAILED" -gt 0 ]; then
    echo "⚠️  Some tests failed. Check $TEST_LOG for details."
    exit 1
else
    echo "✅ All tests passed!"
    exit 0
fi
