# llm-d Pattern 2: Multi-Model Deployment

Deploy multiple LLM models with intelligent routing via a single Gateway endpoint. Demonstrates model-based routing where requests are directed to the correct model backend based on the `model` field in the request JSON with **100% routing accuracy**.

> **📋 Prerequisites**: Pattern 1 must be deployed first. See [llm-d-pattern1-setup.md](./llm-d-pattern1-setup.md) for initial deployment.

## Overview

**Pattern 2** extends Pattern 1 by adding a second model (Mistral-7B-Instruct-v0.3) alongside the existing gemma-2b-it deployment, demonstrating:

- **Multi-model serving**: Two different models running simultaneously
- **Single endpoint**: One Gateway IP for all models
- **Intelligent routing**: Scheduler automatically discovers both models and routes with 100% accuracy
- **Unified scheduler**: Single InferencePool with dynamic model discovery
- **Zero routing errors**: No 404 errors from model mismatch

**Architecture**:
```
Internet → Gateway (35.209.201.202)
              ↓
         HTTPRoute (100% to single pool)
              ↓
         InferencePool (gaie-pattern1)
              ↓
         Scheduler (auto-discovers both models)
         /              \
        /                \
    vLLM               vLLM
(gemma-2b-it)      (Mistral-7B)
   GPU Node 1        GPU Node 2
```

## Prerequisites

### 1. Pattern 1 Deployed

Pattern 2 builds on Pattern 1. You must have:
- ✅ Pattern 1 deployed and working (gemma-2b-it)
- ✅ Gateway accessible at 35.209.201.202
- ✅ HTTPRoute routing to gaie-pattern1 InferencePool

Verify Pattern 1 is working:
```bash
export GATEWAY_IP=35.209.201.202

curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "Test",
    "max_tokens": 10
  }'
```

### 2. GPU Node Capacity

Pattern 2 requires a **second GPU node**:
- Each T4 GPU runs one model
- Mistral-7B (7B params) needs its own dedicated T4 GPU
- Current cluster has 1 GPU node, can scale to 3

**Cost**: +$0.35-0.50/hour (~$260/month) for second GPU node

### 3. Cluster Resources

**Current cluster** (nvidia-test-cluster):
- Zone: us-central1-a
- CPU nodes: 2x n1-standard-4
- GPU nodes: 1x n1-standard-4 with 1x T4 GPU (will scale to 2)
- Namespace: llm-d

## Deployment Patterns Comparison

| Feature | Pattern 1 | Pattern 2 |
|---------|-----------|-----------|
| **Models** | 1 (gemma-2b-it) | 2 (gemma + Mistral-7B) |
| **Replicas** | 1 per model | 1 per model |
| **Gateway** | Single (35.209.201.202) | Single (shared) |
| **InferencePools** | 1 (gaie-pattern1) | 1 (gaie-pattern1, shared) |
| **Schedulers** | 1 (gaie-pattern1-epp) | 1 (with multi-model discovery) |
| **HTTPRoute** | Routes to 1 backend | Routes to 1 backend (100% accuracy) |
| **Model Discovery** | Static (1 model) | Dynamic (queries /v1/models) |
| **Routing Accuracy** | 100% (single model) | 100% (model-aware scheduler) |
| **GPU Nodes** | 1 | 2 |
| **Cost** | ~$470/month | ~$760/month |

## Quick Start Guide (30 minutes)

### Step 1: Scale GPU Node Pool to 2 Nodes

Mistral-7B requires a second GPU node:

```bash
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool \
  --num-nodes 2 \
  --zone us-central1-a \
  --project ecoeng-llmd
```

**Wait for second node** (takes 2-3 minutes):
```bash
kubectl get nodes -w
# Press Ctrl+C when you see 2 nodes with GPU (nvidia.com/gpu: 1)
```

**Verify**:
```bash
kubectl get nodes -o wide
# Should show 4 nodes total: 2 CPU + 2 GPU
```

### Step 2: Create pattern2-overrides.yaml

Copy Pattern 2 GPU Helm overrides from tracked configuration:

**Note:** The Pattern 2 GPU override file is tracked in `helm-configs/pattern-overrides/pattern2-gpu-overrides.yaml`.
See [helm-configs/README.md](../../helm-configs/README.md) for details.

