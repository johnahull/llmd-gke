#!/bin/bash
# Compare GPU vs TPU performance
# Usage: ./compare_targets.sh [tpu_ip]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PATH="/home/jhull/devel/venv"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Activate venv
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
fi

echo -e "${BLUE}========================================"
echo "  GPU vs TPU Comparison Benchmark"
echo "========================================${NC}"
echo ""

# Get TPU IP from argument or prompt
TPU_IP=$1
if [ -z "$TPU_IP" ]; then
    echo "No TPU IP provided."
    read -p "Enter TPU VM external IP (or press Enter to skip TPU test): " TPU_IP
fi

# Test parameters
TEST_SCENARIO="latency_benchmark"
OUTPUT_DIR="$BENCHMARK_DIR/results/comparison_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

# Run GPU benchmark
echo -e "${BLUE}Testing GKE T4 GPU...${NC}"
echo ""
python3 "$BENCHMARK_DIR/python/benchmark_async.py" \
    --target gke-t4 \
    --scenario "$TEST_SCENARIO" \
    --output "$OUTPUT_DIR/gpu_results.json"

GPU_STATUS=$?

# Run TPU benchmark if IP provided
if [ -n "$TPU_IP" ]; then
    echo ""
    echo -e "${BLUE}Testing TPU v6e...${NC}"
    echo ""

    # Temporarily override TPU URL
    python3 "$BENCHMARK_DIR/python/benchmark_async.py" \
        --base-url "http://$TPU_IP:8000" \
        --model "google/gemma-2b-it" \
        --scenario "$TEST_SCENARIO" \
        --output "$OUTPUT_DIR/tpu_results.json"

    TPU_STATUS=$?
else
    echo -e "${YELLOW}Skipping TPU test (no IP provided)${NC}"
    TPU_STATUS=1
fi

# Generate comparison report
echo ""
echo -e "${BLUE}Generating comparison report...${NC}"
echo ""

python3 -c "
import json
import sys
from pathlib import Path

def load_results(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error loading {path}: {e}', file=sys.stderr)
        return None

gpu_results = load_results('$OUTPUT_DIR/gpu_results.json')
tpu_results = load_results('$OUTPUT_DIR/tpu_results.json')

print('\n' + '='*60)
print('  Performance Comparison Report')
print('='*60 + '\n')

if gpu_results:
    print('GPU (GKE T4):')
    print(f'  TTFT (p50): {gpu_results.get(\"ttft_p50\", \"N/A\"):.3f}s')
    print(f'  TTFT (p95): {gpu_results.get(\"ttft_p95\", \"N/A\"):.3f}s')
    print(f'  TPOT (p50): {gpu_results.get(\"tpot_p50\", \"N/A\"):.3f}s')
    print(f'  TPOT (p95): {gpu_results.get(\"tpot_p95\", \"N/A\"):.3f}s')
    print(f'  Throughput: {gpu_results.get(\"throughput_tokens_per_sec\", \"N/A\"):.2f} tokens/s')
    print(f'  Success rate: {(1 - gpu_results.get(\"error_rate\", 0)) * 100:.1f}%')
    mlperf = gpu_results.get('mlperf_compliant', False)
    print(f'  MLPerf compliant: {\"✓ Yes\" if mlperf else \"✗ No\"}')

if tpu_results:
    print('\nTPU (v6e):')
    print(f'  TTFT (p50): {tpu_results.get(\"ttft_p50\", \"N/A\"):.3f}s')
    print(f'  TTFT (p95): {tpu_results.get(\"ttft_p95\", \"N/A\"):.3f}s')
    print(f'  TPOT (p50): {tpu_results.get(\"tpot_p50\", \"N/A\"):.3f}s')
    print(f'  TPOT (p95): {tpu_results.get(\"tpot_p95\", \"N/A\"):.3f}s')
    print(f'  Throughput: {tpu_results.get(\"throughput_tokens_per_sec\", \"N/A\"):.2f} tokens/s')
    print(f'  Success rate: {(1 - tpu_results.get(\"error_rate\", 0)) * 100:.1f}%')
    mlperf = tpu_results.get('mlperf_compliant', False)
    print(f'  MLPerf compliant: {\"✓ Yes\" if mlperf else \"✗ No\"}')

if gpu_results and tpu_results:
    print('\n' + '-'*60)
    print('Relative Performance (TPU vs GPU):')
    print('-'*60)
    ttft_ratio = tpu_results.get('ttft_p50', 1) / gpu_results.get('ttft_p50', 1)
    tpot_ratio = tpu_results.get('tpot_p50', 1) / gpu_results.get('tpot_p50', 1)
    throughput_ratio = tpu_results.get('throughput_tokens_per_sec', 1) / gpu_results.get('throughput_tokens_per_sec', 1)

    print(f'  TTFT (p50): {ttft_ratio:.2f}x')
    print(f'  TPOT (p50): {tpot_ratio:.2f}x')
    print(f'  Throughput: {throughput_ratio:.2f}x')

    print('\nInterpretation:')
    if throughput_ratio > 1.1:
        print('  TPU has higher throughput than GPU')
    elif throughput_ratio < 0.9:
        print('  GPU has higher throughput than TPU')
    else:
        print('  TPU and GPU have similar throughput')

print('\n' + '='*60)
print(f'Detailed results saved to: $OUTPUT_DIR')
print('='*60 + '\n')
"

echo ""
echo -e "${GREEN}Comparison complete!${NC}"
echo "Results directory: $OUTPUT_DIR"
