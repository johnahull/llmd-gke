# RHAIIS vLLM Benchmarks - Quick Start Guide

## Setup (One-Time)

```bash
cd /home/jhull/devel/rhaiis-test
./benchmarks/scripts/setup_env.sh
```

This installs all dependencies and activates the Python virtual environment.

## Quick Tests

### 1. Health Check (10 seconds)

Verify the deployment is working:

```bash
./benchmarks/scripts/quick_test.sh http://136.116.159.221:8000
```

**What it does:**
- Health check
- Model availability check
- Single completion request with timing
- Shows basic latency and throughput

**When to use:**
- After deployment or configuration changes
- Daily health checks
- Quick validation

### 2. Apache Bench (1-3 minutes)

Simple HTTP load test:

```bash
./benchmarks/scripts/ab_benchmark.sh http://136.116.159.221:8000 100 10
# Arguments: URL, total_requests, concurrency
```

**What it does:**
- Sends 100 requests with concurrency 10
- Measures basic request/response metrics
- Saves results to TSV file

**When to use:**
- Quick baseline throughput measurement
- Before/after comparisons
- Simple load testing

## Comprehensive Benchmarks

### 3. Latency Benchmark (5-10 minutes)

Detailed TTFT/TPOT measurement:

```bash
# Activate venv
source /home/jhull/devel/venv/bin/activate

# Run benchmark
python benchmarks/python/benchmark_async.py \
    --target gke-t4 \
    --scenario latency_benchmark \
    --output benchmarks/results/latency_$(date +%Y%m%d).json \
    --html
```

**What it measures:**
- Time to First Token (TTFT) - p50, p90, p95, p99
- Time Per Output Token (TPOT) - p50, p90, p95, p99
- End-to-end latency
- Throughput (tokens/sec, requests/sec)
- MLPerf 2025-2026 compliance

**Output:**
- JSON file with all metrics
- HTML report with visualizations

**When to use:**
- Pre-deployment validation
- Performance regression testing
- MLPerf compliance verification

### 4. Quick Validation (1 minute)

Fast sanity check:

```bash
source /home/jhull/devel/venv/bin/activate

python benchmarks/python/benchmark_async.py \
    --target gke-t4 \
    --scenario quick_validation \
    --output benchmarks/results/quick_$(date +%Y%m%d).json
```

**What it does:**
- 10 requests, concurrency 1
- Basic TTFT/TPOT measurement
- Success rate check

**When to use:**
- Quick automated checks
- CI/CD pipelines
- Continuous monitoring

## Load Testing

### 5. Locust Load Test (10+ minutes)

Sustained load with realistic user patterns:

```bash
source /home/jhull/devel/venv/bin/activate

# Headless mode (automated)
locust -f benchmarks/python/locustfile.py \
       --host http://136.116.159.221:8000 \
       --users 50 \
       --spawn-rate 10 \
       --run-time 10m \
       --html benchmarks/results/locust_$(date +%Y%m%d).html
```

**Or web UI mode (interactive):**

```bash
locust -f benchmarks/python/locustfile.py \
       --host http://136.116.159.221:8000

# Then open http://localhost:8089 in your browser
```

**What it tests:**
- Sustained concurrent load
- Mixed prompt sizes (40% short, 40% medium, 20% long)
- Realistic user behavior (think time between requests)
- Error rates under load
- Performance degradation

**Output:**
- HTML report with charts
- Real-time metrics in web UI
- CSV time-series data

**When to use:**
- Production readiness testing
- Capacity planning
- Stress testing

## Comparing GPU vs TPU

```bash
source /home/jhull/devel/venv/bin/activate

./benchmarks/scripts/compare_targets.sh
# Enter TPU IP when prompted (or press Enter to skip)
```

**What it does:**
- Runs identical benchmark on both GPU and TPU
- Generates side-by-side comparison
- Shows relative performance ratios

## Custom Benchmarks

### Using Command-Line Options

```bash
source /home/jhull/devel/venv/bin/activate

python benchmarks/python/benchmark_async.py \
    --base-url http://136.116.159.221:8000 \
    --model google/gemma-2b-it \
    --num-requests 100 \
    --concurrency 10 \
    --max-tokens 200 \
    --output benchmarks/results/custom_test.json \
    --html
```

**Available options:**
- `--target`: Use predefined target (gke-t4, tpu-v6e)
- `--scenario`: Use predefined scenario (latency_benchmark, etc.)
- `--base-url`: Custom URL
- `--model`: Model name
- `--num-requests`: Total requests
- `--concurrency`: Concurrent requests
- `--max-tokens`: Max tokens per request
- `--output`: Output file (.json or .html)
- `--html`: Also generate HTML report