```bash
# Copy Pattern 2 GPU Helm overrides from helm-configs
cp helm-configs/pattern-overrides/pattern2-gpu-overrides.yaml \
   llm-d/guides/inference-scheduling/ms-inference-scheduling/pattern2-overrides.yaml
```

**Key differences from pattern1-overrides.yaml**:
- Model: mistralai/Mistral-7B-Instruct-v0.3 (vs google/gemma-2b-it)
- Size: 20Gi (vs 10Gi)
- Max model len: 2048 tokens (same as pattern1, conservative for T4)
- GPU utilization: 0.85 (same as pattern1)
- Startup timeout: 90 failures × 30s = 45 min (vs 30 min for smaller model)

### Step 3: Update Pattern 1 Labels (Optional but Recommended)

Add multi-model labels to Pattern 1 for consistency:

**Note:** This modifies the Pattern 1 override file to add multi-model labels.
Alternatively, use the pre-configured file from `helm-configs/pattern-overrides/pattern1-overrides.yaml`
which may already include these labels.

```bash
# Edit pattern1-overrides.yaml to add commonLabels
cat >> /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/ms-inference-scheduling/pattern1-overrides.yaml <<'EOF'
# Multi-Model Deployment Labels
commonLabels:
  llm-d.ai/inferenceServing: "true"
  llm-d.ai/deployment: "multi-model"
  llm-d.ai/model: "gemma-2b-it"
EOF

# Redeploy Pattern 1 with updated labels
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling
RELEASE_NAME_POSTFIX=pattern1 helmfile -e gke -n llm-d apply
```

### Step 4: Deploy Pattern 2 ModelService

Deploy Mistral-7B ModelService that will share the existing InferencePool:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d"
export RELEASE_NAME_POSTFIX="pattern2"

# Deploy ONLY Pattern 2 ModelService (skip infrastructure)
helmfile -e gke -n $NAMESPACE apply --selector type=modelservice
```

**What gets deployed**:
- ms-pattern2-*-decode-* (vLLM pod with Mistral-7B)
- **Shares existing gaie-pattern1 InferencePool** (no new InferencePool created)

**Monitor deployment** (takes 10-15 minutes for model download):
```bash
# Watch pods come up
kubectl get pods -n llm-d -w

# Watch Mistral-7B model download progress
kubectl logs -n llm-d -l llm-d.ai/inferenceServing=true -l app.kubernetes.io/instance=ms-pattern2 -f
```

**Expected pods** when complete:
```
gaie-pattern1-epp-xxx          1/1 Running   (scheduler - auto-discovers BOTH models)
ms-pattern1-...-decode-xxx     1/1 Running   (vLLM with gemma-2b-it)
ms-pattern2-...-decode-xxx     1/1 Running   (vLLM with Mistral-7B)
```

**Note**: Only ONE scheduler pod (gaie-pattern1-epp) manages both models via dynamic discovery.

### Step 5: Verify InferencePool Discovers Both Models

Check that the single InferencePool sees both backend pods:

```bash
# View InferencePool status
kubectl get inferencepool gaie-pattern1 -n llm-d -o yaml

# Check that both pods are labeled correctly
kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true

# Expected: Both ms-pattern1 and ms-pattern2 pods shown
```

The InferencePool's label selector (`llm-d.ai/inferenceServing: "true"`) matches both ModelService pods.

### Step 6: Update HTTPRoute (If Needed)

Verify HTTPRoute points to single InferencePool:

```bash
kubectl get httproute -n llm-d -o yaml
```

If HTTPRoute needs updating (e.g., from old weighted routing):

```bash
# Delete old HTTPRoute (if exists)
kubectl delete httproute llm-d-pattern1-inference-scheduling -n llm-d 2>/dev/null || true

# Apply unified HTTPRoute
kubectl apply -f pattern2/manifests/httproute-unified.yaml -n llm-d
```

**How this works**:
1. HTTPRoute sends 100% of requests to single InferencePool (gaie-pattern1)
2. InferencePool's scheduler queries each backend's `/v1/models` endpoint
3. Scheduler maintains awareness of which backend serves which model
4. Scheduler reads `model` field from request JSON and routes to correct backend
5. **100% routing accuracy** - no 404 errors from model mismatch

**Verify HTTPRoute**:
```bash
kubectl get httproute -n llm-d
kubectl describe httproute llm-d-multi-model-inference -n llm-d
```

### Step 7: Verify Deployment

Check all components are running correctly:

```bash
# Pods (should see 3 total: 1 scheduler + 2 vLLM)
kubectl get pods -n llm-d | grep -E "(gaie|ms-pattern)"

