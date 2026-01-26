# RHAIIS vLLM Deployment on Google Cloud

Deployment configurations and benchmarking tools for running **RHAIIS (Red Hat AI Inference Services)** vLLM workloads on Google Cloud infrastructure with **llm-d** intelligent routing.

## Overview

This repository demonstrates three deployment patterns for large language model (LLM) inference at scale:

- **Pattern 1**: Single replica baseline deployment
- **Pattern 2**: Multi-model serving with intelligent routing
- **Pattern 3**: N/S-Caching Scale-Out with prefix caching (3 replicas)

Each pattern supports both **NVIDIA GPU** (T4) and **Google Cloud TPU** (v6e) accelerators.

## Repository Structure

```
rhaiis-test/
├── helm-configs/                # Custom llm-d Helm configurations (tracked)
│   ├── helmfile.yaml.gotmpl     # Modified helmfile with pattern conditionals
│   ├── pattern-overrides/       # Pattern-specific Helm value overrides
│   │   ├── pattern1-overrides.yaml
│   │   ├── pattern1-tpu-overrides.yaml
│   │   ├── pattern2-tpu-overrides.yaml
│   │   └── pattern3-gpu-overrides.yaml
│   └── README.md                # Setup instructions
├── pattern1/                    # Pattern 1: Single Replica Baseline
│   ├── llm-d-pattern1-gpu-setup.md
│   ├── llm-d-pattern1-tpu-setup.md
│   ├── manifests/               # Kubernetes manifests
│   │   ├── httproute-pattern1.yaml
│   │   └── README.md
│   └── benchmarks/
├── pattern2/                    # Pattern 2: Multi-Model Serving
│   ├── llm-d-pattern2-gpu-setup.md
│   ├── llm-d-pattern2-tpu-setup.md
│   ├── manifests/               # Kubernetes manifests
│   │   ├── httproute-unified.yaml        # GPU auto-discovery
│   │   ├── inferencepools-bbr.yaml       # TPU BBR pools
│   │   ├── httproutes-bbr.yaml           # TPU BBR routes
│   │   ├── healthcheck-policy-fixed.yaml # TPU health checks
│   │   └── README.md
│   └── benchmarks/
├── pattern3/                    # Pattern 3: N/S-Caching Scale-Out
│   ├── llm-d-pattern3-gpu-setup.md
│   ├── llm-d-pattern3-tpu-setup.md
│   ├── PATTERN3_QUICKSTART.md
│   └── benchmarks/
├── benchmarks/                  # Unified benchmarking infrastructure
│   ├── python/                  # Python benchmark scripts
│   ├── scripts/                 # Shell benchmark scripts
│   ├── config/                  # Target configurations
│   └── results/                 # Benchmark results (HTML/JSON)
├── llm-d/                       # llm-d repository (clone separately, ignored)
└── rhaiis-test/                 # Legacy testing configurations
    ├── rhaiis-nvidia.yaml       # Pre-llm-d GPU deployment
    ├── rhaiis-tpu.yaml          # Pre-llm-d TPU deployment
    └── *.md                     # Original setup guides
```

## Deployment Patterns

### Pattern 1: Single Replica Baseline

- **Purpose**: Simple baseline deployment for testing and cost-effective inference
- **Configuration**: 1 replica with vLLM on single GPU/TPU
- **Use Case**: Development, testing, low-traffic applications
- **Cost**: ~$365/month (GPU) or ~$3,650/month (TPU)
- **Throughput**: ~1 req/s

📖 **Guides**:
- [GPU Setup](pattern1/llm-d-pattern1-gpu-setup.md)
- [TPU Setup](pattern1/llm-d-pattern1-tpu-setup.md)

### Pattern 2: Multi-Model Serving

- **Purpose**: Serve multiple models with intelligent routing
- **Configuration**: Multiple deployments with model-aware load balancing
- **Use Case**: Applications requiring different models for different tasks
- **Features**: Model selection based on request, independent scaling per model

📖 **Guides**:
- [GPU Setup](pattern2/llm-d-pattern2-gpu-setup.md)
- [TPU Setup](pattern2/llm-d-pattern2-tpu-setup.md)

### Pattern 3: N/S-Caching Scale-Out (Recommended)

- **Purpose**: High-throughput inference with intelligent prefix caching
- **Configuration**: 3 replicas with prefix-cache-aware routing
- **Use Case**: Production workloads with repeated prompts (RAG, chatbots, agents)
- **Cost**: ~$1,095/month (GPU) or ~$10,950/month (TPU)
- **Throughput**: ~17 req/s (GPU), ~25 req/s (TPU)
- **Cost Efficiency**: 65% cheaper per request than Pattern 1

