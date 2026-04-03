#!/bin/bash
# pg_coverage.sh - Generate an HTML coverage report for PostgreSQL
# Usage: ./pg_coverage.sh <build_dir> [output_dir] [source_file_pattern]
# source_file_pattern: optional glob to filter to a specific file, e.g. 'src/backend/lib/dshash.c'

sudo yum install lcov -y

BUILD_DIR="${1:?Usage: $0 <build_dir> [output_dir]}"
SOURCE_DIR="$(dirname "$BUILD_DIR")"
OUTPUT_DIR="${2:-coverage_report}"
SOURCE_FILE="${3:-}"
LCOV_FILE="$OUTPUT_DIR/coverage.info"

# Determine include pattern for lcov capture
if [ -n "$SOURCE_FILE" ]; then
  [[ "$SOURCE_FILE" != /* && "$SOURCE_FILE" != *"*"* ]] && SOURCE_FILE="*/$SOURCE_FILE"
  INCLUDE_PATTERN="$SOURCE_FILE"
else
  INCLUDE_PATTERN="$SOURCE_DIR/*"
fi

set -e
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Baseline (zero counters)
lcov --capture --initial --directory "$BUILD_DIR" --output-file "$LCOV_FILE.base" \
  --include "$INCLUDE_PATTERN"

# Capture actual coverage
lcov --capture --directory "$BUILD_DIR" --output-file "$LCOV_FILE.test" \
  --include "$INCLUDE_PATTERN"

# Combine baseline + test data
lcov -a "$LCOV_FILE.base" -a "$LCOV_FILE.test" -o "$LCOV_FILE"

# Remove noise (only when not filtering to a specific file)
if [ -z "$SOURCE_FILE" ]; then
  lcov --remove "$LCOV_FILE" '*/src/test/*' '*/contrib/*' '*/src/interfaces/ecpg/test/*' -o "$LCOV_FILE" --ignore-errors unused
fi

# Generate HTML
genhtml "$LCOV_FILE" --output-directory "$OUTPUT_DIR" --title "PostgreSQL Coverage" --ignore-errors unmapped,unused

echo "Report: $OUTPUT_DIR/index.html"

# Zip the report
zip -rq "$OUTPUT_DIR.zip" "$OUTPUT_DIR"
echo "Zipped: $OUTPUT_DIR.zip"
