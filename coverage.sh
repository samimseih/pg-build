#!/bin/bash
# pg_coverage.sh - Generate an HTML coverage report for PostgreSQL
# Usage: ./pg_coverage.sh <build_dir> [output_dir]

sudo yum install lcov -y

BUILD_DIR="${1:?Usage: $0 <build_dir> [output_dir]}"
SOURCE_DIR="$(dirname "$BUILD_DIR")"
OUTPUT_DIR="${2:-coverage_report}"
LCOV_FILE="$OUTPUT_DIR/coverage.info"

set -e
mkdir -p "$OUTPUT_DIR"

# Baseline (zero counters)
lcov --capture --initial --directory "$BUILD_DIR" --output-file "$LCOV_FILE.base" \
  --include "$SOURCE_DIR/*"

# Capture actual coverage
lcov --capture --directory "$BUILD_DIR" --output-file "$LCOV_FILE.test" \
  --include "$SOURCE_DIR/*"

# Combine baseline + test data
lcov -a "$LCOV_FILE.base" -a "$LCOV_FILE.test" -o "$LCOV_FILE"

# Remove noise
lcov --remove "$LCOV_FILE" '*/src/test/*' '*/contrib/*' '*/src/interfaces/ecpg/test/*' -o "$LCOV_FILE" --ignore-errors unused

# Generate HTML
genhtml "$LCOV_FILE" --output-directory "$OUTPUT_DIR" --title "PostgreSQL Coverage" --ignore-errors unmapped,unused

echo "Report: $OUTPUT_DIR/index.html"
