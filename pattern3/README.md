# Pattern 3: N/S-Caching Scale-Out

**Intelligent routing with prefix cache awareness for high-throughput LLM inference**

Pattern 3 demonstrates horizontal scaling with intelligent request routing based on prefix cache hits, queue depth, and KV cache utilization, optimizing for both latency and throughput.

## Overview

**What it does:**
- Deploys 3 replicas of the same model for higher throughput
- Uses intelligent routing to maximize prefix cache hits
- Load-balances based on queue depth and KV cache utilization
- Achieves 16-17 req/s throughput with prefix caching enabled

**Key Innovation:** Prefix cache-aware routing directs requests with shared system prompts to the same replica, maximizing cache hits and reducing latency.

## Architecture

```
Internet → GKE Gateway → Inference Scheduler (EPP)
                              ↓
                    Intelligent routing based on:
                    1. Prefix cache hits (weight: 3.0)
                    2. Queue depth (weight: 1.0)
                    3. KV cache utilization (weight: 1.0)
                              ↓
              ┌───────────┬───────────┬───────────┐
              ↓           ↓           ↓           ↓
          Replica 1   Replica 2   Replica 3
          (T4 GPU)    (T4 GPU)    (T4 GPU)
```

**Routing Behavior:**
- Requests with shared prefix → routed to same replica (cache hit)
- High queue depth on replica → route to less busy replica
- High KV cache utilization → route to replica with more free memory

## Deployment Configuration

### Current Setup (GPU)

| Component | Count | Accelerator | Location | Cost/month |
|-----------|-------|-------------|----------|------------|
| **vLLM Replicas** | 3 | NVIDIA T4 GPU | us-central1-a | ~$450 |
| **Model** | Qwen/Qwen2.5-3B-Instruct | 3B params | - | - |
| **Gateway** | 1 | - | us-central1-a | ~$25 |
| **EPP** | 1 | - | us-central1-a | ~$10 |

**Total:** ~$485/month (GPU deployment)

### Configuration Parameters

```yaml
# GPU Memory Utilization
gpu_memory_utilization: 0.75  # 75% of 16 GiB = 12 GiB

# Prefix Caching
enable_prefix_caching: true  # Critical for pattern 3

# Routing Weights (EPP configuration)
scoring_plugins:
  - name: prefix-cache-scorer
    weight: 3.0  # Highest priority
  - name: queue-scorer
    weight: 1.0
  - name: kv-cache-utilization-scorer
    weight: 1.0
```

## Performance Benchmarks

### Throughput Results

**Without Prefix Caching:**
- Throughput: ~12-13 req/s
- Latency p95: ~800ms
- Cache hit rate: 0%

**With Prefix Caching (Pattern 3):**
- Throughput: **16-17 req/s** (+30% improvement)
- Latency p95: ~600ms (-25% reduction)
- Cache hit rate: 60-70% (with shared system prompts)

### Load Distribution

**Intelligent routing test (15 requests):**
```
Replica 1: 6 requests (40%)
Replica 2: 5 requests (33%)
Replica 3: 4 requests (27%)
```

**Result:** Balanced distribution with slight preference for replicas with cache hits.

### Benchmark Files

Available in [`benchmarks/`](./benchmarks/):
- `llm-d-pattern3-20260123_1406.html/json` - Standard throughput test
- `llm-d-pattern3-throughput-20260123_1410.html/json` - High throughput (50 concurrent)
- `llm-d-pattern3-high-concurrency-20260123_1411.html/json` - Stress test

## Quick Start

### Prerequisites
- GKE cluster with 3 GPU nodes (T4 recommended)
- Pattern 1 infrastructure deployed (Gateway, EPP)
- llm-d repository cloned

### Deploy Pattern 3

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d"
export RELEASE_NAME_POSTFIX="pattern3"

# Deploy infrastructure (if not from Pattern 1)
helmfile -e gke_gpu -n $NAMESPACE apply --selector type=infra

# Deploy model service with 3 replicas
helmfile -e gke_gpu -n $NAMESPACE apply --selector type=modelservice
```

### Apply HTTPRoute Manifest

After deploying infrastructure and model service:

```bash
# Apply HTTPRoute from manifests directory
kubectl apply -f pattern3/manifests/httproute-pattern3.yaml -n llm-d-inference-scheduling
```

See [`manifests/README.md`](./manifests/README.md) for details.

**Wait for deployment** (2-3 minutes per replica):
```bash
kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true -w
```

**Expected:** 3 pods in Running state

### Test Deployment

```bash
export GATEWAY_IP=$(kubectl get gateway infra-pattern3-inference-gateway \
  -n llm-d -o jsonpath='{.status.addresses[0].value}')

