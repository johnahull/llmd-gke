# Pattern 2: Multi-Model Deployment with BBR Routing

**100% routing accuracy using Body Based Router (BBR) and header-based HTTPRoute matching**

Pattern 2 extends Pattern 1 to serve multiple LLM models via a single Gateway endpoint, demonstrating production-ready multi-model routing with zero routing errors.

## Overview

**What it does:**
- Serves 2+ models through single Gateway endpoint
- Uses BBR to extract model name from request body
- Routes via HTTPRoute header matching (supports model names with slashes)
- Achieves 100% routing accuracy (validated with 420+ test requests)
- Maintains separate InferencePools for intelligent endpoint picking per model

**Key Innovation:** HTTP header values (unlike Kubernetes labels) can contain slashes, enabling exact model name matching for models like `Qwen/Qwen2.5-3B-Instruct`.

## Architecture

```
Client Request: {"model": "Qwen/Qwen2.5-3B-Instruct", "prompt": "..."}
         ↓
Gateway (35.214.154.17)
         ↓
BBR (body-based-router:9004)
  - Parses request JSON body
  - Extracts: model = "Qwen/Qwen2.5-3B-Instruct"
  - Injects header: X-Gateway-Base-Model-Name: "Qwen/Qwen2.5-3B-Instruct"
         ↓
HTTPRoute (qwen-model-route)
  - Matches header value (slashes allowed!)
  - Routes to: qwen-pool InferencePool
         ↓
EPP (gaie-pattern1-epp:9002)
  - Picks best endpoint in qwen-pool
  - Uses: queue-scorer, kv-cache-scorer, prefix-cache-scorer
         ↓
vLLM Pod (Qwen model)
  - Serves request
  - Returns response → 100% success
```

## Deployed Models

### Current Configuration (2 models)

| Model | Size | InferencePool | Accelerator | Cost/month |
|-------|------|---------------|-------------|------------|
| **Qwen/Qwen2.5-3B-Instruct** | 3B | qwen-pool | TPU v6e-1 (4 chips) | ~$3,760 |
| **microsoft/Phi-3-mini-4k-instruct** | 3.8B | phi-pool | TPU v6e-1 (4 chips) | ~$3,760 |

**Total:** ~$7,520/month (can scale to 0 when not in use)

## Routing Performance

### Validated Accuracy: 100%

| Test Scenario | Requests | Qwen Success | Phi-3 Success | Total Accuracy |
|---------------|----------|--------------|---------------|----------------|
| Quick Validation | 20 | 10/10 (100%) | 10/10 (100%) | **100%** |
| Latency Benchmark | 200 | 100/100 (100%) | 100/100 (100%) | **100%** |
| Concurrent (c=10) | 200 | 100/100 (100%) | 100/100 (100%) | **100%** |
| **Total** | **420** | **210/210** | **210/210** | **100%** |

**Zero routing errors** - no "model does not exist", no "no healthy upstream", no client retries needed.

### Throughput Benchmarks

**Qwen/Qwen2.5-3B-Instruct:**
- Serial (c=1): 2.28 req/s, 513ms p95 latency
- Concurrent (c=10): **21.19 req/s**, 673ms p95 latency
- Throughput scaling: 9.3x (near-linear)

**microsoft/Phi-3-mini-4k-instruct:**
- Serial (c=1): 1.99 req/s, 554ms p95 latency
- Concurrent (c=10): **16.32 req/s**, 736ms p95 latency
- Throughput scaling: 8.2x (near-linear)

**Key Findings:**
- ✅ 100% routing accuracy across all scenarios
- ✅ Qwen 12% faster throughput than Phi-3 under load
- ✅ Graceful latency degradation (31-33% increase under 10x load)
- ✅ MLPerf Standard PASS for both models

## Quick Start

### Prerequisites
- Pattern 1 infrastructure deployed (Gateway, EPP)
- 2 TPU v6e nodes available (or 2 GPU nodes)
- Helm 3.x installed
- Models pods deployed and labeled

### Deploy Pattern 2

#### Step 1: Deploy BBR (Body-Based Router)

