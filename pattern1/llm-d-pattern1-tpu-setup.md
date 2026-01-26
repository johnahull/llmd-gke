# llm-d Pattern 1: Single Replica Deployment on TPU v6e

Kubernetes-native distributed LLM inference framework with intelligent scheduling on Google Cloud TPU v6e (Trillium) accelerators.

> **🚀 Quick Start**: This guide deploys **llm-d Pattern 1** on TPU v6e: A single-replica vLLM deployment with intelligent inference scheduling on GKE with Google Cloud TPU v6e accelerators.

## Overview

**What is llm-d?**
- Kubernetes-native distributed LLM inference framework
- Intelligent load-aware and prefix-cache-aware routing
- Foundation for scale-out, multi-model, and MoE deployments
- Supports NVIDIA GPUs, AMD GPUs, Google TPUs, Intel XPUs

**Architecture**:
```
Internet → GKE Gateway → Inference Scheduler → vLLM Pod (Qwen2.5-3B-Instruct on TPU v6e)
                              ↓
                    Metrics endpoints exposed
                   (scheduler:9090, vLLM:8000/metrics)
```

**Components**:
1. **vLLM TPU**: Model serving engine with JAX/XLA backend
2. **Inference Scheduler (EPP)**: Request router with intelligent scheduling
3. **Gateway API**: Kubernetes-native load balancing (GKE built-in)
4. **InferencePool**: Custom resource managing pools of inference endpoints

## Prerequisites

### Required Before Starting

1. **GKE TPU Cluster** - Already created per tpu-cluster-setup.md:
   - Cluster: `tpu-test-cluster` (zone: `europe-west4-a`)
   - TPU Node Pool: `tpu-v6e-pool` (machine-type: `ct6e-standard-4t`)
   - Auto-scaling: 0-2 nodes

2. **Google Cloud Configuration**:
   - Project: `ecoeng-llmd`
   - TPU v6e quota in europe-west4-a (minimum 4 chips)
   - `gcloud` CLI installed and configured

3. **Credentials**:
   - Red Hat registry pull secret: `11009103-jhull-svc-pull-secret.yaml`
   - Hugging Face token: `YOUR_HUGGINGFACE_TOKEN`

4. **Repository**:
   - llm-d repository cloned at `/home/jhull/devel/rhaiis-test/llm-d`
   - Working directory: `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling`

## TPU vs GPU Deployment Differences

### Key TPU-Specific Considerations

**1. XLA Compilation**
- First inference request triggers JIT compilation (60-120s delay)
- Subsequent requests use compiled graph (fast)
- This is expected and only happens once per model load

**2. Resource Allocation**
- TPU pods MUST request chips matching the node's topology
- **GKE Warden enforces**: ct6e-standard-4t nodes (2x2 topology) MUST request all 4 chips
- Cannot request fewer chips than the topology provides
- Requests must equal limits
- **Pattern 1 configuration**: `google.com/tpu: 4` for ct6e-standard-4t (mandatory)

**3. Topology Configuration**
- TPU_CHIPS_PER_HOST_BOUNDS must match the requested chips:
  - 4 chips (TP=4) → `2,2,1` (2x2 topology) - **Pattern 1 configuration**
  - 8 chips (TP=8) → `2,4,1` (2x4 topology)
- **Pattern 1 uses**: `2,2,1` for 4-chip Qwen2.5-3B-Instruct deployment
- **Important**: Not all models work with TP=4 (tensor sharding requirements vary by architecture)

**4. Node Selector**
- TPU pods require both `cloud.google.com/gke-tpu-topology` and `cloud.google.com/gke-tpu-accelerator` labels for proper scheduling

**5. Extended Startup Times**
- TPU initialization: 2-3 minutes
- Model download: 1-2 minutes (first time)
- XLA compilation: 1-2 minutes (first inference)
- **Total cold start**: 4-7 minutes

**6. JAX/XLA Backend**
- vLLM uses JAX for TPU, not PyTorch
- Different metrics and performance characteristics
- Different debugging and monitoring tools

**7. Container Images**
- GPU: `ghcr.io/llm-d/llm-d-cuda:v0.4.0`
- TPU: `vllm/vllm-tpu:v0.11.1` or `registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5`

**8. Helmfile Environment and Configuration**
- GPU: `helmfile -e gke apply` (loads `values.yaml` + `pattern1-overrides.yaml`)
- TPU: `helmfile -e gke_tpu apply` (loads `values_tpu.yaml` + `pattern1-tpu-overrides.yaml`)

## Deployment Guide

### Step 1: Enable Gateway API and Prepare Cluster

**Enable Gateway API in the cluster**:

```bash
# Set project and zone
export PROJECT_ID="ecoeng-llmd"
export ZONE="europe-west4-a"
export CLUSTER_NAME="tpu-test-cluster"

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME \
  --zone $ZONE \
  --project $PROJECT_ID

# Enable Gateway API (required for InferencePool)
gcloud container clusters update $CLUSTER_NAME \
  --gateway-api=standard \
  --zone $ZONE \
  --project $PROJECT_ID

# This takes 3-5 minutes
```