# Quick test
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is 2+2?",
    "max_tokens": 20
  }'
```

### Run Comprehensive Benchmark

```bash
cd /home/jhull/devel/rhaiis-test
./benchmarks/scripts/pattern3_comprehensive_benchmark.sh
```

**What it tests:**
- ✓ Health check (all replicas ready)
- ✓ Prefix cache routing (10 requests with shared system prompt)
- ✓ Load distribution (15 requests across replicas)
- ✓ Throughput (50 concurrent requests)
- ✓ Latency profile (P50/P95/P99)

## Routing Strategy Deep Dive

### Prefix Cache-Aware Routing

**How it works:**
1. Request arrives with prompt: "System: You are a helpful assistant.\nUser: What is AI?"
2. EPP checks all replicas for prefix cache hits on "System: You are a helpful assistant."
3. If Replica 2 has cached this prefix, it scores higher (weight: 3.0)
4. Request routed to Replica 2 → cache hit → faster response

**Benefits:**
- **Lower latency:** Cached prefix doesn't need recomputation
- **Higher throughput:** Less GPU compute per request
- **Better efficiency:** Maximize cache utilization across replicas

### Queue-Based Load Balancing

**How it works:**
1. EPP queries each replica's queue depth metric
2. Replica with fewer queued requests scores higher
3. Prevents hot-spotting on single replica

**Benefits:**
- **Even distribution:** Prevents overloading single replica
- **Lower wait time:** Requests routed to least busy replica
- **Better throughput:** All replicas utilized efficiently

### KV Cache Utilization

**How it works:**
1. EPP monitors KV cache memory usage per replica
2. Replica with more free KV cache scores higher
3. Prevents OOM errors from cache exhaustion

**Benefits:**
- **Stability:** Avoids cache eviction and recomputation
- **Predictability:** More consistent latency
- **Capacity:** Maximizes total KV cache across cluster

## Monitoring

### Check Replica Status

```bash
# Pod status
kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true

# GPU utilization
kubectl exec -n kube-system \
  $(kubectl get pods -n kube-system -l app=nvidia-gpu-device-plugin -o name | head -1) \
  -- nvidia-smi
```

### View EPP Routing Decisions

```bash
# EPP logs (shows scoring decisions)
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern3-epp --tail=100
```

**Look for:**
- `prefix-cache-scorer`: Score based on cache hits
- `queue-scorer`: Score based on queue depth
- `kv-cache-utilization-scorer`: Score based on cache memory

### View vLLM Metrics

```bash
# Port-forward to vLLM replica
kubectl port-forward -n llm-d \
  $(kubectl get pod -n llm-d -l llm-d.ai/inferenceServing=true -o name | head -1) \
  8000:8000

# Query metrics
curl http://localhost:8000/metrics | grep -E "(cache|queue|gpu)"
```

## Cost Optimization

### Scale Replicas Based on Load

```bash
# Scale down to 1 replica (off-hours)
kubectl scale deployment ms-pattern3-llm-d-modelservice-decode --replicas=1 -n llm-d

# Scale up to 3 replicas (peak hours)
kubectl scale deployment ms-pattern3-llm-d-modelservice-decode --replicas=3 -n llm-d
```

### Auto-scaling with HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: pattern3-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ms-pattern3-llm-d-modelservice-decode
  minReplicas: 1
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: gpu
      target:
        type: Utilization
        averageUtilization: 80
```

### Cost Comparison

| Replicas | Cost/month (GPU) | Throughput | Cost per req/s |
|----------|------------------|------------|----------------|
| 1 | ~$150 | ~5 req/s | $30/req/s |
| 3 | ~$450 | ~17 req/s | $26/req/s |
| 5 | ~$750 | ~25 req/s | $30/req/s |

**Sweet spot:** 3 replicas for best cost/performance ratio

## Troubleshooting

### Replicas Not Evenly Loaded

**Symptom:** One replica handling 80%+ of requests

**Cause:** Prefix cache routing directing all requests to same replica

**Diagnosis:**
```bash
# Check if all requests share same prefix
# View EPP logs for prefix-cache-scorer decisions
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern3-epp | grep prefix-cache
```

**Expected behavior:** This is normal if requests share common prefixes (e.g., same system prompt)

### Low Cache Hit Rate

**Symptom:** Expected 60-70% cache hits, seeing 10-20%

**Cause:** Requests don't share common prefixes

**Fix:**
1. Verify `enable_prefix_caching: true` in deployment
2. Check that requests actually share prefixes
3. Increase prefix-cache-scorer weight (current: 3.0, try: 5.0)

### GPU OOM Errors

