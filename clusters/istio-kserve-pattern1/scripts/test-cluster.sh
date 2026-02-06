#!/bin/bash
# Quick validation test for istio-kserve-pattern1 cluster
# Tests LLM inference through Gateway API with path-based routing
#
# Usage: ./test-cluster.sh [http|https] [gateway_ip]
# Examples:
#   ./test-cluster.sh http 34.7.208.8
#   ./test-cluster.sh https 34.7.208.8
#   ./test-cluster.sh  # Uses defaults

set -euo pipefail

# Configuration
PROTOCOL=${1:-"http"}
GATEWAY_IP=${2:-"34.7.208.8"}
BASE_URL="${PROTOCOL}://${GATEWAY_IP}"
PATH_PREFIX="/llm-d-inference-scheduling/qwen2-3b-pattern1"
MODEL="Qwen/Qwen2.5-3B-Instruct"

# Add -k flag for HTTPS with self-signed cert
CURL_OPTS=""
if [ "$PROTOCOL" = "https" ]; then
    CURL_OPTS="-k"
fi

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "  istio-kserve-pattern1 Cluster Test"
echo "========================================"
echo "Gateway: $BASE_URL"
echo "Path: $PATH_PREFIX"
echo "Model: $MODEL"
echo ""

# 1. Gateway connectivity check
echo -n "Gateway connectivity... "
if curl -s $CURL_OPTS -w "%{http_code}" -o /dev/null --connect-timeout 10 --max-time 10 "$BASE_URL/" | grep -qE "^(200|404)$"; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ FAILED${NC}"
    echo "Cannot connect to Gateway at $BASE_URL"
    echo "Check:"
    echo "  1. Cluster is running: kubectl get gateway -n opendatahub"
    echo "  2. Gateway IP is correct: kubectl get gateway inference-gateway -n opendatahub -o jsonpath='{.status.addresses[0].value}'"
    echo "  3. LoadBalancer is provisioned"
    exit 1
fi

# 2. Model info check
echo -n "Model info... "
MODEL_INFO=$(curl -s $CURL_OPTS -X GET "$BASE_URL${PATH_PREFIX}/v1/models" \
  --connect-timeout 10 --max-time 10 2>/dev/null)

if echo "$MODEL_INFO" | grep -q "data"; then
    echo -e "${GREEN}✓ Model endpoint accessible${NC}"

    # Extract model details if available
    if command -v jq &> /dev/null; then
        MODEL_ID=$(echo "$MODEL_INFO" | jq -r '.data[0].id // "N/A"' 2>/dev/null)
        MAX_MODEL_LEN=$(echo "$MODEL_INFO" | jq -r '.data[0].max_model_len // "N/A"' 2>/dev/null)
        if [ "$MAX_MODEL_LEN" != "N/A" ]; then
            echo "  Model ID: $MODEL_ID"
            echo "  Max context length: $MAX_MODEL_LEN tokens"
        fi
    fi
else
    echo -e "${RED}✗ FAILED${NC}"
    echo "Model endpoint not accessible or deployment scaled to 0"
    echo "Check:"
    echo "  1. LLMInferenceService status: kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling"
    echo "  2. Pod is running: kubectl get pods -n llm-d-inference-scheduling"
    echo "  3. HTTPRoute exists: kubectl get httproute -n llm-d-inference-scheduling"
    echo ""
    echo "If scaled to 0, start deployment first:"
    echo "  kubectl patch llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling \\"
    echo "    --type='json' -p='[{\"op\": \"replace\", \"path\": \"/spec/replicas\", \"value\": 1}]'"
    exit 1
fi

# 3. Completion test (text completion endpoint)
echo ""
echo -e "${BLUE}Running completion test...${NC}"
START=$(date +%s.%N)
RESPONSE=$(curl -s $CURL_OPTS -X POST "$BASE_URL${PATH_PREFIX}/v1/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"prompt\": \"What is 2+2? Answer:\",
    \"max_tokens\": 20,
    \"temperature\": 0
  }" \
  --connect-timeout 10 --max-time 30 2>/dev/null)
END=$(date +%s.%N)

if echo "$RESPONSE" | grep -q "choices"; then
    LATENCY=$(echo "$END - $START" | bc)
    echo -e "${GREEN}✓ Completion successful${NC}"
    echo ""
    echo "Performance Metrics:"
    echo "  Total latency: ${LATENCY}s"

    # Extract token counts if available and jq is installed
    if command -v jq &> /dev/null && echo "$RESPONSE" | jq -e '.usage' > /dev/null 2>&1; then
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
    if command -v jq &> /dev/null; then
        echo "$RESPONSE" | jq -r '.choices[0].text' 2>/dev/null | head -c 500
    else
        echo "$RESPONSE" | grep -o '"text":"[^"]*"' | head -1 | cut -d'"' -f4
    fi
    echo ""
    echo "----------------------------------------"
else
    echo -e "${RED}✗ Completion failed${NC}"
    echo "Error response:"
    if command -v jq &> /dev/null; then
        echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
    else
        echo "$RESPONSE"
    fi
    exit 1
fi

# 4. Chat completion test
echo ""
echo -e "${BLUE}Running chat completion test...${NC}"
START=$(date +%s.%N)
CHAT_RESPONSE=$(curl -s $CURL_OPTS -X POST "$BASE_URL${PATH_PREFIX}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Hello! Respond with just 'Hi'\"}],
    \"max_tokens\": 10,
    \"temperature\": 0
  }" \
  --connect-timeout 10 --max-time 30 2>/dev/null)
END=$(date +%s.%N)

if echo "$CHAT_RESPONSE" | grep -q "choices"; then
    CHAT_LATENCY=$(echo "$END - $START" | bc)
    echo -e "${GREEN}✓ Chat completion successful${NC}"
    echo "  Latency: ${CHAT_LATENCY}s"

    echo ""
    echo "Chat Response:"
    echo "----------------------------------------"
    if command -v jq &> /dev/null; then
        echo "$CHAT_RESPONSE" | jq -r '.choices[0].message.content' 2>/dev/null | head -c 500
    else
        echo "$CHAT_RESPONSE" | grep -o '"content":"[^"]*"' | head -1 | cut -d'"' -f4
    fi
    echo ""
    echo "----------------------------------------"
else
    echo -e "${YELLOW}⚠ Chat completion failed${NC}"
    echo "This is non-critical. Text completions work fine."
fi

echo ""
echo -e "${GREEN}========================================"
echo "  Cluster validation passed!"
echo "========================================${NC}"
echo ""
echo "Cluster Status:"
echo "  Protocol: $PROTOCOL"
echo "  Gateway: $BASE_URL"
echo "  Latency: ${LATENCY}s (completion)"
echo ""
echo "Next steps:"
echo "  # Test HTTPS endpoint:"
echo "  ./test-cluster.sh https $GATEWAY_IP"
echo ""
echo "  # Check cluster status:"
echo "  kubectl get llminferenceservice -n llm-d-inference-scheduling"
echo "  kubectl get pods -n llm-d-inference-scheduling"
echo "  kubectl get gateway -n opendatahub"
echo ""
echo "  # Run comprehensive benchmark:"
echo "  cd ../../benchmarks"
echo "  ./scripts/benchmark-cluster.sh"