**Create proxy-only subnet** (required for GKE Gateway):

```bash
# Create proxy-only subnet for regional external ALB
gcloud compute networks subnets create proxy-only-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=$ZONE \
  --network=default \
  --range=192.168.100.0/23 \
  --project=$PROJECT_ID
```

**Install Gateway API and InferencePool CRDs**:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/prereq/gateway-provider
./install-gateway-provider-dependencies.sh apply
```

**Verify CRDs are installed**:
```bash
kubectl api-resources --api-group=inference.networking.k8s.io

# Expected output should show:
# NAME             SHORTNAMES   APIVERSION                       NAMESPACED   KIND
# inferencepools   infpool      inference.networking.k8s.io/v1   true         InferencePool
```

**Scale node pools**:

TPU workloads need both CPU nodes (for scheduler) and TPU nodes (for vLLM):

```bash
# Scale CPU node pool for scheduler pod
gcloud container clusters resize $CLUSTER_NAME \
  --node-pool default-pool \
  --num-nodes 1 \
  --zone $ZONE \
  --project $PROJECT_ID \
  --quiet

# Scale TPU node pool for vLLM pod
gcloud container clusters resize $CLUSTER_NAME \
  --node-pool tpu-v6e-pool \
  --num-nodes 1 \
  --zone $ZONE \
  --project $PROJECT_ID \
  --quiet

# Wait for nodes to be ready (TPU node takes 2-3 minutes)
kubectl get nodes
# Wait until both nodes show Ready status
```

**Expected output**: 2 nodes total
- 1 CPU node (`e2-standard-4`) for scheduler
- 1 TPU node (`ct6e-standard-4t`) for vLLM

**Verify TPU node labels**:
```bash
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.cloud\.google\.com/gke-tpu-topology}{"\n"}{end}'

# Expected: One node should show "2x2" topology
```

### Step 2: Create Namespace and Secrets

Create llm-d namespace and configure authentication:

```bash
# Create namespace
kubectl create namespace llm-d

# Apply Red Hat registry pull secret (if using RHAIIS image)
kubectl apply -f /home/jhull/devel/rhaiis-test/11009103-jhull-svc-pull-secret.yaml -n llm-d

# Verify secret
kubectl get secret 11009103-jhull-svc-pull-secret -n llm-d

# Create HuggingFace token secret
# Note: Create with both 'token' and 'HF_TOKEN' keys (Helm chart expects both)
kubectl create secret generic huggingface-token \
  --from-literal=token=YOUR_HUGGINGFACE_TOKEN \
  --from-literal=HF_TOKEN=YOUR_HUGGINGFACE_TOKEN \
  -n llm-d

# Verify secrets
kubectl get secrets -n llm-d
```

**Expected secrets**:
- `11009103-jhull-svc-pull-secret` (kubernetes.io/dockerconfigjson) - for RHAIIS image (optional)
- `huggingface-token` (Opaque) - for model download (has both 'token' and 'HF_TOKEN' keys)

### Step 3: Review TPU Configuration

Examine the TPU-specific configuration that will be used:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

# Review base TPU values file
cat ms-inference-scheduling/values_tpu.yaml

# Review Pattern 1 TPU overrides (this is what actually gets deployed)
cat ms-inference-scheduling/pattern1-tpu-overrides.yaml
```

**Configuration Files**:
1. **values_tpu.yaml** - Base TPU defaults (general TPU settings)
2. **pattern1-tpu-overrides.yaml** - Pattern 1 specific overrides (Qwen2.5-3B-Instruct, 1 replica, 4 chips)

**Key TPU configurations in pattern1-tpu-overrides.yaml**:
- `accelerator.type: google` (Google Cloud TPU)
- `modelArtifacts.uri: hf://Qwen/Qwen2.5-3B-Instruct` (3B model for Pattern 1)
- `decode.replicas: 1` (Single replica deployment)
- `decode.parallelism.tensor: 4` (4-way tensor parallelism - **required by GKE Warden**)
- `decode.containers[].image: vllm/vllm-tpu:v0.11.1` (vLLM TPU image)
- `decode.containers[].resources: google.com/tpu: 4` (Requests all 4 TPU chips - **mandatory for 2x2 topology**)
- `decode.containers[].env`: TPU topology (TPU_CHIPS_PER_HOST_BOUNDS=2,2,1) and PJRT configuration
- `decode.containers[].startupProbe.failureThreshold: 60` (Extended for XLA compilation)
- `decode.extraConfig.nodeSelector`: TPU topology (2x2) and accelerator type (tpu-v6e-slice)

**Important**: GKE Warden enforces that ct6e-standard-4t nodes with 2x2 topology MUST request all 4 chips. You cannot request fewer chips.

