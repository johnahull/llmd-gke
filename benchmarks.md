# RHAIIS vLLM Benchmark Suite

Industry-standard benchmark suite for testing RHAIIS vLLM inference deployments on Google Cloud, following MLPerf 2025-2026 standards.

## Quick Start

**Note**: This guide uses shell variables for cluster-specific values. Set these based on your deployment:
- `$EXTERNAL_IP` - Your cluster's external IP address
- `$SERVICE_NAME` - Your Kubernetes service name (GKE)
- `$TPU_NAME` - Your TPU VM name (TPU standalone)
- `$ZONE` - Your cluster zone
- `$PROJECT_ID` - Your GCP project ID
- `$MODEL_NAME` - Your deployed model (e.g., google/gemma-2b-it)
- `$MAX_TOKENS` - Maximum context length (e.g., 4096 for GPU, 2048 for TPU)

### 1. Setup Environment

```bash
cd /home/jhull/devel/rhaiis-test
source /home/jhull/devel/venv/bin/activate
./benchmarks/scripts/setup_env.sh
```

### 2. Configure Your Target

Edit `benchmarks/config/targets.yaml` to add your cluster:

```yaml
targets:
  my-cluster:
    base_url: "http://$EXTERNAL_IP:8000"
    model: "$MODEL_NAME"  # e.g., google/gemma-2b-it
    max_tokens: $MAX_TOKENS  # e.g., 4096 for GPU, 2048 for TPU
```

Get your cluster IP:
```bash
# For GKE
EXTERNAL_IP=$(kubectl get svc $SERVICE_NAME -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# For TPU VM
EXTERNAL_IP=$(gcloud compute tpus tpu-vm describe $TPU_NAME --zone $ZONE --project $PROJECT_ID --format='get(networkEndpoints[0].accessConfig[0].externalIp)')

# Verify
echo "Cluster IP: $EXTERNAL_IP"
```

### 3. Quick Validation Test

```bash
./benchmarks/scripts/quick_test.sh http://$EXTERNAL_IP:8000
```

### 4. Run Full Benchmark

```bash
python benchmarks/python/benchmark_async.py \
    --target my-cluster \
    --scenario latency_benchmark \
    --output benchmarks/results/benchmark_$(date +%Y%m%d).json \
    --html
```

## Benchmark Types

### 1. Quick Validation (`quick_test.sh`)

**Purpose**: Fast health check and basic performance validation

**Duration**: 10-20 seconds

**Output**: Console with response time and basic metrics

**When to use**: Verify deployment is working after changes

```bash
./benchmarks/scripts/quick_test.sh http://$EXTERNAL_IP:8000
```

### 2. Apache Bench (`ab_benchmark.sh`)

**Purpose**: Simple HTTP load testing with minimal setup

**Duration**: 1-3 minutes

**Output**: Apache Bench statistics, TSV file for analysis

**When to use**: Quick baseline throughput measurement

```bash
./benchmarks/scripts/ab_benchmark.sh http://$EXTERNAL_IP:8000 100 10
# 100 requests, concurrency 10
```

### 3. Async Python Benchmark (`benchmark_async.py`)

**Purpose**: Comprehensive metrics collection (TTFT, TPOT, throughput, percentiles)

**Duration**: 5-20 minutes (depends on scenario)

**Output**: JSON and/or HTML reports with detailed metrics

**When to use**: Detailed performance analysis, MLPerf compliance validation

```bash
# Using predefined target and scenario
python benchmarks/python/benchmark_async.py \
    --target my-cluster \
    --scenario latency_benchmark \
    --output results/latency.json \
    --html

# Custom parameters
python benchmarks/python/benchmark_async.py \
    --base-url http://$EXTERNAL_IP:8000 \
    --model google/gemma-2b-it \
    --num-requests 100 \
    --concurrency 10 \
    --max-tokens 100 \
    --output results/custom_test.json
```

### 4. Locust Load Test (`locustfile.py`)

**Purpose**: Sustained load with realistic user behavior patterns

**Duration**: 10+ minutes (configurable)

**Output**: HTML report, real-time web UI, CSV time-series data

**When to use**: Production readiness testing, sustained load validation

```bash
# Web UI mode (interactive)
locust -f benchmarks/python/locustfile.py \
       --host http://$EXTERNAL_IP:8000
# Then open http://localhost:8089

# Headless mode (automated)
locust -f benchmarks/python/locustfile.py \
       --host http://$EXTERNAL_IP:8000 \
       --users 50 \
       --spawn-rate 10 \
       --run-time 10m \
       --html benchmarks/results/locust_report.html
```

## Test Scenarios

### Available Scenarios

Scenarios are defined in `benchmarks/config/test_scenarios.yaml`:

