# Pattern 1: Single Replica Baseline Deployment

**Kubernetes-native LLM inference with intelligent scheduling on GKE**

Pattern 1 establishes the foundational deployment architecture for llm-d on Google Cloud, serving as the baseline for multi-model (Pattern 2) and scale-out (Pattern 3) configurations.

## Overview

**What it does:**
- Deploys a single LLM model (Qwen/Qwen2.5-3B-Instruct) on GKE
- Provides intelligent inference scheduling via EPP (Endpoint Picker)
- Exposes OpenAI-compatible API via Gateway API
- Supports both NVIDIA GPU and Google TPU accelerators

**Deployment Options:**
1. **KServe LLMInferenceService** (Recommended) - Istio + KServe + llm-d integration
2. **Helm-based** (Legacy) - Direct llm-d Helm chart deployment

**Architecture:**
```
Internet → Gateway → Inference Scheduler (EPP) → vLLM Pod
                         ↓
               Intelligent routing based on:
               - Queue depth
               - KV cache utilization
               - Prefix cache hits
```

## Key Components

| Component | Purpose | Port |
|-----------|---------|------|
| **vLLM Pod** | Model serving engine (JAX/XLA for TPU, CUDA for GPU) | 8000 |
| **EPP (Endpoint Picker)** | Intelligent request router with metric-based scoring | 9002 |
| **Gateway** | Kubernetes-native load balancer (GKE managed) | 80 |
| **InferencePool** | Custom resource managing inference endpoints | - |

## Deployment Targets