# InferencePools (should see 1)
kubectl get inferencepool -n llm-d

# Gateway (should see ONLY 1)
kubectl get gateway -n llm-d

# HTTPRoute (should see unified route)
kubectl get httproute -n llm-d

# Services
kubectl get svc -n llm-d | grep -E "(gaie|ms-pattern)"
```

**Expected resources**:
- 1 scheduler pod (gaie-pattern1-epp) - manages BOTH models
- 2 vLLM pods (ms-pattern1-decode, ms-pattern2-decode)
- 1 InferencePool (gaie-pattern1) - selects BOTH vLLM pods
- 1 Gateway (infra-pattern1-inference-gateway)
- 1 HTTPRoute (llm-d-multi-model-inference)

### Step 8: Verify Model Discovery

Check that the scheduler discovered both models:

```bash
# Get scheduler logs to confirm model discovery
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp | grep -i "model\|backend"

# Query available models via API
export GATEWAY_IP=35.209.201.202
curl http://${GATEWAY_IP}/v1/models | jq
```

**Expected /v1/models response**:
```json
{
  "data": [
    {"id": "google/gemma-2b-it", ...},
    {"id": "mistralai/Mistral-7B-Instruct-v0.3", ...}
  ]
}
```

### Step 9: Test Multi-Model Routing (100% Accuracy)

Test requests to **both models** via single Gateway endpoint:

```bash
export GATEWAY_IP=35.209.201.202

# Test 1: Request gemma-2b-it model (10 requests - should ALL succeed)
echo "Testing gemma-2b-it (10 requests)..."
for i in {1..10}; do
  echo "Request $i:"
  curl -X POST http://${GATEWAY_IP}/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "google/gemma-2b-it",
      "prompt": "Hello",
      "max_tokens": 10
    }' | jq -r '.choices[0].text // .error.message'
  echo "---"
done

# Test 2: Request Mistral-7B model (10 requests - should ALL succeed)
echo "Testing Mistral-7B (10 requests)..."
for i in {1..10}; do
  echo "Request $i:"
  curl -X POST http://${GATEWAY_IP}/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "mistralai/Mistral-7B-Instruct-v0.3",
      "prompt": "Hello",
      "max_tokens": 10
    }' | jq -r '.choices[0].text // .error.message'
  echo "---"
done
```

**Expected**: **10/10 successful responses for each model** (not 5/10 like old weighted routing).

### Step 10: Verify Scheduler Routing

Check scheduler logs to see model-based routing decisions:

```bash
# Unified scheduler logs (manages both models)
echo "=== Unified Scheduler (both models) ==="
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp --tail=50
```

**Look for** in logs:
- `"incomingModelName": "google/gemma-2b-it"` for gemma requests
- `"incomingModelName": "mistralai/Mistral-7B-Instruct-v0.3"` for Mistral requests
- Backend selection showing routing to different pods
- Routing plugin decisions (prefix-cache-scorer, queue-scorer, etc.)

### Step 9: Verify GPU Allocation

Check that each vLLM pod is on a **different GPU node**:

```bash
kubectl get pods -n llm-d -o wide | grep ms-pattern
```

**Expected**:
- `ms-pattern1-*-decode-*` on node `10.128.0.4` (GPU node 1)
- `ms-pattern2-*-decode-*` on node `10.128.0.5` (GPU node 2)

Each pod should be on a different node with its own T4 GPU.

---

## Architecture Deep Dive

### Multi-Model Network Flow

```
Internet (Client Request)
  ↓
  {"model": "mistralai/Mistral-7B-Instruct-v0.3", "prompt": "...", "max_tokens": 30}
  ↓
Gateway: 35.209.201.202:80
  ↓
GCP Load Balancer (regional external Application LB)
  ↓