**Key Features**:
- vLLM prefix caching for efficient repeated prompt handling
- Intelligent routing (prefix-cache-scorer, kv-cache-utilization, queue-aware)
- 17× throughput improvement over Pattern 1 (GPU)

📖 **Guides**:
- [GPU Setup](pattern3/llm-d-pattern3-gpu-setup.md)
- [TPU Setup](pattern3/llm-d-pattern3-tpu-setup.md)
- [Quick Start](pattern3/PATTERN3_QUICKSTART.md)

## Quick Start

### Prerequisites

1. **Google Cloud Project**: `ecoeng-llmd` with appropriate quotas
2. **GKE Cluster**: For GPU or TPU deployments
3. **Credentials**:
   - Red Hat registry: `11009103-jhull-svc-pull-secret.yaml`
   - Hugging Face token: `huggingface-token-secret.yaml` (create from template)

```bash
# Create Hugging Face token secret
cp huggingface-token-secret.yaml.template huggingface-token-secret.yaml
# Edit and add your token, then apply
kubectl apply -f huggingface-token-secret.yaml
```

### Setup llm-d

The deployment uses llm-d Helm charts with custom pattern configurations:

```bash
# 1. Clone llm-d (if not already done)
git clone https://github.com/llm-d/llm-d.git

# 2. Copy custom configurations
cp helm-configs/pattern-overrides/*.yaml \
   llm-d/guides/inference-scheduling/ms-inference-scheduling/

cp helm-configs/helmfile.yaml.gotmpl \
   llm-d/guides/inference-scheduling/
```

See [helm-configs/README.md](helm-configs/README.md) for detailed setup instructions.

### Deploy Pattern 3 (Recommended)

**GPU Deployment**:
```bash
# Review the setup guide
cat pattern3/llm-d-pattern3-gpu-setup.md

# Deploy using helmfile
cd llm-d/guides/inference-scheduling
helmfile apply -e gke -n llm-d --selector release=pattern3

# Run comprehensive benchmark
./benchmarks/scripts/pattern3_comprehensive_benchmark.sh
```

**Quick Test**:
```bash
# Get gateway IP
kubectl get gateway -n llm-d

# Test inference
curl -X POST http://GATEWAY_IP/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is the capital of France?",
    "max_tokens": 50
  }'
```

## Benchmarking

The repository includes comprehensive benchmarking tools for performance testing:

### Sync Benchmarks (Shell Scripts)

```bash
# Pattern 3 comprehensive test suite
./benchmarks/scripts/pattern3_comprehensive_benchmark.sh

# Compare multiple targets
./benchmarks/scripts/compare_targets.sh llm-d-pattern1-gpu llm-d-pattern3-gpu

# Apache Bench style testing
./benchmarks/scripts/ab_benchmark.sh http://GATEWAY_IP 100 10
```

### Async Benchmarks (Python)

```bash
# Activate virtual environment
source /home/jhull/devel/venv/bin/activate

# Run async benchmark with concurrency
python benchmarks/python/benchmark_async.py \
  --target llm-d-pattern3-gpu \
  --scenario latency_benchmark \
  --num-requests 100 \
  --concurrency 50

# Results saved to benchmarks/results/ (HTML + JSON)
```

### Benchmark Targets

All targets are configured in [`benchmarks/config/targets.yaml`](benchmarks/config/targets.yaml):

- `llm-d-pattern1-gpu` - Pattern 1 GPU baseline
- `llm-d-pattern3-gpu` - Pattern 3 GPU (3× T4)
- `tpu-v6e` - TPU v6e deployment
- Local targets: `ollama-local`, `lmstudio-local`, `llamacpp-local`

## Architecture

### llm-d Framework

This repository uses **llm-d**, a Kubernetes-native distributed LLM inference framework with:

- **Gateway API Integration**: Kubernetes Gateway API for intelligent routing
- **InferencePool CRD**: Custom resource for managing inference replicas
- **Intelligent Routing**: Prefix-cache-aware, KV-cache-aware, queue-aware load balancing
- **Model Service**: Helm-based model deployment with monitoring

### GPU Backend (NVIDIA T4)

- **Image**: `ghcr.io/llm-d/llm-d-cuda:v0.4.0`
- **Backend**: vLLM with FLASHINFER (T4 optimized)
- **Memory**: 16GB per GPU, 0.75 utilization
- **Features**: CUDA graph capture, prefix caching, torch compile cache

### TPU Backend (v6e)

- **Image**: `vllm/vllm-tpu:v0.11.1`
- **Backend**: vLLM with JAX/XLA
- **Topology**: 2×2 (4 chips)
- **Features**: XLA precompilation, prefix caching, HBM optimization

