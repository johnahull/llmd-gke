#!/bin/bash
# Apache Bench benchmark for vLLM
# Usage: ./ab_benchmark.sh [base_url] [num_requests] [concurrency]

BASE_URL=${1:-"http://136.116.159.221:8000"}
NUM_REQUESTS=${2:-100}
CONCURRENCY=${3:-10}
MODEL="google/gemma-2b-it"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================"
echo "  Apache Bench vLLM Benchmark"
echo "========================================${NC}"
echo "Target: $BASE_URL"
echo "Total requests: $NUM_REQUESTS"
echo "Concurrency: $CONCURRENCY"
echo ""

# Check if ab is installed
if ! command -v ab &> /dev/null; then
    echo "Error: Apache Bench (ab) not found"
    echo "Install with: sudo apt-get install apache2-utils"
    exit 1
fi

# Create results directory
RESULTS_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")/results"
mkdir -p "$RESULTS_DIR"

# Create temporary POST data file
TMP_FILE=$(mktemp)
cat > "$TMP_FILE" << EOF
{
  "model": "$MODEL",
  "prompt": "Write a short story about a robot learning to paint:",
  "max_tokens": 100,
  "temperature": 0.7
}
EOF

# Generate output file names
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TSV_FILE="$RESULTS_DIR/ab_results_${TIMESTAMP}.tsv"

# Run Apache Bench
echo "Running benchmark..."
echo ""

ab -n "$NUM_REQUESTS" \
   -c "$CONCURRENCY" \
   -p "$TMP_FILE" \
   -T "application/json" \
   -g "$TSV_FILE" \
   "$BASE_URL/v1/completions"

# Cleanup
rm "$TMP_FILE"

echo ""
echo -e "${GREEN}========================================"
echo "  Benchmark Complete"
echo "========================================${NC}"
echo "Results saved to:"
echo "  $TSV_FILE"
echo ""
echo "To analyze results:"
echo "  cat $TSV_FILE"
echo "  # or import into spreadsheet/plotting tool"