HTTPRoute (llm-d-multi-model-inference)
  ↓
  100% → InferencePool gaie-pattern1 (port 54321)
           ↓
       Scheduler gaie-pattern1-epp (ext-proc :9002)
           ↓
       (Queries backends on startup: /v1/models endpoint)
       (Discovers: Backend 1 = gemma-2b-it, Backend 2 = Mistral-7B)
           ↓
       (Reads model field from request JSON)
       (model="mistralai/..." → routes to Backend 2)
           ↓
       vLLM Pod: ms-pattern2-*-decode-* (10.0.0.7:8000)
           ↓ (processes inference with Mistral-7B)
           ↓ (returns completion)
           ↓
       Response flows back through Gateway
           ↓
       Client receives response (100% success rate)
```

### Request Routing Logic

**Unified InferencePool** (HTTPRoute level):
- HTTPRoute sends 100% of requests to single InferencePool (gaie-pattern1)
- No weighted distribution - all traffic goes to one scheduler

**Dynamic Model Discovery** (Scheduler startup):
- Scheduler queries each backend pod's `/v1/models` endpoint
- Builds internal map: `{"google/gemma-2b-it": Backend1, "mistralai/Mistral-7B-Instruct-v0.3": Backend2}`
- Maintains awareness of available models across all backends

**Intelligent Routing** (Scheduler request handling):
- Scheduler receives request via ext-proc on port 9002
- Reads `model` field from request JSON body
- Looks up model in internal map
- Routes to correct backend with 100% accuracy
- Returns 404 only if model truly doesn't exist

**Why 100% accuracy?**
- Single scheduler has complete view of all available models
- No blind distribution - scheduler knows which backend serves which model
- Model-aware routing before backend selection
- Eliminates client retries and 404 errors

### Component Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│ llm-d Namespace                                                     │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Unified InferencePool (gaie-pattern1)                         │ │
│  │  Label Selector: llm-d.ai/inferenceServing=true               │ │
│  │                                                                │ │
│  │  Scheduler: gaie-pattern1-epp                                 │ │
│  │    Pod IP: 10.0.1.8                                           │ │
│  │    Port: 9002 (ext-proc)                                      │ │
│  │    Port: 9090 (metrics)                                       │ │
│  │    Discovers: gemma-2b-it, Mistral-7B                         │ │
│  │                                                                │ │
│  │  Backend Pods (selected by label):                            │ │
│  │  ┌─────────────────────┐  ┌─────────────────────┐             │ │
│  │  │ ms-pattern1-decode  │  │ ms-pattern2-decode  │             │ │
│  │  │ Pod IP: 10.0.0.6    │  │ Pod IP: 10.0.0.7    │             │ │
│  │  │ Port: 8000 (vLLM)   │  │ Port: 8000 (vLLM)   │             │ │
│  │  │ Model: gemma-2b-it  │  │ Model: Mistral-7B   │             │ │
│  │  │ GPU: T4 Node 1      │  │ GPU: T4 Node 2      │             │ │
│  │  │ Label: inferencing  │  │ Label: inferencing  │             │ │
│  │  └─────────────────────┘  └─────────────────────┘             │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Gateway (Shared)                                              │ │
│  │  infra-pattern1-inference-gateway                             │ │
│  │  External IP: 35.209.201.202                                  │ │
│  │  Class: gke-l7-regional-external-managed                      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ HTTPRoute (Unified)                                           │ │
│  │  llm-d-multi-model-inference                                  │ │
│  │  Backend:                                                     │ │
│  │   - gaie-pattern1 (100% traffic)                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### GCP Load Balancer Backend Services

```bash
# View backend services created by Gateway
gcloud compute backend-services list --filter="name~gkegw1" --project=ecoeng-llmd | grep gaie-pattern
```

**Expected backends**:
```
gkegw1-*-gaie-pattern1-epp-9002-*       (ext-proc for unified scheduler)
gkegw1-*-gaie-pattern1-ips-*-54321-*    (InferencePool backends - both vLLM pods)
```

The single InferencePool has:
- **Port 54321 backend**: Routes to both vLLM pods (gemma + Mistral)
- **Port 9002 backend**: ext-proc (unified scheduler) integration

---

## Verification and Testing

### Quick Verification Script

```bash
#!/bin/bash
set -e

echo "=== Pattern 2 Verification ==="