- **quick_validation**: 10 requests, fast health check
- **latency_benchmark**: 100 requests, focused TTFT/TPOT measurement
- **throughput_benchmark**: 500 requests with progressive concurrency
- **load_test**: Sustained load with mixed prompt sizes
- **stress_test**: Progressive load increase to find breaking point

### Using Scenarios

```bash
python benchmarks/python/benchmark_async.py \
    --target my-cluster \
    --scenario quick_validation
```

## Understanding Metrics

### Time to First Token (TTFT)

**Definition**: Time from request submission to receiving the first token

**Includes**:
- Request queueing time
- Prompt processing (prefill) time
- Network latency

**What affects it**:
- Prompt length (longer prompts = higher TTFT)
- Queue depth (more concurrent requests = higher TTFT)
- Model size

**MLPerf Standards**:
- Standard: TTFT p95 ≤ 2.0 seconds
- Interactive: TTFT p95 ≤ 0.5 seconds

### Time Per Output Token (TPOT)

**Definition**: Average time to generate each output token (excluding TTFT)

**Calculation**: (Generation time - TTFT) / (Number of output tokens - 1)

**What affects it**:
- Model size
- Batch size
- KV cache efficiency

**MLPerf Standards**:
- Standard: TPOT p95 ≤ 100 milliseconds
- Interactive: TPOT p95 ≤ 30 milliseconds

### Throughput

**Definition**: Total tokens generated per second across all requests

**What affects it**:
- Concurrency level
- Prompt/output length distribution
- Error rate

### Percentiles (p50, p90, p95, p99)

- **p50 (median)**: 50% of requests are faster
- **p90**: 90% of requests are faster
- **p95**: 95% of requests are faster (MLPerf uses this)
- **p99**: 99% of requests are faster

## Expected Performance Baselines

These baselines are for reference. Your actual performance will vary based on cluster configuration.

### GKE GPU (NVIDIA T4) - Example

**Configuration**:
- Model: google/gemma-2b-it
- GPU: NVIDIA T4 (13.12 GiB memory)
- Max context: 4096 tokens
- Backend: XFormers

**Expected Performance**:
- TTFT (p50): 0.3-0.8s (varies with prompt length)
- TTFT (p95): < 2.0s ✓ MLPerf compliant
- TPOT (p50): 20-50ms
- TPOT (p95): < 100ms ✓ MLPerf compliant
- Throughput: 500-1500 tokens/sec (depends on concurrency)
- Max concurrency: ~86 (based on KV cache)
- Error rate: < 1% under normal load

### GKE TPU (v6e Trillium) - Example

**Configuration**:
- Model: google/gemma-2b-it
- Accelerator: TPU v6e (4 chips, 2x2 topology)
- Max context: 2048 tokens
- Backend: JAX/XLA

**Expected Performance**:
- TTFT (p50): 0.5-2.0s
- TTFT (first request): 5-10s (XLA compilation)
- TPOT (p50): 30-80ms
- Throughput: 400-1200 tokens/sec
- Max concurrency: ~50 (estimated)

## Comparing Different Clusters

```bash
./benchmarks/scripts/compare_targets.sh

# Or manually:
# 1. Run benchmark on first cluster
python benchmarks/python/benchmark_async.py \
    --target cluster-1 \
    --scenario latency_benchmark \
    --output results/cluster1_results.json

# 2. Run benchmark on second cluster
python benchmarks/python/benchmark_async.py \
    --target cluster-2 \
    --scenario latency_benchmark \
    --output results/cluster2_results.json

# 3. Compare results manually or use compare script
```

## Interpreting Results

### Good Performance Indicators

- ✓ Success rate > 99%
- ✓ TTFT p95 < 2.0s (MLPerf standard)
- ✓ TPOT p95 < 100ms (MLPerf standard)
- ✓ Error rate < 1%
- ✓ Consistent performance across percentiles (p95/p50 ratio < 3)

### Warning Signs

- ⚠ Success rate < 95%
- ⚠ TTFT p95 > 5s
- ⚠ TPOT p95 > 200ms
- ⚠ High variance (p99 >> p95)
- ⚠ Error rate > 5%

### Red Flags

- ✗ Success rate < 90%
- ✗ TTFT p95 > 10s
- ✗ TPOT increasing with concurrency
- ✗ Timeout errors
- ✗ Error rate > 10%

## Troubleshooting

### High TTFT

**Possible causes**:
- High queue depth (too many concurrent requests)
- Long prompts
- Network latency

**Solutions**:
- Reduce concurrency
- Check `num_requests_running` metric
- Verify network connectivity

### High TPOT

**Possible causes**:
- KV cache full (memory pressure)
- Too many concurrent requests
- Model size vs. available memory