## Understanding Results

### MLPerf Compliance

**Standard Workload:**
- ✓ TTFT p95 ≤ 2.0 seconds
- ✓ TPOT p95 ≤ 100 milliseconds

**Interactive Workload (aggressive):**
- ✓ TTFT p95 ≤ 0.5 seconds
- ✓ TPOT p95 ≤ 30 milliseconds

### Expected Performance (GKE T4 GPU)

Based on recent test results:

- **TTFT p50**: ~1.3 seconds
- **TTFT p95**: ~1.4 seconds ✓ (below 2.0s threshold)
- **TPOT**: ~0ms in non-streaming mode (all tokens generated at once)
- **Throughput**: 85-95 tokens/sec
- **Success Rate**: 100%
- **MLPerf Standard**: ✓ PASS

### Good vs. Bad Results

**Good Indicators:**
- ✓ Success rate > 99%
- ✓ TTFT p95 < 2.0s
- ✓ Consistent performance (p95/p50 ratio < 2)
- ✓ Error rate < 1%

**Warning Signs:**
- ⚠ Success rate < 95%
- ⚠ TTFT p95 > 5s
- ⚠ High variance (p99 >> p95)
- ⚠ Error rate > 5%

## Viewing Results

### JSON Reports

```bash
# View with jq
cat benchmarks/results/benchmark_20260119.json | jq '.metrics | {success_rate, ttft_p95, throughput_tokens_per_sec, mlperf_compliant}'

# Full metrics
cat benchmarks/results/benchmark_20260119.json | jq '.metrics'
```

### HTML Reports

```bash
# Copy to local machine to view
# Or use Python HTTP server:
cd benchmarks/results
python3 -m http.server 8080

# Then open http://localhost:8080/benchmark_20260119.html
```

## Common Workflows

### Daily Health Check

```bash
./benchmarks/scripts/quick_test.sh http://136.116.159.221:8000
```

### Weekly Performance Test

```bash
source /home/jhull/devel/venv/bin/activate

python benchmarks/python/benchmark_async.py \
    --target gke-t4 \
    --scenario latency_benchmark \
    --output benchmarks/results/weekly_$(date +%Y%m%d).json \
    --html
```

### Pre-Production Validation

```bash
source /home/jhull/devel/venv/bin/activate

# 1. Latency benchmark
python benchmarks/python/benchmark_async.py \
    --target gke-t4 \
    --scenario latency_benchmark \
    --output benchmarks/results/preprod_latency.json \
    --html

# 2. Load test (30 minutes)
locust -f benchmarks/python/locustfile.py \
       --host http://136.116.159.221:8000 \
       --users 100 \
       --spawn-rate 10 \
       --run-time 30m \
       --html benchmarks/results/preprod_load.html
```

## Troubleshooting

### High TTFT

Check queue depth and reduce concurrency:
```bash
curl http://136.116.159.221:8000/metrics | grep num_requests_running
```

### Errors or Timeouts

Check server logs:
```bash
# GKE
kubectl logs -l app=rhaiis-inference --tail=50

# TPU VM
gcloud compute tpus tpu-vm ssh test-tpu --zone=us-east5-a --command="podman logs vllm-tpu --tail=50"
```

### Connection Refused

Verify firewall and service:
```bash
# Test health endpoint
curl http://136.116.159.221:8000/health

# Check GKE service
kubectl get svc rhaiis-t4-test
```

## More Information

For complete documentation, see:
- `/home/jhull/devel/rhaiis-test/benchmarks.md` - Complete benchmark guide
- `/home/jhull/devel/rhaiis-test/cluster-setup.md` - GKE deployment guide
- `/home/jhull/devel/rhaiis-test/tpu-vm-setup.md` - TPU VM deployment guide

## Summary of Available Tools

| Tool | Duration | Use Case | Output |
|------|----------|----------|--------|
| quick_test.sh | 10s | Health check | Console |
| ab_benchmark.sh | 1-3min | Simple load test | TSV file |
| benchmark_async.py | 5-20min | Comprehensive metrics | JSON/HTML |
| locustfile.py | 10+min | Sustained load | HTML/CSV |
| compare_targets.sh | 10-20min | GPU vs TPU | Console/JSON |

**Recommendation**: Start with `quick_test.sh`, then run `benchmark_async.py` with `latency_benchmark` scenario for detailed analysis.