# Check pod count
POD_COUNT=$(kubectl get pods -n llm-d | grep -E "(gaie|ms-pattern)" | wc -l)
echo "Pods running: $POD_COUNT (expected: 4)"

# Check Gateway count
GATEWAY_COUNT=$(kubectl get gateway -n llm-d --no-headers | wc -l)
echo "Gateways: $GATEWAY_COUNT (expected: 1)"

# Check InferencePool count
POOL_COUNT=$(kubectl get inferencepool -n llm-d --no-headers | wc -l)
echo "InferencePools: $POOL_COUNT (expected: 2)"

# Test both models
export GATEWAY_IP=35.209.201.202

echo -e "\n=== Testing gemma-2b-it ==="
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "google/gemma-2b-it", "prompt": "Hi", "max_tokens": 5}' \
  | jq -r '.choices[0].text'

echo -e "\n=== Testing Mistral-7B ==="
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "mistralai/Mistral-7B-Instruct-v0.3", "prompt": "Hi", "max_tokens": 5}' \
  | jq -r '.choices[0].text'

echo -e "\n✅ Pattern 2 verification complete"
```

### Model Comparison Test

Compare responses from both models to the same prompt:

```bash
export GATEWAY_IP=35.209.201.202

PROMPT="Explain containerization in 2 sentences."

echo "=== Gemma-2B-IT Response ==="
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"google/gemma-2b-it\", \"prompt\": \"$PROMPT\", \"max_tokens\": 100}" \
  | jq -r '.choices[0].text'

echo -e "\n=== Mistral-7B Response ==="
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"mistralai/Mistral-7B-Instruct-v0.3\", \"prompt\": \"$PROMPT\", \"max_tokens\": 100}" \
  | jq -r '.choices[0].text'
```

**Expected**: Different responses showcasing each model's capabilities.

### Load Test (Optional)

Test concurrent requests to both models:

```bash
# Send 10 requests to each model concurrently
for i in {1..10}; do
  (curl -s -X POST http://35.209.201.202/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "google/gemma-2b-it", "prompt": "Test '$i'", "max_tokens": 10}' \
    | jq -r '.choices[0].text') &
done

for i in {1..10}; do
  (curl -s -X POST http://35.209.201.202/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "mistralai/Mistral-7B-Instruct-v0.3", "prompt": "Test '$i'", "max_tokens": 10}' \
    | jq -r '.choices[0].text') &
done

wait
echo "Load test complete"
```

---

## Troubleshooting

### Issue 1: Mistral-7B Pod OOM (CrashLoopBackOff)

**Symptom**:
```bash
kubectl get pods -n llm-d | grep ms-pattern2
# ms-pattern2-*-decode-*  0/1  CrashLoopBackOff

kubectl logs -n llm-d <ms-pattern2-pod-name>
# Shows: "CUDA out of memory"
```

**Cause**: 7B model with 2048 context length exceeds T4 GPU memory (14.58 GB total)

**Fix**: Reduce memory requirements:

```bash
# Edit pattern2-overrides.yaml
# Option 1: Reduce context length
#   Change: --max-model-len from "2048" to "1024"
# Option 2: Reduce GPU memory utilization
#   Change: --gpu-memory-utilization from "0.85" to "0.80"

# Redeploy
RELEASE_NAME_POSTFIX=pattern2 helmfile -e gke -n llm-d apply
```

**Alternative**: Use quantization (if model supports):
```yaml
args:
  - "--quantization"
  - "awq"  # or "gptq" if available
```

### Issue 2: Both Pods on Same GPU Node

**Symptom**:
```bash
kubectl get pods -n llm-d -o wide | grep ms-pattern
# Both pods show same NODE (10.128.0.4)
# One pod is Pending with "Insufficient nvidia.com/gpu"
```

**Cause**: GPU node pool didn't scale to 2 nodes

**Fix**:
```bash
# Force scale to 2 nodes
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool \
  --num-nodes 2 \
  --zone us-central1-a \
  --project ecoeng-llmd

# Wait for second node
kubectl get nodes -w
# Press Ctrl+C when second GPU node appears

# Check pod distribution
kubectl get pods -n llm-d -o wide | grep ms-pattern
```

### Issue 3: 404 Error "Model does not exist"

**Symptom**: Requests fail with 404 "Model does not exist" error

**Cause**: Model truly doesn't exist OR scheduler hasn't discovered models yet

**Diagnosis**:
```bash
# Check available models via API
curl http://35.209.201.202/v1/models | jq