Deploy BBR using the official GKE Helm chart:

```bash
# Set environment variables
export NAMESPACE="llm-d-inference-scheduling"  # or "llm-d" for GPU
export GATEWAY_NAME="infra-pattern1-inference-gateway"  # or your gateway name

# Install BBR via Helm
helm install body-based-router \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing \
  --namespace $NAMESPACE \
  --set provider.name=gke \
  --set inferenceGateway.name=$GATEWAY_NAME

# Wait for BBR to be ready
kubectl wait --for=condition=Ready pod \
  -l app.kubernetes.io/name=body-based-routing \
  -n $NAMESPACE \
  --timeout=120s
```

**See [BBR_HELM_DEPLOYMENT.md](./BBR_HELM_DEPLOYMENT.md) for detailed instructions and troubleshooting.**

#### Step 2: Scale Up Cluster and Deploy Models

```bash
# 1. Scale up TPU node pool to 2 nodes
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 2 \
  --zone europe-west4-a \
  --project=ecoeng-llmd

# 2. Deploy both model pods
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

# Deploy Pattern 1 (Qwen)
export RELEASE_NAME_POSTFIX="pattern1"
helmfile -e gke_tpu -n $NAMESPACE apply --selector type=modelservice

# Deploy Pattern 2 (Phi-3)
export RELEASE_NAME_POSTFIX="pattern2"
helmfile -e gke_tpu -n $NAMESPACE apply --selector type=modelservice

# 3. Label pods for InferencePool selection
POD_QWEN=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/instance=ms-pattern1 -o jsonpath='{.items[0].metadata.name}')
POD_PHI=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/instance=ms-pattern2 -o jsonpath='{.items[0].metadata.name}')

kubectl label pod $POD_QWEN model-instance=qwen -n $NAMESPACE --overwrite
kubectl label pod $POD_PHI model-instance=phi -n $NAMESPACE --overwrite
```

#### Step 3: Create Model Allowlist ConfigMaps

**Critical:** BBR requires allowlist ConfigMaps to map model names.

```bash
# For TPU (Qwen + Phi-3)
kubectl apply -f - <<EOF
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: qwen-allowlist
  namespace: $NAMESPACE
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
  namespace: $NAMESPACE
  labels:
    inference.networking.k8s.io/bbr-managed: "true"
data:
  baseModel: "microsoft/Phi-3-mini-4k-instruct"
  adapters: |
    # No adapters for base model
EOF
```

#### Step 4: Deploy InferencePools, HTTPRoutes, and HealthCheckPolicies

```bash
# For TPU (BBR approach):
kubectl apply -f pattern2/manifests/inferencepools-bbr.yaml -n $NAMESPACE
kubectl apply -f pattern2/manifests/httproutes-bbr.yaml -n $NAMESPACE
kubectl apply -f pattern2/manifests/healthcheck-policy-fixed.yaml -n $NAMESPACE

# For GPU (auto-discovery approach):
kubectl apply -f pattern2/manifests/httproute-unified.yaml -n llm-d

# Wait 2-3 minutes for GKE health checks to propagate

# See manifests/README.md for details on both approaches
```

### Test Multi-Model Routing

```bash
export GATEWAY_IP=35.214.154.17

# Test Qwen model
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is machine learning?",
    "max_tokens": 50
  }'

# Test Phi-3 model
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "prompt": "What is machine learning?",
    "max_tokens": 50
  }'
```

**Expected:** Both requests succeed with responses from their respective models.

## Key Components

### BBR (Body Based Router)
**Purpose:** Extract model name from request body and inject as HTTP header

**How it works:**
1. Intercepts requests via Envoy ext_proc filter
2. Parses JSON body: `{"model": "Qwen/Qwen2.5-3B-Instruct", ...}`
3. Injects header: `X-Gateway-Base-Model-Name: "Qwen/Qwen2.5-3B-Instruct"`
4. Clears route cache to force HTTPRoute re-evaluation

**Deployment:**
- Helm chart: `registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing`
- See [BBR_HELM_DEPLOYMENT.md](./BBR_HELM_DEPLOYMENT.md) for complete deployment guide

