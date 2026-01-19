#!/bin/bash
# Quick validation test for RHAIIS vLLM deployment
# Usage: ./quick_test.sh [base_url]

BASE_URL=${1:-"http://136.116.159.221:8000"}
MODEL="google/gemma-2b-it"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "  RHAIIS vLLM Quick Validation Test"
echo "========================================"
echo "Target: $BASE_URL"
echo ""

# 1. Health check
echo -n "Health check... "
HEALTH=$(curl -s -w "%{http_code}" -o /dev/null --connect-timeout 10 "$BASE_URL/health")
if [ "$HEALTH" = "200" ]; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED (HTTP $HEALTH)${NC}"
    echo "Cannot connect to vLLM server. Please check:"
    echo "  1. Server is running"
    echo "  2. URL is correct"
    echo "  3. Firewall allows access to port 8000"
    exit 1
fi

# 2. Model info
echo -n "Model info... "
MODEL_INFO=$(curl -s "$BASE_URL/v1/models" 2>/dev/null)
if echo "$MODEL_INFO" | grep -q "$MODEL"; then
    echo -e "${GREEN}✓ Model available: $MODEL${NC}"
    MAX_MODEL_LEN=$(echo "$MODEL_INFO" | jq -r '.data[0].max_model_len // "N/A"' 2>/dev/null)
    if [ "$MAX_MODEL_LEN" != "N/A" ]; then
        echo "  Max context length: $MAX_MODEL_LEN tokens"
    fi
else
    echo -e "${YELLOW}⚠ Warning: Model name mismatch or unavailable${NC}"
fi

# 3. Completion test with timing
echo ""
echo -e "${BLUE}Running completion test...${NC}"
START=$(date +%s.%N)
RESPONSE=$(curl -s -X POST "$BASE_URL/v1/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"prompt\": \"Explain quantum computing in one sentence:\",
    \"max_tokens\": 50,
    \"temperature\": 0.7
  }" 2>/dev/null)
END=$(date +%s.%N)

if echo "$RESPONSE" | grep -q "choices"; then
    LATENCY=$(echo "$END - $START" | bc)
    echo -e "${GREEN}✓ Completion successful${NC}"
    echo ""
    echo "Performance Metrics:"
    echo "  Total latency: ${LATENCY}s"

    # Extract token counts if available
    if echo "$RESPONSE" | jq -e '.usage' > /dev/null 2>&1; then
        PROMPT_TOKENS=$(echo "$RESPONSE" | jq -r '.usage.prompt_tokens // "N/A"')
        COMPLETION_TOKENS=$(echo "$RESPONSE" | jq -r '.usage.completion_tokens // "N/A"')
        TOTAL_TOKENS=$(echo "$RESPONSE" | jq -r '.usage.total_tokens // "N/A"')
        echo "  Prompt tokens: $PROMPT_TOKENS"
        echo "  Completion tokens: $COMPLETION_TOKENS"
        echo "  Total tokens: $TOTAL_TOKENS"

        # Calculate tokens per second
        if [ "$COMPLETION_TOKENS" != "N/A" ] && [ "$LATENCY" != "0" ]; then
            TOKENS_PER_SEC=$(echo "scale=2; $COMPLETION_TOKENS / $LATENCY" | bc)
            echo "  Throughput: ${TOKENS_PER_SEC} tokens/sec"
        fi
    fi

    # Show response
    echo ""
    echo "Response:"
    echo "----------------------------------------"
    echo "$RESPONSE" | jq -r '.choices[0].text' 2>/dev/null | head -c 500
    echo ""
    echo "----------------------------------------"
else
    echo -e "${RED}✗ Completion failed${NC}"
    echo "Error response:"
    echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================"
echo "  All tests passed!"
echo "========================================${NC}"
echo ""
echo "Quick validation complete. For comprehensive benchmarking, use:"
echo "  python benchmarks/python/benchmark_async.py --target gke-t4 --scenario latency_benchmark"