**Symptom:** Pod crashes with "CUDA out of memory"

**Cause:** `gpu_memory_utilization` set too high

**Fix:** Reduce GPU memory utilization:
```yaml
# In values file
decode:
  containers:
  - args:
    - "--gpu-memory-utilization=0.65"  # Reduce from 0.75
```

### Slow First Request

**Symptom:** First request to each replica takes 2-3 seconds

**Cause:** Cold start - KV cache not yet populated

**Expected behavior:** Subsequent requests with shared prefix will be faster

## Documentation

- [`llm-d-pattern3-gpu-setup.md`](./llm-d-pattern3-gpu-setup.md) - Complete GPU setup guide
- [`llm-d-pattern3-tpu-setup.md`](./llm-d-pattern3-tpu-setup.md) - TPU deployment guide
- [`PATTERN3_QUICKSTART.md`](./PATTERN3_QUICKSTART.md) - Quick reference commands
- [`manifests/`](./manifests/) - Kubernetes manifests (HTTPRoute)
- [`benchmarks/`](./benchmarks/) - Benchmark results

## When to Use Pattern 3

### ✅ Good fit for:
- **High throughput requirements** (>10 req/s)
- **Shared system prompts** (chatbots, assistants)
- **Predictable load patterns** (business hours traffic)
- **Latency-sensitive applications** (interactive chat)

### ❌ Not ideal for:
- **Low traffic** (<5 req/s) - use Pattern 1 instead
- **Unique prompts** - cache hit rate will be low
- **Tight budget** - 3x cost of Pattern 1
- **Variable load** - consider auto-scaling or Pattern 1

## Scaling Strategies

### Horizontal Scaling (More Replicas)

**When to scale up:**
- Queue depth consistently >10 requests
- GPU utilization >90%
- Latency p95 >1 second

**How to scale:**
```bash
kubectl scale deployment ms-pattern3-llm-d-modelservice-decode --replicas=5 -n llm-d
```

**Trade-offs:**
- ➕ Higher throughput
- ➕ Better availability
- ➖ Higher cost
- ➖ Lower cache hit rate (distributed across more replicas)

### Vertical Scaling (Bigger GPUs)

**Alternative:** Use A100 or H100 GPUs for single replica

**Trade-offs:**
- ➕ Higher throughput per replica
- ➕ Better cache hit rate (single replica)
- ➖ Much higher cost per GPU
- ➖ Lower availability (single point of failure)

## Advanced Configuration

### Tuning Routing Weights

Adjust EPP scoring plugin weights based on workload:

**Latency-optimized (favor cache hits):**
```yaml
prefix-cache-scorer: 5.0  # Maximize cache hits
queue-scorer: 1.0
kv-cache-utilization-scorer: 1.0
```

**Throughput-optimized (favor load balancing):**
```yaml
prefix-cache-scorer: 1.0
queue-scorer: 3.0  # Maximize even distribution
kv-cache-utilization-scorer: 2.0
```

**Capacity-optimized (favor available memory):**
```yaml
prefix-cache-scorer: 1.0
queue-scorer: 1.0
kv-cache-utilization-scorer: 5.0  # Maximize available cache
```

### GPU Memory Tuning

```yaml
# Conservative (more stability)
gpu_memory_utilization: 0.65
max_model_len: 2048

# Aggressive (more capacity)
gpu_memory_utilization: 0.85
max_model_len: 4096
```

**Recommendation:** Start conservative, increase gradually while monitoring OOM errors.

## Resources

**Official Documentation:**
- [llm-d Architecture - N/S-Caching](https://llm-d.ai/docs/architecture/Patterns/ns-caching)
- [Gateway API Inference Extension - EPP Scoring](https://gateway-api-inference-extension.sigs.k8s.io/)
- [vLLM Prefix Caching](https://docs.vllm.ai/en/latest/automatic_prefix_caching/apc.html)

**Related Patterns:**
- [Pattern 1: Baseline Single Replica](../pattern1/) - Foundation for scale-out
- [Pattern 2: Multi-Model BBR Routing](../pattern2/) - Multiple models, single endpoint

## Summary

Pattern 3 demonstrates **horizontal scaling with intelligent routing** for high-throughput LLM inference:

✅ **Architecture:** 3 replicas with prefix cache-aware routing
✅ **Performance:** 16-17 req/s throughput (3x Pattern 1)
✅ **Efficiency:** 60-70% cache hit rate with shared prompts
✅ **Scalability:** Near-linear throughput scaling with replicas
✅ **Production-Ready:** Validated with comprehensive benchmarks

**Key Insight:** Intelligent routing based on prefix cache hits maximizes both throughput and efficiency by directing requests to replicas with cached state.