### HTTPRoute Header Matching
**Purpose:** Route requests based on BBR-injected header

**Configuration:**
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: qwen-model-route
spec:
  rules:
  - matches:
    - headers:
      - name: X-Gateway-Base-Model-Name
        value: "Qwen/Qwen2.5-3B-Instruct"  # Slashes OK!
    backendRefs:
    - kind: InferencePool
      name: qwen-pool
```

**Why header matching?**
- HTTP headers support slashes in values (Kubernetes labels don't)
- Enables exact model name matching
- Production-ready Gateway API standard

### InferencePools with Simple Selectors
**Purpose:** Group endpoints for each model

**Configuration:**
```yaml
apiVersion: inference.networking.k8s.io/v1
kind: InferencePool
metadata:
  name: qwen-pool
spec:
  selector:
    matchLabels:
      model-instance: qwen  # Simple selector, no slashes
  endpointPickerRef:
    kind: Service
    name: gaie-pattern1-epp  # Shared EPP
```

**Key insight:** EPP picks best endpoint within pool, HTTPRoute handles model routing.

### HealthCheckPolicies
**Purpose:** Configure GKE load balancer health checks

**Critical configuration:**
- **MUST target InferencePool** (not Service)
- **MUST use `/health` path** (vLLM endpoint, not `/`)
- Create InferencePool first, then HealthCheckPolicy

## Benchmark Results

Comprehensive benchmark reports available in [`benchmarks/`](./benchmarks/):

**Latency Benchmarks:**
- `pattern2_bbr_qwen_latency.html/json` - Qwen 100 requests, c=1
- `pattern2_bbr_phi3_latency.html/json` - Phi-3 100 requests, c=1

**Concurrent Throughput:**
- `pattern2_bbr_qwen_concurrent.html/json` - Qwen 100 requests, c=10
- `pattern2_bbr_phi3_concurrent.html/json` - Phi-3 100 requests, c=10

**Analysis:**
- [`PATTERN2_BBR_BENCHMARK_RESULTS.md`](./PATTERN2_BBR_BENCHMARK_RESULTS.md) - Complete analysis
- [`PATTERN2_INVESTIGATION_SUMMARY.md`](./PATTERN2_INVESTIGATION_SUMMARY.md) - Implementation journey

## Cost Analysis

### Incremental Cost vs Pattern 1

**Additional Resources:**
- +1 TPU node (ct6e-standard-4t): +$5.00/hour
- +2 InferencePools (phi-pool, qwen-pool): No cost (K8s resources)
- +2 HTTPRoutes: No cost (Gateway API resources)

**Total Incremental:** ~$3,655/month

### Cost Optimization

**Scale to zero:**
```bash
# Scale deployments
kubectl scale deployment ms-pattern1-llm-d-modelservice-decode ms-pattern2-llm-d-modelservice-decode \
  --replicas=0 -n llm-d-inference-scheduling

# Scale TPU nodes
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a \
  --project=ecoeng-llmd
```

**Cost while scaled to 0:** ~$113/month (saves $7,302/month)

## Troubleshooting

### "no healthy upstream" Error

**Symptom:** All requests fail with "no healthy upstream"

**Cause:** Health checks using wrong path (`/` instead of `/health`)

**Fix:**
1. Delete and recreate InferencePools
2. Recreate HealthCheckPolicies targeting InferencePools
3. Wait 90 seconds for GCE health checks to update

See [`llm-d-pattern2-tpu-setup.md`](./llm-d-pattern2-tpu-setup.md) Troubleshooting section.

### Routing Accuracy < 100%

**Diagnosis:**
```bash
# Check BBR is injecting headers
kubectl logs -n llm-d-inference-scheduling -l app=body-based-router --tail=50 | grep "X-Gateway"

