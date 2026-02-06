# Cluster Testing and Benchmarking Scripts

Scripts for testing and benchmarking the istio-kserve-pattern1 cluster.

## Prerequisites

### Required
- `curl` - For API testing
- `kubectl` - For cluster management
- Cluster access configured

### Optional
- `jq` - For JSON parsing (prettier output)
- `ab` (Apache Bench) - For load testing
- `bc` - For calculations

**Install on Fedora/RHEL:**
```bash
sudo dnf install curl jq httpd-tools bc
```

**Install on Ubuntu/Debian:**
```bash
sudo apt-get install curl jq apache2-utils bc
```

---

## Quick Test: test-cluster.sh

Validates cluster connectivity and runs basic inference tests.

### Usage

```bash
# Test with HTTP (default)
./test-cluster.sh

# Test with HTTPS
./test-cluster.sh https

# Custom Gateway IP
./test-cluster.sh http 34.7.208.8
```

### What It Tests

1. **Gateway Connectivity** - Verifies LoadBalancer is accessible
2. **Model Endpoint** - Checks `/v1/models` responds correctly
3. **Text Completion** - Tests `/v1/completions` endpoint
4. **Chat Completion** - Tests `/v1/chat/completions` endpoint

### Example Output

```
========================================
  istio-kserve-pattern1 Cluster Test
========================================
Gateway: http://34.7.208.8
Path: /llm-d-inference-scheduling/qwen2-3b-pattern1
Model: Qwen/Qwen2.5-3B-Instruct

Gateway connectivity... ✓ OK
Model info... ✓ Model endpoint accessible
  Model ID: /mnt/models
  Max context length: 2048 tokens

Running completion test...
✓ Completion successful

Performance Metrics:
  Total latency: 1.234s
  Prompt tokens: 8
  Completion tokens: 15
  Total tokens: 23
  Throughput: 12.16 tokens/sec

Response:
----------------------------------------
 4
----------------------------------------

========================================
  Cluster validation passed!
========================================
```

### Troubleshooting

**If model endpoint is not accessible:**

1. Check if deployment is scaled to 0:
   ```bash
   kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling
   ```

2. Scale up if needed:
   ```bash
   # Scale TPU node pool
   gcloud container clusters resize istio-kserve-pattern1 \
     --node-pool=tpu-v6e-pool --num-nodes=1 \
     --zone=europe-west4-a --project=ecoeng-llmd

   # Scale deployment
   kubectl patch llminferenceservice qwen2-3b-pattern1 \
     -n llm-d-inference-scheduling \
     --type='json' \
     -p='[{"op": "replace", "path": "/spec/replicas", "value": 1}]'

   # Wait ~7-10 minutes for pod to be ready
   kubectl get pods -n llm-d-inference-scheduling -w
   ```

---

## Comprehensive Benchmark: benchmark-cluster.sh

Runs Apache Bench load tests across multiple scenarios.

### Usage

```bash
# Run with HTTP (recommended for benchmarking)
./benchmark-cluster.sh http

# Run with HTTPS (may have issues with self-signed certs)
./benchmark-cluster.sh https

# Custom Gateway IP
./benchmark-cluster.sh http 34.7.208.8
```

### Benchmark Scenarios

| Scenario | Requests | Concurrency | Purpose |
|----------|----------|-------------|---------|
| Baseline | 1 | 1 | Single request latency |
| Serial | 10 | 1 | Sequential throughput |
| Light load | 20 | 5 | Low concurrency performance |
| Medium load | 50 | 10 | Moderate concurrency |
| Heavy load | 100 | 20 | High concurrency stress test |

### Example Output

```
========================================
  istio-kserve-pattern1 Benchmark
========================================
Endpoint: http://34.7.208.8/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/completions
Model: Qwen/Qwen2.5-3B-Instruct

Pre-flight: Checking endpoint... ✓ OK

Running benchmark scenarios...

Scenario: Baseline (1 req, concurrency 1)
  Requests: 1, Concurrency: 1
  ✓ Complete
  Throughput: 0.82 req/sec
  Latency (mean): 1225ms
  Failed: 0

Scenario: Medium load (50 req, concurrency 10)
  Requests: 50, Concurrency: 10
  ✓ Complete
  Throughput: 3.45 req/sec
  Latency (mean): 2897ms
  Failed: 0

...
```

### Output Files

Results are saved to `../../benchmarks/results/cluster/`:

- **Summary:** `benchmark_summary_YYYYMMDD_HHMMSS.txt`
- **TSV data:** `ab_*req_*c_YYYYMMDD_HHMMSS.tsv`
- **Raw output:** `ab_*req_*c_YYYYMMDD_HHMMSS.txt`

### Analyzing Results

**View summary:**
```bash
cat ../benchmarks/results/cluster/benchmark_summary_*.txt | tail -50
```

**Import TSV into spreadsheet:**
- Open Excel/Google Sheets
- Import TSV file
- Create charts for latency distribution, percentiles, etc.

**Plot with gnuplot:**
```bash
# Install gnuplot
sudo dnf install gnuplot

# Plot response times
gnuplot -persist -e '
  set datafile separator "\t";
  set xlabel "Request #";
  set ylabel "Response Time (ms)";
  set title "Response Time Distribution";
  plot "ab_100req_20c_*.tsv" using 2:5 with linespoints title "Response Time"
'
```