## Cost Analysis

### Pattern 3 Comparison (Monthly, 24/7)

| Accelerator | Config | Monthly Cost | Throughput | Cost/1M Req |
|-------------|--------|--------------|------------|-------------|
| **GPU (3× T4)** | Pattern 3 | $1,095 | ~17 req/s | $4.36 |
| **TPU (3× v6e-4t)** | Pattern 3 | $10,950 | ~25 req/s | $3.15 |
| **GPU (1× T4)** | Pattern 1 | $365 | ~1 req/s | $12.50 |

**Key Insights**:
- Pattern 3 GPU is **17× faster** than Pattern 1 for only 3× the cost
- Pattern 3 GPU is **14× cheaper** than TPU for similar architecture
- TPUs offer higher absolute throughput but at premium cost

## Monitoring

### Real-Time Monitoring

```bash
# Watch pod status
watch -n 2 'kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true'

# View vLLM metrics
kubectl port-forward -n llm-d deployment/ms-pattern3-llm-d-modelservice-decode 8000:8000
curl http://localhost:8000/metrics

# Check routing decisions
kubectl logs -n llm-d -f deployment/gaie-pattern3-epp | grep -E "score|endpoint"

# GPU utilization (for GPU deployments)
kubectl exec -n kube-system \
  $(kubectl get pods -n kube-system -l app=nvidia-gpu-device-plugin -o name | head -1) \
  -- nvidia-smi
```

### Backend Health

```bash
# Check GCP Load Balancer health
gcloud compute backend-services get-health <BACKEND_SERVICE_NAME> \
  --region=us-central1 \
  --project=ecoeng-llmd
```

## Key Features

✅ **Production-Ready Deployments**: Battle-tested configurations for GPU and TPU
✅ **Intelligent Routing**: Prefix-cache-aware load balancing for optimal performance
✅ **Cost Optimization**: Scale to zero support, node pool management
✅ **Comprehensive Benchmarking**: Sync and async performance testing tools
✅ **Multi-Model Support**: Serve different models for different use cases (Pattern 2)
✅ **Observability**: Prometheus metrics, detailed logging, health checks
✅ **Documentation**: Step-by-step guides for each pattern and accelerator type

## Supported Models

### Currently Deployed

- **Pattern 1 GPU**: `google/gemma-2b-it`
- **Pattern 2 GPU**: `microsoft/Phi-3-mini-4k-instruct`
- **Pattern 3 GPU/TPU**: `Qwen/Qwen2.5-3B-Instruct`

### Tested Models

**Small (2-3B)**:
- `google/gemma-2b-it`
- `microsoft/Phi-3-mini-4k-instruct` (3.8B)
- `Qwen/Qwen2.5-3B-Instruct`

**Medium (7-9B)**:
- `mistralai/Mistral-7B-Instruct-v0.3`
- `meta-llama/Llama-3.1-8B-Instruct` (requires license)
- `google/gemma-2-9b-it`

**Specialized**:
- `codellama/CodeLlama-7b-Instruct-hf`

## Troubleshooting

### Common Issues

**Pods stuck in Pending**: Not enough GPU/TPU nodes
```bash
# Scale GPU node pool
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 3 --zone us-central1-a
```

**OOM errors during startup**: GPU memory utilization too high
- Solution: Already tuned to 0.75 in Pattern 3 GPU config

**Gateway routing failure**: Old HTTPRoute conflicts
```bash
# Delete conflicting routes
kubectl delete httproute -n llm-d <old-route-name>
```

**Image pull errors**: Missing registry secret
```bash
# Verify secret exists
kubectl get secret -n llm-d 11009103-jhull-svc-pull-secret
```

## Documentation

- **Project Instructions**: [`CLAUDE.md`](CLAUDE.md) - Comprehensive guide for Claude Code
- **Benchmarking Guide**: [`benchmarks.md`](benchmarks.md)
- **Pattern Guides**: See `pattern1/`, `pattern2/`, `pattern3/` directories
- **llm-d Documentation**: [llm-d.ai](https://llm-d.ai/)
- **Google AI on GKE**: [gke-ai-labs.dev](https://gke-ai-labs.dev)

## Contributing

When making changes:

1. Test deployments in development namespace first
2. Run benchmarks before and after changes
3. Update relevant pattern documentation
4. Follow existing naming conventions
5. Keep secrets in `.gitignore` (use `.template` files for sharing)

## License

This repository contains deployment configurations and documentation for Red Hat AI Inference Services (RHAIIS) on Google Cloud infrastructure.

---

**Last Updated**: January 2026
**Project**: `ecoeng-llmd`
**Maintainer**: Red Hat AI Engineering