**Note**: The helmfile automatically loads both `values_tpu.yaml` and `pattern1-tpu-overrides.yaml` when using the `gke_tpu` environment. The override file ensures you get the Pattern 1 configuration (Qwen2.5-3B-Instruct, 1 replica, 4 chips) instead of the base defaults.

### Step 4: Deploy Pattern 1 with Helmfile

Deploy llm-d using the `gke_tpu` environment:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d-inference-scheduling"
export RELEASE_NAME_POSTFIX="pattern1"

# Deploy using gke_tpu environment
# This automatically loads:
#   - values_tpu.yaml (base TPU settings)
#   - pattern1-tpu-overrides.yaml (Pattern 1 configuration)
helmfile -e gke_tpu -n $NAMESPACE apply

# Create HTTPRoute to connect Gateway to InferencePool
# Apply HTTPRoute from manifests directory
kubectl apply -f pattern1/manifests/httproute-pattern1.yaml -n llm-d-inference-scheduling
```

See [`manifests/README.md`](manifests/README.md) for the HTTPRoute manifest details.

**What gets deployed** (with RELEASE_NAME_POSTFIX=pattern1):
- `infra-pattern1-inference-gateway` - Gateway with external IP
- `gaie-pattern1-epp` - Inference scheduler (ext-proc service)
- `gaie-pattern1` - InferencePool custom resource
- `pattern1-route` - HTTPRoute connecting Gateway to InferencePool
- `ms-pattern1-*-decode-*` - vLLM pod with Qwen/Qwen2.5-3B-Instruct on TPU

**Expected deployment time**:
- Helm chart installation: 30 seconds
- TPU pod initialization: 2-3 minutes
- Model download (first time): 1-2 minutes
- **Pod becomes Ready**: ~3-5 minutes after deployment
- **First inference (XLA compilation)**: Additional 1-2 minutes on first request

### Step 5: Monitor Deployment

Watch pod startup in real-time:

```bash
# Watch all pods in llm-d-inference-scheduling namespace
kubectl get pods -n llm-d-inference-scheduling -w

# In another terminal, check deployment status
kubectl get deployments -n llm-d-inference-scheduling

# Check vLLM pod logs
POD=$(kubectl get pods -n llm-d-inference-scheduling -l llm-d.ai/inferenceServing=true -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n llm-d-inference-scheduling $POD -f
```

**Expected log sequence**:
1. "Starting vLLM..." - Container starts
2. "Downloading model..." - HuggingFace download (if not cached)
3. "Initializing TPU..." - PJRT device initialization
4. "Loading model on TPU..." - Model loaded to TPU memory
5. "Uvicorn running on 0.0.0.0:8000" - vLLM server ready
6. **Pod status changes to Running/Ready**
7. **First inference will trigger**: "Compiling XLA graph..." (1-2 min delay)

**Troubleshooting pod startup**:

If pod is stuck in `Pending`:
```bash
kubectl describe pod $POD -n llm-d-inference-scheduling
# Look for: "0/X nodes available: insufficient google.com/tpu"
# Fix: Ensure TPU node pool scaled to 1 (Step 1)
```

If pod is in `CrashLoopBackOff`:
```bash
kubectl logs $POD -n llm-d-inference-scheduling
# Common issues:
# - "No TPU devices found" → Wrong node selector or TPU not initialized
# - "PJRT error" → Wrong TPU_CHIPS_PER_HOST_BOUNDS configuration
# - "OOM" → max-model-len too high for model size
```

### Step 6: Get Gateway External IP

Retrieve the Gateway's external IP address:

```bash
# Wait for Gateway to get external IP (may take 1-2 minutes)
kubectl get gateway infra-pattern1-inference-gateway -n llm-d-inference-scheduling -w

# Get external IP when PROGRAMMED=True
GATEWAY_IP=$(kubectl get gateway infra-pattern1-inference-gateway -n llm-d-inference-scheduling \
  -o jsonpath='{.status.addresses[0].value}')

echo "Gateway IP: $GATEWAY_IP"

# Verify Gateway is ready and has routes attached
kubectl describe gateway infra-pattern1-inference-gateway -n llm-d-inference-scheduling | grep -A 2 "Attached Routes"
```

**Expected output**:
```
NAME                                   CLASS                              ADDRESS         PROGRAMMED   AGE
infra-pattern1-inference-gateway      gke-l7-regional-external-managed   X.X.X.X         True         2m

Attached Routes:  1
```

### Step 7: Verify InferencePool and HTTPRoute

Check that llm-d resources are configured correctly:

```bash
# Check InferencePool
kubectl get inferencepool -n llm-d-inference-scheduling
kubectl describe inferencepool gaie-pattern1 -n llm-d-inference-scheduling

# Check HTTPRoute
kubectl get httproute -n llm-d-inference-scheduling
kubectl describe httproute pattern1-route -n llm-d-inference-scheduling

# Check scheduler service
kubectl get svc -n llm-d-inference-scheduling | grep gaie-pattern1-epp
```

**Expected InferencePool output**:
```
NAME             AGE
gaie-pattern1    5m
```

**Expected HTTPRoute output**:
```yaml
Name:         pattern1-route
Namespace:    llm-d-inference-scheduling
Spec:
  Parent Refs:
    Group:  gateway.networking.k8s.io
    Kind:   Gateway
    Name:   infra-pattern1-inference-gateway
  Rules:
    Backend Refs:
      Group:  inference.networking.k8s.io
      Kind:   InferencePool
      Name:   gaie-pattern1
      Weight: 1
    Matches:
      Path:
        Type:   PathPrefix
        Value:  /
Status:
  Parents:
    Conditions:
      Type:    ResolvedRefs
      Status:  True
      Type:    Accepted
      Status:  True
```

**IMPORTANT**: The HTTPRoute must NOT include a `port` field in the `backendRefs` when using InferencePool. The port is defined in the InferencePool spec itself (targetPorts: 8000).

### Step 8: Test Inference (First Request - XLA Compilation)

**IMPORTANT**: The first inference request will trigger XLA compilation and take 60-120 seconds. This is expected behavior.

```bash
export GATEWAY_IP=$(kubectl get gateway infra-pattern1-inference-gateway -n llm-d-inference-scheduling \
  -o jsonpath='{.status.addresses[0].value}')

# First request - XLA compilation happens during pod startup (precompilation)
# By the time the pod is Ready, XLA is already compiled
echo "Sending first request..."
time curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is Kubernetes?",
    "max_tokens": 50
  }' | jq '.'
