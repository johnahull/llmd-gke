#!/bin/bash
# Comprehensive benchmark for istio-kserve-pattern1 cluster
# Tests throughput and latency under various load conditions
#
# Usage: ./benchmark-cluster.sh [protocol] [gateway_ip]
# Examples:
#   ./benchmark-cluster.sh http 34.7.208.8
#   ./benchmark-cluster.sh https 34.7.208.8
#   ./benchmark-cluster.sh  # Uses defaults

set -euo pipefail

# Configuration
PROTOCOL=${1:-"http"}
GATEWAY_IP=${2:-"34.7.208.8"}
BASE_URL="${PROTOCOL}://${GATEWAY_IP}"
PATH_PREFIX="/llm-d-inference-scheduling/qwen2-3b-pattern1"
ENDPOINT="$BASE_URL${PATH_PREFIX}/v1/completions"
MODEL="Qwen/Qwen2.5-3B-Instruct"

# Benchmark scenarios
SCENARIOS=(
  "1,1,Baseline (1 req, concurrency 1)"
  "10,1,Serial (10 req, concurrency 1)"
  "20,5,Light load (20 req, concurrency 5)"
  "50,10,Medium load (50 req, concurrency 10)"
  "100,20,Heavy load (100 req, concurrency 20)"
)

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Add curl opts for HTTPS
CURL_OPTS=""
AB_OPTS=""
if [ "$PROTOCOL" = "https" ]; then
    CURL_OPTS="-k"
    # Note: ab doesn't have a simple flag for self-signed certs
    echo -e "${YELLOW}Warning: Apache Bench may not work with self-signed HTTPS certs${NC}"
    echo "Consider using HTTP for benchmarking: ./benchmark-cluster.sh http $GATEWAY_IP"
    echo ""
fi

echo -e "${BLUE}========================================"
echo "  istio-kserve-pattern1 Benchmark"
echo "========================================${NC}"
echo "Endpoint: $ENDPOINT"
echo "Model: $MODEL"
echo "Protocol: $PROTOCOL"
echo ""

# Check prerequisites
if ! command -v ab &> /dev/null; then
    echo -e "${RED}Error: Apache Bench (ab) not found${NC}"
    echo "Install with:"
    echo "  Fedora/RHEL: sudo dnf install httpd-tools"
    echo "  Ubuntu/Debian: sudo apt-get install apache2-utils"
    echo ""
    echo "Or use curl-based testing instead"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${YELLOW}Warning: jq not found (optional, for pretty output)${NC}"
    echo "Install with: sudo dnf install jq"
    echo ""
fi

# Pre-flight check
echo -n "Pre-flight: Checking endpoint... "
PREFLIGHT=$(curl -s $CURL_OPTS -X GET "$BASE_URL${PATH_PREFIX}/v1/models" \
  --connect-timeout 10 --max-time 10 -w "%{http_code}" -o /dev/null 2>/dev/null || echo "000")

if [ "$PREFLIGHT" = "200" ]; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED (HTTP $PREFLIGHT)${NC}"
    echo ""
    echo "Cluster appears to be scaled down or unavailable."
    echo "Check cluster status:"
    echo "  kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling"
    echo "  kubectl get pods -n llm-d-inference-scheduling"
    echo ""
    echo "To start the cluster:"
    echo "  1. Scale up node pool:"
    echo "     gcloud container clusters resize istio-kserve-pattern1 \\"
    echo "       --node-pool=tpu-v6e-pool --num-nodes=1 \\"
    echo "       --zone=europe-west4-a --project=ecoeng-llmd"
    echo ""
    echo "  2. Scale up deployment:"
    echo "     kubectl patch llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling \\"
    echo "       --type='json' -p='[{\"op\": \"replace\", \"path\": \"/spec/replicas\", \"value\": 1}]'"
    echo ""
    echo "  3. Wait ~7-10 minutes for pod to be ready"
    exit 1
fi

# Create results directory
RESULTS_DIR="../benchmarks/results/cluster"
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SUMMARY_FILE="$RESULTS_DIR/benchmark_summary_${TIMESTAMP}.txt"