---

## Performance Expectations

### TPU v6e (Qwen/Qwen2.5-3B-Instruct)

**Single Request:**
- First request: ~7-10s (cold start + XLA compilation)
- Subsequent requests: ~1-2s (warm)

**Concurrent Requests:**
- Light load (5 concurrent): ~2-3 req/sec
- Medium load (10 concurrent): ~3-5 req/sec
- Heavy load (20 concurrent): ~4-6 req/sec

**Tokens:**
- Throughput: ~10-15 tokens/sec per request
- Max context: 2048 tokens

### Factors Affecting Performance

1. **Cold vs Warm Start**
   - First inference after pod start triggers XLA compilation
   - Compilation can take 30-60 seconds
   - Subsequent requests are much faster

2. **Request Size**
   - Larger prompts increase latency
   - max_tokens setting affects completion time

3. **Concurrency**
   - TPU v6e handles batching well
   - Throughput increases with concurrency up to ~20 concurrent requests

4. **Network**
   - Gateway adds ~10-50ms overhead
   - NetworkPolicy enforcement is transparent (no measurable impact)

---

## Cluster Status Commands

### Check if cluster is ready

```bash
# Gateway status
kubectl get gateway inference-gateway -n opendatahub

# LLMInferenceService status
kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling

# Pod status
kubectl get pods -n llm-d-inference-scheduling

# HTTPRoute status
kubectl get httproute -n llm-d-inference-scheduling
```

### Check Gateway IP

```bash
kubectl get gateway inference-gateway -n opendatahub \
  -o jsonpath='{.status.addresses[0].value}'
```

### View logs

```bash
# vLLM logs
kubectl logs -n llm-d-inference-scheduling \
  deployment/qwen2-3b-pattern1-kserve -f

# Gateway logs
kubectl logs -n opendatahub \
  deployment/inference-gateway-istio -f
```

---

## Cost Considerations

**Before benchmarking:**
- Ensure cluster is scaled up (costs ~$127/day for TPU)
- Consider running benchmarks during off-peak hours
- Scale down after testing to save costs

**Scale down after benchmarking:**
```bash
# Scale deployment to 0
kubectl patch llminferenceservice qwen2-3b-pattern1 \
  -n llm-d-inference-scheduling \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/replicas", "value": 0}]'

# Scale TPU node pool to 0
gcloud container clusters resize istio-kserve-pattern1 \
  --node-pool=tpu-v6e-pool --num-nodes=0 \
  --zone=europe-west4-a --project=ecoeng-llmd
```

---

## Advanced Testing

### Custom cURL Tests

```bash
# Get Gateway IP
GATEWAY_IP=$(kubectl get gateway inference-gateway -n opendatahub \
  -o jsonpath='{.status.addresses[0].value}')

# Test with custom prompt
curl -X POST "http://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "Your custom prompt here",
    "max_tokens": 100,
    "temperature": 0.7,
    "top_p": 0.9
  }' | jq .
```

### Stress Testing

```bash
# Install hey (HTTP load generator)
go install github.com/rakyll/hey@latest

# Run stress test
hey -n 100 -c 10 -m POST \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-3B-Instruct", "prompt": "Test", "max_tokens": 20}' \
  "http://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/completions"
```

---

## Troubleshooting

### Connection Refused

**Symptom:** `curl: (7) Failed to connect`

**Cause:** Gateway not accessible or LoadBalancer not provisioned

**Fix:**
```bash
# Check Gateway status
kubectl get gateway inference-gateway -n opendatahub

# Check LoadBalancer service
kubectl get svc inference-gateway-istio -n opendatahub

# If EXTERNAL-IP shows <pending>, wait a few minutes
```

### 404 Not Found

**Symptom:** `HTTP/1.1 404 Not Found`

**Cause:** Wrong path or HTTPRoute not created

**Fix:**
```bash
# Verify HTTPRoute exists
kubectl get httproute -n llm-d-inference-scheduling

# Check path in HTTPRoute
kubectl get httproute qwen2-3b-pattern1-kserve-route \
  -n llm-d-inference-scheduling \
  -o jsonpath='{.spec.rules[*].matches[*].path.value}'

# Should show: /llm-d-inference-scheduling/qwen2-3b-pattern1/...
```

### Timeout / No Response

**Symptom:** Request hangs or times out

**Cause:** Pod not ready or crashed

**Fix:**
```bash
# Check pod status
kubectl get pods -n llm-d-inference-scheduling

# Check pod logs
kubectl logs -n llm-d-inference-scheduling \
  deployment/qwen2-3b-pattern1-kserve --tail=50

# Check events
kubectl get events -n llm-d-inference-scheduling --sort-by='.lastTimestamp'
```

---

## Related Documentation

- [Cluster README](../README.md) - Cluster overview
- [Architecture](../docs/architecture.md) - Architecture details
- [Deployment Guide](../docs/deployment-guide.md) - Deployment procedures
- [Security Model](../docs/security-model.md) - Security configuration