```

**Expected response** (from actual deployment test):
```json
{
  "choices": [
    {
      "finish_reason": "length",
      "index": 0,
      "text": " (Part 1) – The basics\n\nKubernetes (k8s) is an open-source container orchestration system for automating deployment, scaling, and management of containerized applications..."
    }
  ],
  "model": "Qwen/Qwen2.5-3B-Instruct",
  "usage": {
    "completion_tokens": 50,
    "prompt_tokens": 4,
    "total_tokens": 54
  }
}
```

**Expected behavior**:
- vLLM performs XLA precompilation during pod startup (takes ~151 seconds)
- Pod only becomes Ready after XLA compilation completes
- First inference request after pod is Ready completes quickly (~0.5-1s)
- Check pod logs: `init engine (profile, create kv cache, warmup model) took 151.45 seconds`

**If request fails with "fault filter abort"**:
```bash
# Check HTTPRoute is created and attached to Gateway
kubectl get httproute -n llm-d-inference-scheduling
kubectl describe gateway infra-pattern1-inference-gateway -n llm-d-inference-scheduling | grep "Attached Routes"

# Should show: Attached Routes: 1
# If 0, the HTTPRoute was not created or has configuration errors
```

### Step 9: Test Subsequent Requests (Fast Inference)

After XLA compilation completes, subsequent requests should be fast:

```bash
# Test completions endpoint
echo "Testing completions endpoint..."
time curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "Explain Docker in one sentence.",
    "max_tokens": 30
  }' -s | jq -r '.choices[0].text'

# Test chat completions endpoint
echo "Testing chat completions endpoint..."
curl -X POST http://${GATEWAY_IP}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [
      {"role": "user", "content": "What is a container?"}
    ],
    "max_tokens": 50
  }' -s | jq -r '.choices[0].message.content'

# Test health endpoint
curl http://${GATEWAY_IP}/health

# Test models endpoint
curl http://${GATEWAY_IP}/v1/models -s | jq
```

**Expected response times** (from actual tests):
- **Completions**: 0.457s (real time from test)
  - Response: `"Docker is an open-source platform that uses containers to package, distribute, and run applications in isolation."`
- **Health check**: <100ms
- **Models list**: <100ms

**Example completion output**:
```
Testing completions endpoint...
 Docker is an open-source platform that uses containers to package, distribute, and run applications in isolation.

real    0m0.457s
user    0m0.002s
sys     0m0.003s
```

### Step 10: Verify Intelligent Routing

Check scheduler logs to see intelligent routing in action:

```bash
# Get scheduler pod
SCHEDULER_POD=$(kubectl get pods -n llm-d-inference-scheduling -l inferencepool=gaie-pattern1-epp \
  -o jsonpath='{.items[0].metadata.name}')

# View scheduler logs
kubectl logs -n llm-d-inference-scheduling $SCHEDULER_POD --tail=50

# The scheduler handles routing decisions based on:
# - Request queue depth (queue-scorer)
# - KV cache utilization (kv-cache-utilization-scorer)
# - Prefix cache hit rate (prefix-cache-scorer)
# In Pattern 1 with single replica, routing is straightforward to the one backend
```

### Step 11: Access Metrics

Check metrics endpoints:

```bash
# Scheduler metrics (port 9090)
kubectl port-forward -n llm-d svc/gaie-pattern1-epp 9090:9090 &
curl http://localhost:9090/metrics | grep -E "(reconcile|backend_health|pool_status)"