**Solutions**:
- Reduce `max_tokens`
- Lower concurrency
- Check KV cache usage: `curl http://$EXTERNAL_IP:8000/metrics | grep kv_cache`

### Low Throughput

**Possible causes**:
- Concurrency too low
- Network bottleneck
- High error rate

**Solutions**:
- Increase concurrency gradually
- Check network bandwidth
- Verify error logs

### TPU First Request Slow

**Expected behavior**: First request to TPU triggers XLA compilation (5-10s)

**Solution**: Run warmup requests before benchmarking

### Errors and Timeouts

**Check**:
1. Server logs: `kubectl logs $POD_NAME` (GKE) or `podman logs $CONTAINER_NAME` (standalone)
2. Server health: `curl http://$EXTERNAL_IP:8000/health`
3. Network connectivity
4. Firewall rules

## Integration with Prometheus/Grafana

vLLM exposes Prometheus metrics at `/metrics`:

```bash
# View raw metrics
curl http://$EXTERNAL_IP:8000/metrics

# Filter specific metrics
curl http://$EXTERNAL_IP:8000/metrics | grep vllm
```

**Key metrics**:
- `vllm:e2e_request_latency_seconds_bucket` - Latency histogram
- `vllm:num_requests_running` - Active requests
- `vllm:kv_cache_usage_perc` - KV cache utilization
- `vllm:request_prompt_tokens` - Prompt token distribution
- `vllm:request_generation_tokens` - Generated token distribution

**Grafana Dashboard**: [https://grafana.com/grafana/dashboards/23991-vllm/](https://grafana.com/grafana/dashboards/23991-vllm/)

## Configuration Files

### Targets (`benchmarks/config/targets.yaml`)

Define deployment targets with connection details and expected performance:

```yaml
targets:
  my-cluster:
    base_url: "http://$EXTERNAL_IP:8000"
    model: "$MODEL_NAME"
    max_tokens: $MAX_TOKENS
    description: "My inference cluster"
```

**To update**: Edit `benchmarks/config/targets.yaml` with your cluster details

### Scenarios (`benchmarks/config/test_scenarios.yaml`)

Define test scenarios with parameters:

```yaml
scenarios:
  latency_benchmark:
    num_requests: 100
    concurrency: 1
    prompt_tokens: [10, 50, 100, 500]
    max_tokens: [50, 100, 200]
```

**To add custom scenario**: Edit `benchmarks/config/test_scenarios.yaml`

## Best Practices

### Before Benchmarking

1. Verify deployment is healthy: `./benchmarks/scripts/quick_test.sh`
2. Check resource utilization is normal
3. Ensure no other load on the system
4. Use warmup requests for TPU deployments

### During Benchmarking

1. Start with low concurrency, increase gradually
2. Monitor server metrics (GPU/TPU utilization, memory)
3. Watch for error rates
4. Let tests run to completion for accurate results

### After Benchmarking

1. Review all percentiles, not just averages
2. Check for outliers (p99 vs p95)
3. Correlate with server-side metrics
4. Save results with descriptive names
5. Document any changes between runs

## Common Patterns

### Daily Health Check

```bash
./benchmarks/scripts/quick_test.sh http://$EXTERNAL_IP:8000
```

### Pre-Deployment Validation

```bash
python benchmarks/python/benchmark_async.py \
    --target my-cluster \
    --scenario latency_benchmark \
    --output results/pre_deploy_$(date +%Y%m%d).json \
    --html
```

### Load Testing Before Launch

```bash
locust -f benchmarks/python/locustfile.py \
       --host http://$EXTERNAL_IP:8000 \
       --users 100 \
       --spawn-rate 10 \
       --run-time 30m \
       --html results/pre_launch_load_test.html
```

### Continuous Monitoring

```bash
# Run every hour
python benchmarks/python/benchmark_async.py \
    --target my-cluster \
    --scenario quick_validation \
    --output results/monitoring/$(date +%Y%m%d_%H%M).json
```

## References

- [vLLM Metrics Documentation](https://docs.vllm.ai/en/latest/design/metrics/)
- [MLPerf Inference 5.1](https://mlcommons.org/2025/09/small-llm-inference-5-1/)
- [Anyscale LLM Metrics Guide](https://docs.anyscale.com/llm/serving/benchmarking/metrics)
- [vLLM Prometheus/Grafana Setup](https://docs.vllm.ai/en/v0.7.2/getting_started/examples/prometheus_grafana.html)

## Support

For issues or questions:
- Check troubleshooting section above
- Review `/home/jhull/devel/rhaiis-test/cluster-setup.md` for GKE setup
- Review `/home/jhull/devel/rhaiis-test/tpu-vm-setup.md` for TPU setup
- Check vLLM server logs for errors