# Verify HTTPRoute configuration
kubectl describe httproute qwen-model-route phi-model-route -n llm-d-inference-scheduling
```

**Fix:** Ensure HTTPRoute header values match BBR-injected values exactly (case-sensitive).

### Pod Stuck in Pending

**Cause:** Only 1 TPU node available (need 2 for Pattern 2)

**Fix:** Scale TPU node pool to 2 (see Quick Start step 1)

## Documentation

### Deployment Guides
- [`BBR_HELM_DEPLOYMENT.md`](./BBR_HELM_DEPLOYMENT.md) - BBR deployment with official GKE Helm chart
- [`llm-d-pattern2-tpu-setup.md`](./llm-d-pattern2-tpu-setup.md) - Complete TPU setup guide with BBR architecture
- [`llm-d-pattern2-gpu-setup.md`](./llm-d-pattern2-gpu-setup.md) - GPU deployment guide

### Configuration and Manifests
- [`manifests/`](./manifests/) - Kubernetes manifests for both GPU and TPU routing

### Analysis and Results
- [`PATTERN2_BBR_BENCHMARK_RESULTS.md`](./PATTERN2_BBR_BENCHMARK_RESULTS.md) - Comprehensive benchmark analysis
- [`PATTERN2_INVESTIGATION_SUMMARY.md`](./PATTERN2_INVESTIGATION_SUMMARY.md) - Implementation journey and learnings

## Key Learnings

### Why BBR + HTTPRoute?

**Problem:** Model names like `Qwen/Qwen2.5-3B-Instruct` contain slashes, which violate Kubernetes label value restrictions (RFC 1123).

**Failed approaches:**
- Label-based routing: Labels can't contain slashes
- vLLM aliasing: Requires client cooperation, config complexity
- EPP model discovery: Only works with single InferencePool

**Winning solution:**
- BBR extracts model from request body
- Injects as HTTP header (headers support slashes!)
- HTTPRoute matches header value
- Routes to model-specific InferencePool
- **Result: 100% accuracy, zero errors**

### Critical Configuration

1. **Health check path:** MUST use `/health` not `/` (vLLM returns 404 for `/`)
2. **HealthCheckPolicy target:** MUST target InferencePool (not Service)
3. **Order matters:** Create InferencePool first, then HealthCheckPolicy
4. **Pod labels:** Use simple identifiers without slashes (`model-instance: qwen`)
5. **EPP sharing:** Both InferencePools use same EPP (no duplication needed)

## Advantages Over Alternatives

| Feature | BBR Pattern 2 | Weighted Routing | Model Discovery |
|---------|---------------|------------------|-----------------|
| **Routing Accuracy** | 100% | ~50% | ~50% |
| **Client Retries** | Zero | High | High |
| **Model Names** | Supports slashes | Requires sanitization | Requires sanitization |
| **Configuration** | Simple (HTTPRoute) | Complex (weights) | Complex (single pool) |
| **Production Ready** | ✅ Official | ❌ Hacky | ⚠️ Partial |

## Next Steps

**Add More Models:**
1. Deploy new ModelService (pattern3, pattern4, etc.)
2. Label pod with unique `model-instance` label
3. Create new InferencePool with label selector
4. Create new HTTPRoute with header matching
5. Create HealthCheckPolicy for the pool

**Example:** Adding Mistral-7B:
```yaml
# InferencePool
selector:
  matchLabels:
    model-instance: mistral

# HTTPRoute
headers:
- name: X-Gateway-Base-Model-Name
  value: "mistralai/Mistral-7B-Instruct-v0.3"
```

## Resources

**Official Documentation:**
- [Gateway API Inference Extension - Multi-Model Guide](https://gateway-api-inference-extension.sigs.k8s.io/guides/serving-multiple-inference-pools-latest/)
- [BBR Implementation](https://github.com/gateway-api-inference-extension/gateway-api-inference-extension/tree/main/cmd/bbr)
- [GKE HealthCheckPolicy](https://cloud.google.com/kubernetes-engine/docs/how-to/configure-gateway-resources#health_check)

**Related Patterns:**
- [Pattern 1: Baseline Single Model](../pattern1/) - Foundation infrastructure
- [Pattern 3: N/S-Caching Scale-Out](../pattern3/) - Scale to multiple replicas
