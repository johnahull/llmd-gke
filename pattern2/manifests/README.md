# Pattern 2 Multi-Model Routing Manifests

This directory contains Kubernetes manifests for deploying Pattern 2 multi-model serving with intelligent routing.

## Overview

Pattern 2 supports two routing approaches:

1. **Auto-Discovery (GPU)**: Single InferencePool with automatic model discovery
2. **BBR Header-Based Routing (TPU)**: Separate InferencePools with Body-Based Router

Both approaches achieved **100% routing accuracy** in benchmarks.

## Files

### Auto-Discovery Approach (GPU)

#### `httproute-unified.yaml`
HTTPRoute for GPU multi-model deployment with auto-discovery:
- Routes all traffic to single InferencePool (`gaie-pattern1`)
- Scheduler auto-discovers available models from backends
- Simple unified routing approach

### BBR Header-Based Routing (TPU)

#### `inferencepools-bbr.yaml`
Defines separate InferencePools for each model:
- **qwen-pool**: Routes to Qwen/Qwen2.5-3B-Instruct pods
- **phi-pool**: Routes to microsoft/Phi-3-mini-4k-instruct pods

Each pool uses the EPP (Endpoint Picker) service for intelligent endpoint selection.

### `httproutes-bbr.yaml`
Defines HTTPRoutes that match the `X-Gateway-Base-Model-Name` header injected by BBR:
- **qwen-model-route**: Matches header value `"Qwen/Qwen2.5-3B-Instruct"`
- **phi-model-route**: Matches header value `"microsoft/Phi-3-mini-4k-instruct"`

### `healthcheck-policy-fixed.yaml`
Defines GKE HealthCheckPolicies for each InferencePool:
- Uses `/health` endpoint (not `/`)
- Targets InferencePool resources (not Services)
- 15s interval and timeout

## Deployment

### Prerequisites: Deploy BBR

Before applying these manifests, you must deploy Body-Based Router (BBR) using Helm:

```bash
# Set environment variables
export NAMESPACE="llm-d-inference-scheduling"  # or "llm-d" for GPU
export GATEWAY_NAME="infra-pattern1-inference-gateway"

# Install BBR via Helm
helm install body-based-router \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing \
  --namespace $NAMESPACE \
  --set provider.name=gke \
  --set inferenceGateway.name=$GATEWAY_NAME
```

**See [../BBR_HELM_DEPLOYMENT.md](../BBR_HELM_DEPLOYMENT.md) for complete deployment instructions.**

### For GPU (Auto-Discovery Approach)

After deploying BBR and models with helmfile:

```bash
# Apply unified HTTPRoute
kubectl apply -f pattern2/manifests/httproute-unified.yaml -n llm-d
```

### For TPU (BBR Header-Based Routing)

After deploying BBR and models with helmfile:

```bash
# Create model allowlist ConfigMaps (required for BBR)
kubectl apply -f - <<EOF
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: qwen-allowlist
  namespace: llm-d-inference-scheduling
  labels:
    inference.networking.k8s.io/bbr-managed: "true"
data:
  baseModel: "Qwen/Qwen2.5-3B-Instruct"
  adapters: |
    # No adapters for base model
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: phi-allowlist
  namespace: llm-d-inference-scheduling
  labels:
    inference.networking.k8s.io/bbr-managed: "true"
data:
  baseModel: "microsoft/Phi-3-mini-4k-instruct"
  adapters: |
    # No adapters for base model
EOF

# Apply InferencePools
kubectl apply -f pattern2/manifests/inferencepools-bbr.yaml -n llm-d-inference-scheduling

# Apply HTTPRoutes
kubectl apply -f pattern2/manifests/httproutes-bbr.yaml -n llm-d-inference-scheduling

# Apply HealthCheckPolicies
kubectl apply -f pattern2/manifests/healthcheck-policy-fixed.yaml -n llm-d-inference-scheduling
```

## Architecture

### Auto-Discovery (GPU)
```
Client Request with model field
    ↓
Gateway → HTTPRoute (unified)
    ↓
InferencePool (gaie-pattern1)
    ↓
Scheduler (auto-discovers models from /v1/models)
    ↓
Routes to correct vLLM backend
```

### BBR Header-Based Routing (TPU)
```
Client Request with model field
    ↓
BBR Filter (extracts model from request body)
    ↓
Sets header: X-Gateway-Base-Model-Name
    ↓
HTTPRoute (matches header value)
    ↓
InferencePool (routes to correct model pool)
    ↓
EPP (selects best endpoint)
    ↓
vLLM Pod
```

## See Also

### Deployment Guides
- [BBR Helm Deployment](../BBR_HELM_DEPLOYMENT.md) - BBR deployment with official GKE Helm chart
- [Pattern 2 TPU Setup Guide](../llm-d-pattern2-tpu-setup.md) - Complete TPU deployment walkthrough
- [Pattern 2 GPU Setup Guide](../llm-d-pattern2-gpu-setup.md) - Complete GPU deployment walkthrough

### Analysis
- [BBR Benchmark Results](../PATTERN2_BBR_BENCHMARK_RESULTS.md) - Performance analysis