# Check scheduler logs for model discovery
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp | grep -i "discover\|model"
```

**Fix**:
1. **If models not discovered**: Restart scheduler pod
   ```bash
   kubectl delete pod -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp
   ```
2. **If model name is wrong**: Verify exact model name from `/v1/models` endpoint
3. **If backend pod not ready**: Wait for vLLM pod to become Ready

**Note**: With the new unified design, 404 errors should be rare (<1%) and indicate actual issues, not routing problems.

### Issue 4: HTTPRoute Not Bound

**Symptom**:
```bash
kubectl describe httproute llm-d-multi-model-inference -n llm-d
# Shows: ResolvedRefs: False
# Message: "InferencePool gaie-pattern1 not found"
```

**Cause**: InferencePool doesn't exist or isn't ready

**Fix**:
```bash
# Check InferencePool
kubectl get inferencepool -n llm-d

# Check services
kubectl get svc -n llm-d | grep gaie-pattern1

# If missing, redeploy pattern1
RELEASE_NAME_POSTFIX=pattern1 helmfile -e gke -n llm-d apply
```

### Issue 5: Model Download Timeout

**Symptom**:
```bash
kubectl get pods -n llm-d | grep ms-pattern2
# Pod stuck in Init:0/1 or ContainerCreating for > 30 min
```

**Cause**: Mistral-7B download (~14 GB) taking longer than startup timeout

**Fix**: Increase startup probe timeout:
```bash
# Edit pattern2-overrides.yaml
# Change: failureThreshold from 90 to 120
# This allows 120 × 30s = 60 minutes for startup

# Redeploy
RELEASE_NAME_POSTFIX=pattern2 helmfile -e gke -n llm-d apply
```

**Alternative**: Pre-cache model in persistent volume (advanced)

---

## Cost Analysis

### Before Pattern 2 (Pattern 1 Only)

**Compute**:
- 2x CPU nodes (n1-standard-4): $0.10/hr × 2 = $0.20/hr
- 1x GPU node (n1-standard-4 + T4): $0.40/hr
- **Total compute**: $0.60/hr (~$440/month)

**Networking**:
- Gateway forwarding rules: ~$18/month
- Data processing: ~$0.008/GB
- **Total networking**: ~$25/month

**Total Pattern 1**: ~$465/month

### After Pattern 2 (Two Models)

**Compute**:
- 2x CPU nodes (n1-standard-4): $0.10/hr × 2 = $0.20/hr
- 2x GPU nodes (n1-standard-4 + T4): $0.40/hr × 2 = $0.80/hr
- **Total compute**: $1.00/hr (~$730/month)

**Networking**:
- Gateway forwarding rules: ~$18/month (unchanged)
- Data processing: ~$0.008/GB (unchanged)
- **Total networking**: ~$25/month

**Total Pattern 2**: ~$755/month

### Cost Increase

**Incremental cost**: +$290/month for second GPU node

### Cost Savings When Not Testing

**Scale to zero**:
```bash
# Scale all deployments to 0 replicas
kubectl scale deployment --all -n llm-d --replicas=0

# Scale GPU nodes to 0
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd

# Keep CPU nodes for cluster management (minimal cost)
```

**Cost while scaled to 0**:
- 2x CPU nodes: ~$175/month
- Gateway: ~$25/month
- **Total**: ~$200/month (saves $555/month)

**Scale back up when needed**:
```bash
# Scale GPU nodes back to 2
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 2 \
  --zone us-central1-a --project ecoeng-llmd

# Scale deployments back to 1 replica
kubectl scale deployment -n llm-d ms-pattern1-llm-d-modelservice-decode --replicas=1
kubectl scale deployment -n llm-d ms-pattern2-llm-d-modelservice-decode --replicas=1
```

---

## Cleanup Options

### Option 1: Remove Only Pattern 2 (Keep Pattern 1)

Return to Pattern 1 single-model deployment:

```bash
# Delete Pattern 2 releases
RELEASE_NAME_POSTFIX=pattern2 helmfile -e gke -n llm-d destroy