# Start summary file
{
    echo "================================================"
    echo "  istio-kserve-pattern1 Benchmark Results"
    echo "================================================"
    echo "Date: $(date)"
    echo "Endpoint: $ENDPOINT"
    echo "Model: $MODEL"
    echo "Protocol: $PROTOCOL"
    echo ""
} > "$SUMMARY_FILE"

echo ""
echo "Running benchmark scenarios..."
echo ""

# Run each scenario
for scenario in "${SCENARIOS[@]}"; do
    IFS=',' read -r num_requests concurrency description <<< "$scenario"

    echo -e "${BLUE}Scenario: $description${NC}"
    echo "  Requests: $num_requests, Concurrency: $concurrency"

    # Create POST data file
    TMP_FILE=$(mktemp)
    cat > "$TMP_FILE" << EOF
{
  "model": "$MODEL",
  "prompt": "Explain quantum computing in one sentence:",
  "max_tokens": 50,
  "temperature": 0.7
}
EOF

    # Output files
    TSV_FILE="$RESULTS_DIR/ab_${num_requests}req_${concurrency}c_${TIMESTAMP}.tsv"
    AB_OUTPUT="$RESULTS_DIR/ab_${num_requests}req_${concurrency}c_${TIMESTAMP}.txt"

    # Run Apache Bench
    if ab -n "$num_requests" \
        -c "$concurrency" \
        -p "$TMP_FILE" \
        -T "application/json" \
        -g "$TSV_FILE" \
        "$ENDPOINT" > "$AB_OUTPUT" 2>&1; then

        # Extract key metrics
        REQUESTS_PER_SEC=$(grep "Requests per second:" "$AB_OUTPUT" | awk '{print $4}')
        TIME_PER_REQUEST=$(grep "Time per request:" "$AB_OUTPUT" | grep "mean" | head -1 | awk '{print $4}')
        FAILED_REQUESTS=$(grep "Failed requests:" "$AB_OUTPUT" | awk '{print $3}')

        echo -e "  ${GREEN}✓ Complete${NC}"
        echo "  Throughput: $REQUESTS_PER_SEC req/sec"
        echo "  Latency (mean): ${TIME_PER_REQUEST}ms"
        echo "  Failed: $FAILED_REQUESTS"

        # Add to summary
        {
            echo "----------------------------------------"
            echo "Scenario: $description"
            echo "  Requests: $num_requests"
            echo "  Concurrency: $concurrency"
            echo "  Throughput: $REQUESTS_PER_SEC req/sec"
            echo "  Latency (mean): ${TIME_PER_REQUEST}ms"
            echo "  Failed requests: $FAILED_REQUESTS"
            echo ""
        } >> "$SUMMARY_FILE"

    else
        echo -e "  ${RED}✗ Failed${NC}"
        echo "  Check $AB_OUTPUT for details"

        {
            echo "----------------------------------------"
            echo "Scenario: $description - FAILED"
            echo "  See $AB_OUTPUT for details"
            echo ""
        } >> "$SUMMARY_FILE"
    fi

    rm "$TMP_FILE"
    echo ""
done

# Final summary
{
    echo "================================================"
    echo "Results saved to: $RESULTS_DIR"
    echo "================================================"
} >> "$SUMMARY_FILE"

echo -e "${GREEN}========================================"
echo "  Benchmark Complete"
echo "========================================${NC}"
echo ""
echo "Summary:"
cat "$SUMMARY_FILE"
echo ""
echo "Detailed results:"
echo "  Summary: $SUMMARY_FILE"
echo "  TSV files: $RESULTS_DIR/ab_*_${TIMESTAMP}.tsv"
echo "  Raw output: $RESULTS_DIR/ab_*_${TIMESTAMP}.txt"
echo ""
echo "To visualize results:"
echo "  # Import TSV files into Excel/Google Sheets"
echo "  # Or use gnuplot:"
echo "  gnuplot -e 'set datafile separator \"\t\"; plot \"$RESULTS_DIR/ab_100req_20c_${TIMESTAMP}.tsv\" using 2:5 with linespoints title \"Response Time\"'"