### GPU Deployment (NVIDIA T4)
- **Location:** `us-central1-a`
- **Accelerator:** NVIDIA T4 GPU (13.12 GiB memory)
- **Backend:** vLLM + XFormers (T4 doesn't support FlashAttention-2)
- **Cost:** ~$150/month per GPU node
- **Setup Guide:** [`llm-d-pattern1-gpu-setup.md`](./llm-d-pattern1-gpu-setup.md)

### TPU Deployment (TPU v6e)
- **Location:** `europe-west4-a`
- **Accelerator:** TPU v6e-1 (4 chips, 2x2 topology)
- **Backend:** vLLM + JAX/XLA
- **Cost:** ~$3,760/month per TPU node
- **Setup Guide:** [`llm-d-pattern1-tpu-setup.md`](./llm-d-pattern1-tpu-setup.md)

## Quick Start

### Option 1: KServe LLMInferenceService (Recommended)

The KServe-based deployment provides:
- **Automated resource creation** - HTTPRoute and InferencePool auto-created
- **Declarative configuration** - Single YAML manifest for entire deployment
- **Istio integration** - Advanced traffic management and observability
- **Simplified lifecycle** - Autoscaling, canary deployments, monitoring built-in

**Prerequisites:**
- llm-d-infra-xks operators installed (cert-manager, sail-operator, KServe)
- Gateway configured in opendatahub namespace
- See [`istio-kserve-llmd-architecture.md`](./istio-kserve-llmd-architecture.md) for complete guide

**Deploy:**
```bash
# Create namespace and secrets (one-time setup)
export NAMESPACE=llm-d-inference-scheduling
kubectl create namespace $NAMESPACE

kubectl create secret generic redhat-pull-secret \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson=~/.config/containers/auth.json \
  -n $NAMESPACE

kubectl create secret generic hf-token \
  --from-literal=HF_TOKEN=<your-token> \
  -n $NAMESPACE

# Deploy LLMInferenceService
kubectl apply -f pattern1/manifests/llmisvc-pattern1-tpu.yaml
```

**Verify:**
```bash
# Check status
kubectl get llmisvc qwen2-3b-pattern1 -n llm-d-inference-scheduling

# Test inference
GATEWAY_IP=$(kubectl get gateway inference-gateway -n opendatahub \
  -o jsonpath='{.status.addresses[0].value}')

curl -X POST "http://${GATEWAY_IP}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Host: qwen2-3b-pattern1.llm-d-inference-scheduling.svc.cluster.local" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [{"role": "user", "content": "What is Kubernetes?"}],
    "max_tokens": 100
  }'
```

For complete installation and troubleshooting, see [`istio-kserve-llmd-architecture.md`](./istio-kserve-llmd-architecture.md).

### Option 2: Helm-based Deployment (Legacy)

**Prerequisites:**
- GKE cluster with GPU or TPU node pool
- Red Hat registry credentials
- Hugging Face token
- llm-d repository cloned

**Deploy (TPU):**
```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d-inference-scheduling"
export RELEASE_NAME_POSTFIX="pattern1"

# Deploy infrastructure (Gateway, EPP)
helmfile -e gke_tpu -n $NAMESPACE apply --selector type=infra

# Deploy model service
helmfile -e gke_tpu -n $NAMESPACE apply --selector type=modelservice
```

**Apply HTTPRoute Manifest:**

After deploying infrastructure and model service:
```bash
# Apply HTTPRoute from manifests directory
kubectl apply -f pattern1/manifests/httproute-pattern1.yaml -n llm-d-inference-scheduling
```

See [`manifests/README.md`](./manifests/README.md) for details.

**Test Deployment:**
```bash
export GATEWAY_IP=$(kubectl get gateway infra-pattern1-inference-gateway \
  -n llm-d-inference-scheduling -o jsonpath='{.status.addresses[0].value}')

curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "Explain quantum computing in one sentence:",
    "max_tokens": 50
  }'
```

## Performance Baseline

### TPU v6e Results
- **Latency (p95):** ~500ms (cold), ~300ms (warm with KV cache)
- **Throughput:** 2-3 req/s (serial), 15-20 req/s (concurrent)
- **GPU Memory:** 32 GB HBM (TPU v6e)
- **Startup Time:** ~7-10 minutes (TPU init + XLA compilation)

### T4 GPU Results
- **Latency (p95):** ~600ms
- **Throughput:** ~5 req/s (serial), ~20 req/s (concurrent)
- **GPU Memory:** 13.12 GiB (90% utilization)
- **Startup Time:** ~2-3 minutes

## Benchmark Results

Pattern 1 benchmark results are available in [`benchmarks/`](./benchmarks/):
- `llm-d-pattern1-20260122.html` - HTML report
- `llm-d-pattern1-20260122.json` - JSON metrics

## Monitoring

### Check Deployment Status
```bash
# Pods
kubectl get pods -n llm-d-inference-scheduling

# Gateway
kubectl get gateway -n llm-d-inference-scheduling

# InferencePool
kubectl get inferencepool -n llm-d-inference-scheduling
```

### View Metrics
```bash
# EPP metrics (scheduler scoring)
curl http://${GATEWAY_IP}:9090/metrics

# vLLM metrics (model serving)
kubectl port-forward -n llm-d-inference-scheduling \
  svc/ms-pattern1-llm-d-modelservice 8000:8000
curl http://localhost:8000/metrics
```

## Cost Optimization

### Scale to Zero
```bash
# Scale deployment
kubectl scale deployment ms-pattern1-llm-d-modelservice-decode --replicas=0 \
  -n llm-d-inference-scheduling

# Scale TPU node pool
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a \
  --project=ecoeng-llmd
```

**Cost while scaled to 0:** ~$113/month (CPU node + Gateway only)

## Next Steps

Pattern 1 serves as the foundation for:

- **Pattern 2**: Multi-model deployment with BBR routing ([`../pattern2/`](../pattern2/))
  - Adds second model (Phi-3-mini)
  - 100% routing accuracy via header-based routing
  - Shared infrastructure (Gateway, EPP)

- **Pattern 3**: N/S-Caching Scale-Out ([`../pattern3/`](../pattern3/))
  - 3 replicas for higher throughput
  - Prefix cache-aware routing
  - Load balancing across replicas

## Troubleshooting

### Pod CrashLoopBackOff
**Symptom:** vLLM pod crashes during startup

**Common Causes:**
1. Out of memory (reduce `--max-model-len`)
2. Missing TPU drivers (TPU: use `v2-alpha-tpuv6e` image)
3. Wrong accelerator type (check node labels)

**Fix:** Check pod logs:
```bash
kubectl logs -n llm-d-inference-scheduling <pod-name>
```

### Gateway Not Accessible
**Symptom:** External IP shows `<pending>` or connection refused

**Fix:**
```bash
# Check Gateway status
kubectl describe gateway infra-pattern1-inference-gateway \
  -n llm-d-inference-scheduling

# Check HTTPRoute binding
kubectl get httproute -n llm-d-inference-scheduling
```

### Model Load Timeout
**Symptom:** Pod stuck in ContainerCreating or startup probe failing

**Cause:** Model download or XLA compilation taking too long

**Fix:** Increase `startupProbe.failureThreshold` in override file

## Documentation

### KServe-based Deployment
- [`istio-kserve-llmd-architecture.md`](./istio-kserve-llmd-architecture.md) - **Complete KServe + Istio architecture guide** (Recommended)
- [`manifests/llmisvc-pattern1-tpu.yaml`](./manifests/llmisvc-pattern1-tpu.yaml) - LLMInferenceService manifest

### Helm-based Deployment (Legacy)
- [`llm-d-pattern1-tpu-setup.md`](./llm-d-pattern1-tpu-setup.md) - Complete TPU setup guide
- [`llm-d-pattern1-gpu-setup.md`](./llm-d-pattern1-gpu-setup.md) - Complete GPU setup guide
- [`manifests/httproute-pattern1.yaml`](./manifests/httproute-pattern1.yaml) - HTTPRoute manifest
- [`manifests/README.md`](./manifests/README.md) - Manifest documentation

### Benchmarks
- [`benchmarks/`](./benchmarks/) - Benchmark results and reports

## Architecture Decisions

### Why EPP (Endpoint Picker)?
- Intelligent routing beyond simple round-robin
- Metric-based scoring (queue depth, KV cache, prefix cache)
- Optimizes for both latency and throughput

### Why Gateway API?
- Kubernetes-native (no external load balancer needed on GKE)
- InferencePool integration
- HTTPRoute for flexible routing rules

### Why vLLM?
- Production-grade LLM serving engine
- Supports GPU and TPU accelerators
- OpenAI-compatible API
- Continuous batching for efficiency

## Resources

**External Documentation:**
- [llm-d Official Docs](https://llm-d.ai/)
- [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/)
- [vLLM Documentation](https://docs.vllm.ai/)
- [GKE AI Labs](https://gke-ai-labs.dev)

**Related Patterns:**
- [Pattern 2: Multi-Model BBR Routing](../pattern2/) - Extend with multiple models
- [Pattern 3: N/S-Caching Scale-Out](../pattern3/) - Scale to multiple replicas