# Restore single-model HTTPRoute
kubectl delete httproute llm-d-multi-model-inference -n llm-d
kubectl apply -f pattern1/manifests/httproute-pattern1.yaml -n llm-d

# Scale GPU nodes back to 1
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 1 \
  --zone us-central1-a --project ecoeng-llmd

# Verify
kubectl get pods -n llm-d
kubectl get gateway -n llm-d
```

**Result**: Back to Pattern 1 with only gemma-2b-it, saves $290/month.

### Option 2: Remove Both Patterns (Full Cleanup)

Remove all llm-d deployments:

```bash
# Delete all releases
RELEASE_NAME_POSTFIX=pattern1 helmfile -e gke -n llm-d destroy
RELEASE_NAME_POSTFIX=pattern2 helmfile -e gke -n llm-d destroy

# Delete HTTPRoute
kubectl delete httproute llm-d-multi-model-inference -n llm-d --ignore-not-found

# Delete namespace (optional)
kubectl delete namespace llm-d

# Scale GPU nodes to 0
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd
```

**Result**: No llm-d resources running, cluster in minimal state.

### Option 3: Temporary Pause (Keep Configuration)

Scale to 0 without deleting resources:

```bash
# Scale deployments to 0
kubectl scale deployment --all -n llm-d --replicas=0

# Scale GPU nodes to 0
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd

# All configuration (Gateway, HTTPRoute, InferencePools) remains
# Just scale back up when needed
```

**Result**: Minimal cost (~$200/month), quick restart.

---

## Next Steps

### Pattern 3: Scale-Out with Multiple Replicas

Deploy multiple replicas of same model with N/S caching:
- Increase replicas to 3 for gemma-2b-it
- Test load distribution across replicas
- Observe prefix-cache-aware routing
- Benchmark throughput improvement

### Benchmarking

Compare performance between models:
```bash
# Use llm-d benchmark tools
cd /home/jhull/devel/rhaiis-test/llm-d/guides/benchmark

# Compare gemma-2b-it vs Mistral-7B
# - Latency (TTFT, TPOT)
# - Throughput (tokens/sec)
# - Quality (response accuracy)
```

### Advanced Routing

Implement path-based or header-based routing:
```yaml
# Path-based routing
rules:
  - matches:
    - path:
        type: PathPrefix
        value: /gemma
    backendRefs:
    - name: gaie-pattern1

  - matches:
    - path:
        type: PathPrefix
        value: /mistral
    backendRefs:
    - name: gaie-pattern2
```

### Monitoring and Metrics

Deploy Prometheus + Grafana:
```bash
# Enable Prometheus in pattern overrides
monitoring:
  prometheus:
    enabled: true

# Deploy Grafana
# Import vLLM dashboard (ID: 23991)
# Add InferencePool metrics
```

### Cost Optimization

Set up auto-scaling:
- Configure HPA for deployments
- Set up node pool autoscaling based on demand
- Implement request-based scaling policies

---

## Summary

Pattern 2 demonstrates **multi-model serving with 100% routing accuracy** using:
- ✅ Two models (gemma-2b-it + Mistral-7B) on single endpoint
- ✅ Intelligent model-based routing with dynamic model discovery
- ✅ Single unified InferencePool and scheduler
- ✅ Shared Gateway for unified access
- ✅ Zero routing errors (no 404s from model mismatch)
- ✅ Independent scaling per model

**Key learnings**:
- llm-d uses `RELEASE_NAME_POSTFIX` for concurrent deployments
- Single InferencePool can manage multiple models via label selectors
- Scheduler dynamically discovers models by querying `/v1/models` endpoint
- Scheduler reads `model` field from request for intelligent routing
- 100% routing accuracy eliminates need for client-side retries

**Advantages over dual InferencePool design**:
- **100% routing accuracy** vs 50% with weighted routing
- Simpler architecture - fewer components to manage
- Lower infrastructure overhead (one scheduler vs two)
- Easier to add models (just deploy new ModelService with same label)
- No client retries needed
- Reduced 404 errors and improved user experience

**Production considerations**:
- Monitor model-specific metrics and adjust resources accordingly
- Consider rate limiting per model
- Set up alerting for model availability and performance
- Use horizontal pod autoscaling for model replicas
- Implement caching strategies for frequently requested models