# vLLM metrics (port 8000)
POD=$(kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n llm-d $POD 8001:8000 &
curl http://localhost:8001/metrics | grep -E "(vllm:num_requests|kv_cache|tpu_utilization)"

# Stop port-forwards when done
killall kubectl
```

**Key metrics to monitor**:
- `controller_runtime_active_workers{controller="inferencepool"}` - Active scheduler workers
- `controller_runtime_reconcile_errors_total` - Scheduler errors
- `vllm:num_requests_running` - Active inference requests
- `vllm:kv_cache_usage_perc` - KV cache utilization
- `vllm:e2e_request_latency_seconds_bucket` - Request latency distribution

## Verification Steps

### Success Criteria

1. ✅ **TPU node running**: `kubectl get nodes` shows 1 ct6e-standard-4t node in Ready state
2. ✅ **Pods running**: All pods (scheduler + vLLM) in Running state
3. ✅ **Gateway accessible**: External IP assigned and PROGRAMMED=True
4. ✅ **InferencePool ready**: gaie-pattern1 shows backends ready
5. ✅ **HTTPRoute bound**: Route successfully bound to Gateway
6. ✅ **First inference completes**: XLA compilation succeeds (60-120s)
7. ✅ **Subsequent inferences fast**: Requests complete in 1-3 seconds
8. ✅ **Scheduler routing works**: Logs show intelligent routing decisions
9. ✅ **Metrics accessible**: Both scheduler and vLLM metrics endpoints respond

### Quick Verification Script

```bash
#!/bin/bash
set -e

NAMESPACE="llm-d"
GATEWAY_NAME="infra-pattern1-inference-gateway"

echo "=== Pattern 1 TPU Deployment Verification ==="

echo "1. Checking TPU node..."
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice

echo "2. Checking pods..."
kubectl get pods -n $NAMESPACE

echo "3. Checking Gateway..."
kubectl get gateway $GATEWAY_NAME -n $NAMESPACE

echo "4. Checking InferencePool..."
kubectl get inferencepool -n $NAMESPACE

echo "5. Checking HTTPRoute..."
kubectl get httproute -n $NAMESPACE

echo "6. Testing inference..."
GATEWAY_IP=$(kubectl get gateway $GATEWAY_NAME -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "google/gemma-2b-it", "prompt": "Hello", "max_tokens": 10}' \
  | jq -r '.choices[0].text'

echo "=== Verification Complete ==="
```

## Troubleshooting

### Issue 1: Pod Stuck in Pending - "Insufficient google.com/tpu"

**Symptom**: vLLM pod shows `0/X nodes available: insufficient google.com/tpu`

**Cause**: TPU node pool scaled to 0 or no TPU nodes available

**Fix**:
```bash
# Scale TPU node pool to 1
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 1 \
  --zone europe-west4-a \
  --project ecoeng-llmd

# Wait for node
kubectl get nodes -w
```

### Issue 2: Pod CrashLoopBackOff - "No TPU devices found"

**Symptom**: vLLM container crashes with "RuntimeError: No TPU devices found"

**Cause**: Wrong node selector or TPU node not properly initialized

**Fix**:
```bash
# Verify node has TPU labels
kubectl get nodes -o yaml | grep -A5 "tpu"

# Expected labels:
# cloud.google.com/gke-tpu-topology: "2x2"
# cloud.google.com/gke-tpu-accelerator: "tpu-v6e-slice"

# If labels missing, delete and recreate node pool
gcloud container node-pools delete tpu-v6e-pool \
  --cluster tpu-test-cluster \
  --zone europe-west4-a \
  --project ecoeng-llmd

gcloud container node-pools create tpu-v6e-pool \
  --cluster tpu-test-cluster \
  --zone europe-west4-a \
  --machine-type ct6e-standard-4t \
  --num-nodes 1 \
  --enable-autoscaling \
  --min-nodes 0 --max-nodes 2
```

### Issue 3: XLA Compilation Timeout (>120 seconds)

**Symptom**: First inference request times out after 120 seconds

**Cause**: XLA compilation taking longer than expected (large model or complex graph)

**Fix**:
```bash
# Check vLLM logs for compilation progress
kubectl logs -n llm-d $POD --tail=100

# If still compiling, wait longer (up to 5 minutes for larger models)
# For production, increase client timeout

# If compilation fails, reduce model complexity:
# Edit override file and reduce max-model-len:
# args:
#   - "--max-model-len"
#   - "1024"  # Reduced from 2048
```

### Issue 4: "PJRT error: Failed to initialize TPU"

**Symptom**: vLLM logs show PJRT initialization errors

**Cause**: Incorrect TPU topology environment variables

**Fix**:
```bash
# For ct6e-standard-4t (4 chips, 2x2 topology), ensure:
# TPU_CHIPS_PER_HOST_BOUNDS=2,2,1
# TPU_HOST_BOUNDS=1,1,1
# TPU_NUM_DEVICES=4

# Verify pod environment variables
kubectl get pod $POD -n llm-d -o yaml | grep -A10 "env:"

# If wrong, update values_tpu.yaml and redeploy
```

### Issue 5: Gateway External IP Stuck in "Pending"

**Symptom**: Gateway shows no external IP after several minutes

**Cause**: GKE Gateway class not properly configured or quota issues

**Fix**:
```bash
# Check Gateway class
kubectl get gatewayclass

# Expected: istio GatewayClass

# Check Gateway status
kubectl describe gateway infra-pattern1-inference-gateway -n llm-d

# Look for events indicating issues

# If using wrong GatewayClass, check helmfile configuration
# Ensure: gatewayClassName: istio
```

### Issue 6: Model Download Fails (403 Forbidden)

**Symptom**: vLLM logs show "403 Client Error: Forbidden for url: https://huggingface.co/..."

**Cause**: Model requires authentication or wrong HuggingFace token

**Fix**:
```bash
# Verify HuggingFace token secret
kubectl get secret huggingface-token -n llm-d -o yaml

# Decode token
kubectl get secret huggingface-token -n llm-d \
  -o jsonpath='{.data.token}' | base64 -d

# If wrong, delete and recreate:
kubectl delete secret huggingface-token -n llm-d
kubectl create secret generic huggingface-token \
  --from-literal=token=YOUR_HUGGINGFACE_TOKEN \
  -n llm-d

# Restart vLLM pod to pick up new secret
kubectl delete pod $POD -n llm-d
```

### Issue 7: vLLM OOM (Out of Memory)

**Symptom**: vLLM pod killed with OOMKilled status

**Cause**: max-model-len too high for available TPU memory

**Fix**:
```bash
# TPU v6e 4-chip has ~32GB HBM total
# For google/gemma-2b-it:
# - Model weights: ~4GB (FP16)
# - KV cache: depends on max-model-len
# - XLA compilation: ~2-4GB overhead

# Reduce max-model-len by editing values_tpu.yaml:
# args:
#   - "--max-model-len"
#   - "1024"  # Safe for 2B model on 4-chip TPU

# Redeploy
helmfile -e gke_tpu -n llm-d apply
```

### Issue 8: Tensor Sharding Error with gemma-2b-it (TP=4)

**Symptom**: vLLM pod crashes with error like:
```
ValueError: shard_map applied to the function '_ragged_paged_attention' was given argument arrays with axis sizes that are not evenly divisible by the corresponding mesh axis sizes
```

**Cause**: gemma-2b-it architecture has tensor dimensions that cannot be evenly divided across 4 chips with the current vLLM JAX attention implementation

**Fix Option 1 - Use a Different Model**:

Try a model with architecture that shards well across 4 TPU chips:

```bash
# Edit pattern1-tpu-overrides.yaml
# Change modelArtifacts.uri to one of these:
# - "hf://Qwen/Qwen2.5-3B-Instruct"  # 3B params, works well with TP=4
# - "hf://microsoft/Phi-3-mini-4k-instruct"  # 3.8B params
# - "hf://mistralai/Mistral-7B-Instruct-v0.3"  # 7B params (if memory allows)

# Redeploy
helmfile -e gke_tpu -n llm-d apply
```

**Fix Option 2 - Wait for vLLM TPU Improvements**:

The vLLM TPU backend is actively being developed. Future versions may support better sharding for gemma-2b-it.

**Fix Option 3 - Use ct6e-standard-1t Node Type** (requires cluster changes):

If you must use gemma-2b-it, consider using ct6e-standard-1t machine type which has only 1 chip and doesn't require tensor parallelism:

```bash
# This requires recreating the TPU node pool with ct6e-standard-1t
# Not recommended for this guide as it requires significant cluster changes
```

## Architecture Diagram

### Network Flow
```
Internet (Client Request)
  ↓
Gateway: X.X.X.X:80 (GKE Gateway)
  ↓
HTTPRoute (llm-d-pattern1-inference-scheduling)
  ↓
InferencePool: gaie-pattern1
  ↓
Scheduler: gaie-pattern1-epp (ext-proc service)
  ├─ Reads request model field
  ├─ Checks backend health
  └─ Routes to appropriate backend
     ↓
vLLM Backend: ms-pattern1-google-gemma-2b-it-decode
  ├─ Runs on TPU v6e (4 chips, 2x2 topology)
  ├─ Model: google/gemma-2b-it
  ├─ JAX/XLA backend
  └─ Returns response
```

### TPU Resource Allocation
```
TPU Node (ct6e-standard-4t)
  ├─ 4x TPU v6e chips (2x2 topology)
  ├─ ~32 GB HBM (High Bandwidth Memory)
  ├─ Topology: TPU_CHIPS_PER_HOST_BOUNDS=2,2,1
  └─ vLLM Pod
       ├─ Requests: google.com/tpu=4
       ├─ Limits: google.com/tpu=4
       └─ Tensor parallelism across all 4 chips
```

### Request Processing Flow
```
1. Client → Gateway (HTTP/1.1 or HTTP/2)
   POST /v1/completions
   {"model": "google/gemma-2b-it", "prompt": "...", "max_tokens": 50}

2. Gateway → HTTPRoute → InferencePool

3. InferencePool → Scheduler (ext-proc)
   - Scheduler extracts model name: "google/gemma-2b-it"
   - Checks backend pool for matching model
   - Selects healthy backend: ms-pattern1-google-gemma-2b-it-decode

4. Scheduler → vLLM Backend
   - First request: XLA compilation (60-120s)
   - Subsequent requests: Fast (uses compiled graph)

5. vLLM → TPU Processing
   - JAX executes on TPU v6e
   - Tensor parallelism across 4 chips
   - Generates tokens

6. Response path: vLLM → Scheduler → InferencePool → Gateway → Client
```

## Cost Analysis

### TPU v6e Pricing (europe-west4)

**Compute Costs**:
- TPU v6e chip: ~$1.25/hour/chip
- ct6e-standard-4t (4 chips): ~$5.00/hour
- Control plane (GKE cluster): Free (auto-scaled to 0 when no workloads)
- CPU nodes (if needed): ~$0.12/hour/node (e2-standard-2)

**Monthly Costs** (running 24/7):
- 1x TPU node: $5.00/hour × 730 hours = **$3,650/month**
- Total: **~$3,650-3,800/month**

**Cost Savings When Not Testing**:
```bash
# Scale TPU node pool to 0 (stops all charges)
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a \
  --project ecoeng-llmd

# GKE cluster auto-scales to 0 → No compute charges
```

**Cost Comparison vs GPU**:
- NVIDIA T4 GPU: ~$0.35/hour (~$260/month)
- TPU v6e-4t: ~$5.00/hour (~$3,650/month)
- **TPU is ~14x more expensive** but offers:
  - Higher throughput for batch inference
  - Better scaling for large models
  - JAX/XLA optimization benefits

**Recommendation**: Use auto-scaling (min-nodes=0) and scale down when not testing.

## Cleanup Options

### Option 1: Scale to Zero (Preserve Configuration)

```bash
# Scale TPU node pool to 0
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a \
  --project ecoeng-llmd

# Deployments remain, but no compute charges
# To resume: scale node pool back to 1
```

### Option 2: Delete Pattern 1 Deployment (Keep Cluster)

```bash
# Delete llm-d Pattern 1 releases
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d"
export RELEASE_NAME_POSTFIX="pattern1"

helmfile -e gke_tpu -n $NAMESPACE destroy

# Delete namespace (removes all resources)
kubectl delete namespace llm-d

# Scale TPU node pool to 0
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a \
  --project ecoeng-llmd
```

### Option 3: Delete Entire TPU Cluster

```bash
# Delete cluster (removes all resources)
gcloud container clusters delete tpu-test-cluster \
  --zone europe-west4-a \
  --project ecoeng-llmd \
  --quiet

# This removes:
# - TPU node pool
# - Control plane
# - All deployments and namespaces
# - Gateway and HTTPRoute resources
```

## Next Steps After Pattern 1

1. **Test Different Models**: Deploy larger models (7B, 13B) on TPU
2. **Pattern 2**: Multi-model deployment with intelligent routing
3. **Pattern 3**: Scale-out with multiple replicas (N/S caching)
4. **Benchmarking**: Compare TPU vs GPU inference performance
5. **Monitoring**: Deploy Prometheus + Grafana for TPU metrics
6. **Cost Optimization**: Implement request-based auto-scaling
7. **Advanced Features**: Explore speculative decoding, chunked prefill

## Important Changes from Original Guide

### Configuration Adjustments Made

**1. Model Selection (Qwen2.5-3B-Instruct)**
- **Model Used**: Qwen/Qwen2.5-3B-Instruct (3B parameters)
- **Reason**: Works well with 4-way tensor parallelism on TPU v6e
- **Note**: Original guide examples used gemma-2b-it, but it has tensor sharding issues with TP=4
- **Constraint**: GKE Warden requires all 4 chips for ct6e-standard-4t nodes (2x2 topology)

**2. Monitoring Disabled**
- **Change**: GKE monitoring disabled in helmfile.yaml.gotmpl (line 79: `enabled: false`)
- **Reason**: GMP (Google Managed Prometheus) operator couldn't run without nodes, creating chicken-and-egg problem
- **Workaround**: Can re-enable after deployment by changing `enabled: true` and running `helmfile apply`

**3. HuggingFace Secret Keys**
- **Added**: Secret now includes both `token` and `HF_TOKEN` keys
- **Reason**: Helm chart expects `HF_TOKEN` key, but Step 2 created secret with `token` key
- **Command Used**: `kubectl create secret generic huggingface-token --from-literal=token=... --from-literal=HF_TOKEN=...`

**4. Additional Node Pool Required**
- **Requirement**: Both CPU node pool (for scheduler) and TPU node pool needed
- **Reason**: TPU nodes have taint `google.com/tpu: present` preventing non-TPU workloads
- **Solution**: Scale both `default-pool` (CPU) and `tpu-v6e-pool` (TPU) to 1 node each

**5. Gateway API and Proxy-Only Subnet**
- **Required Steps**:
  1. Enable Gateway API in cluster: `gcloud container clusters update ... --gateway-api=standard`
  2. Create proxy-only subnet: `gcloud compute networks subnets create proxy-only-subnet ...`
  3. Install CRDs: `install-gateway-provider-dependencies.sh`
- **Reason**: GKE Gateway requires a proxy-only subnetwork for regional external Application Load Balancer

**6. HTTPRoute Creation Required**
- **Missing Component**: Helmfile doesn't automatically create HTTPRoute to connect Gateway to InferencePool
- **Manual Step Required**: Must create HTTPRoute manually after helmfile deployment (added to Step 4)
- **Configuration**: HTTPRoute connects `infra-pattern1-inference-gateway` to InferencePool `gaie-pattern1`
- **Critical**: HTTPRoute must NOT include `port` field in `backendRefs` when using InferencePool backend
- **Symptom if Missing**: Requests return "fault filter abort" error (Gateway has no routing rules)
- **Verification**: Check `kubectl describe gateway | grep "Attached Routes"` shows `1` (not `0`)

## Key Files Modified/Created

### Files Created for Pattern 1 TPU
1. `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/ms-inference-scheduling/pattern1-tpu-overrides.yaml` - **NEW** Pattern 1 TPU-specific configuration (Qwen2.5-3B-Instruct, 1 replica, 4 chips, 2x2 topology, TP=4)

### Files Modified for Pattern 1 TPU
1. `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/helmfile.yaml.gotmpl` - **MODIFIED**
   - Line 110: Added `pattern1-tpu-overrides.yaml` to gke_tpu environment
   - Line 79: Disabled GKE monitoring (`enabled: false`)

### Existing Files (Referenced)
1. `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/ms-inference-scheduling/values_tpu.yaml` - TPU base configuration (overridden by pattern1-tpu-overrides.yaml)
2. `/home/jhull/devel/rhaiis-test/11009103-jhull-svc-pull-secret.yaml` - Red Hat registry credentials
3. `/home/jhull/devel/rhaiis-test/tpu-cluster-setup.md` - TPU cluster creation guide

## Key Learnings

### TPU-Specific Considerations

1. **XLA Precompilation During Startup**: vLLM performs XLA compilation during pod initialization (takes ~151 seconds). Pod only becomes Ready after compilation completes. First inference request after Ready is fast (~0.5s).

2. **GKE Warden Enforcement**: ct6e-standard-4t nodes with 2x2 topology MUST request all 4 chips. You cannot request fewer chips - GKE Warden enforces requesting all chips for the topology. For Pattern 1: `google.com/tpu: 4` (mandatory).

3. **Topology Configuration**: TPU_CHIPS_PER_HOST_BOUNDS must match the requested chips:
   - 4 chips (TP=4) → `2,2,1` (2x2 topology) - **Pattern 1 configuration**
   - 8 chips (TP=8) → `2,4,1` (2x4 topology)
   - **Note**: Not all models work with TP=4 (tensor sharding requirements vary by architecture)
   - **Pattern 1 uses `2,2,1` for Qwen/Qwen2.5-3B-Instruct** (3B model works well with TP=4)

4. **Model Selection for TP=4**: Small models like gemma-2b-it don't work well with TP=4 (tensor sharding errors). Use 3B+ models:
   - **Recommended**: Qwen/Qwen2.5-3B-Instruct, microsoft/Phi-3-mini-4k-instruct (3.8B)
   - **Also Works**: mistralai/Mistral-7B-Instruct-v0.3, google/gemma-2-9b-it

5. **Node Selector**: TPU pods require both `cloud.google.com/gke-tpu-topology: "2x2"` and `cloud.google.com/gke-tpu-accelerator: "tpu-v6e-slice"` labels.

6. **Extended Startup**: TPU initialization (2-3 min) + model download (1-2 min first time) + XLA precompilation (2.5 min) = 5-7 min total cold start. Plan startup probes with `failureThreshold: 60`.

7. **HTTPRoute Required**: GKE Gateway requires manual HTTPRoute creation to connect to InferencePool. Not created automatically by helmfile. Without HTTPRoute: "fault filter abort" errors.

8. **JAX/XLA Backend**: vLLM uses JAX for TPU, not PyTorch. Different metrics and performance characteristics.

9. **Cost**: TPU v6e is expensive (~$5/hour for 4 chips vs ~$0.35/hour for 1 T4 GPU). Use auto-scaling aggressively to control costs.

## Additional Resources

- [GKE AI Labs - TPU Deployment Guide](https://gke-ai-labs.dev)
- [vLLM TPU Documentation](https://docs.vllm.ai/en/latest/getting_started/tpu-installation.html)
- [Google Cloud TPU v6e Documentation](https://cloud.google.com/tpu/docs/v6e)
- [llm-d GitHub Repository](https://github.com/llm-d)
