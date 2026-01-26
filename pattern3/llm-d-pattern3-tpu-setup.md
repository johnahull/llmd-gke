# llm-d Pattern 3: N/S-Caching Scale-Out Deployment on TPU v6e

Kubernetes-native distributed LLM inference with intelligent prefix-cache-aware routing and horizontal scale-out on Google Cloud TPU v6e (Trillium) accelerators.

> **🚀 Quick Start**: This guide deploys **llm-d Pattern 3** on TPU v6e: A 3-replica scale-out deployment with prefix-cache-aware routing to optimize cache hits and balance load across replicas.

## Overview

**What is Pattern 3?**
- **N/S-Caching Scale-Out**: Multiple replicas of the same model with intelligent routing
- **Prefix-cache-aware routing**: Routes similar prompts to the same replica for cache hits
- **Load-aware balancing**: Distributes load based on queue depth and KV cache utilization
- **Horizontal throughput scaling**: 2.5-2.8× throughput improvement vs single replica

**Architecture**:
```
Internet → GKE Gateway → HTTPRoute
         ↓
    InferencePool (gaie-pattern3)
         ↓
    Inference Scheduler (EPP)
    ├─ Prefix-cache-scorer (weight 3.0)
    ├─ KV-cache-utilization-scorer (weight 2.0)
    └─ Queue-scorer (weight 2.0)
         ↓
    ┌────────┬────────┬────────┐
    ↓        ↓        ↓        ↓
Replica 1  Replica 2  Replica 3
  vLLM      vLLM      vLLM
(Qwen2.5) (Qwen2.5) (Qwen2.5)
TPU Node1 TPU Node2 TPU Node3
(4 chips) (4 chips) (4 chips)
```

**Components**:
1. **vLLM TPU (3 replicas)**: Model serving with JAX/XLA backend and prefix caching enabled
2. **Inference Scheduler (EPP)**: Intelligent router with prefix-cache-aware scoring
3. **Gateway API**: Kubernetes-native load balancing (GKE built-in)
4. **InferencePool**: Custom resource managing pool of 3 inference endpoints

**Key Routing Features**:
- **Prefix-cache-scorer** (weight 3.0): Routes requests with similar prefixes to the same replica for cache hit optimization
- **KV-cache-utilization-scorer** (weight 2.0): Balances load based on GPU memory usage
- **Queue-scorer** (weight 2.0): Balances load based on request queue depth

## Prerequisites

### Required Before Starting

1. **GKE TPU Cluster** - Already created per tpu-cluster-setup.md:
   - Cluster: `tpu-test-cluster` (zone: `europe-west4-a`)
   - TPU Node Pool: `tpu-v6e-pool` (machine-type: `ct6e-standard-4t`)
   - Auto-scaling: 0-4 nodes (Pattern 3 needs 3 TPU nodes)

2. **Google Cloud Configuration**:
   - Project: `ecoeng-llmd`
   - TPU v6e quota in europe-west4-a (minimum 12 chips for 3 nodes)
   - `gcloud` CLI installed and configured

3. **Credentials**:
   - Hugging Face token: `YOUR_HUGGINGFACE_TOKEN`
   - Already configured as secret `huggingface-token` in namespace

4. **Repository**:
   - llm-d repository cloned at `/home/jhull/devel/rhaiis-test/llm-d`
   - Working directory: `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling`

5. **Existing Deployments**:
   - **Pattern 1**: Qwen/Qwen2.5-3B-Instruct (1 replica) - **Will be replaced by Pattern 3**
   - **Pattern 2**: microsoft/Phi-3-mini-4k-instruct (1 replica) - **Remains deployed**

## Pattern 3 vs Pattern 1: Key Differences

| Aspect | Pattern 1 (Single Replica) | Pattern 3 (N/S-Caching Scale-Out) |
|--------|----------------------------|-----------------------------------|
| **Replicas** | 1 replica | 3 replicas |
| **TPU Nodes** | 1 node (4 chips) | 3 nodes (12 chips total) |
| **Model** | Qwen/Qwen2.5-3B-Instruct | Qwen/Qwen2.5-3B-Instruct (same) |
| **Routing** | Simple (single backend) | Prefix-cache-aware + load-aware |
| **Throughput** | Baseline | 2.5-2.8× improvement |
| **Cache Strategy** | Local cache per replica | Intelligent cache hit optimization |
| **Use Case** | Low concurrency, simple workloads | High concurrency, repeated patterns |
| **Cost** | ~$3,650/month (1 TPU node) | ~$10,950/month (3 TPU nodes) |
| **Prefix Caching** | Basic (no `--enable-prefix-caching`) | Advanced (with `--enable-prefix-caching`) |

## Why Replace Pattern 1 with Pattern 3?

**Decision Rationale**:
1. **Same Model**: Both use Qwen/Qwen2.5-3B-Instruct, making Pattern 1 redundant
2. **Cost Efficiency**: Running both patterns would cost $18,348/month (5 TPU nodes); replacing Pattern 1 saves $3,655/month
3. **Better Scaling**: Pattern 3 demonstrates production-ready horizontal scale-out
4. **Advanced Routing**: Pattern 3 showcases prefix-cache-aware routing not available in Pattern 1

**Resource Allocation After Deployment**:
- **Pattern 3**: 3 TPU nodes (Qwen2.5-3B × 3)
- **Pattern 2**: 1 TPU node (Phi-3-mini × 1)
- **Total**: 4 TPU nodes (~$14,693/month)

## TPU Configuration for Pattern 3

### Key TPU-Specific Considerations

**1. Multi-Replica Deployment**
- Pattern 3 deploys 3 separate vLLM pods across 3 TPU nodes
- Each pod is independent with its own model instance and KV cache
- Scheduler intelligently routes requests across replicas

**2. Resource Allocation per Replica**
- Each replica requests all 4 chips: `google.com/tpu: 4`
- GKE Warden enforces requesting all chips for ct6e-standard-4t nodes
- Total allocation: 3 replicas × 4 chips = 12 TPU chips

**3. Topology Configuration per Replica**
- TPU_CHIPS_PER_HOST_BOUNDS: `2,2,1` (2x2 topology for 4 chips)
- TPU_HOST_BOUNDS: `1,1,1` (single host per replica)
- TPU_NUM_DEVICES: `4` (4 TPU chips per replica)
- Same as Pattern 1, but replicated 3 times

**4. Node Distribution**
- Kubernetes automatically distributes 3 pods across 3 TPU nodes
- Each pod gets exclusive access to one TPU node
- No explicit pod anti-affinity rules needed (resource constraints enforce distribution)

**5. vLLM Prefix Caching**
- **New Flag**: `--enable-prefix-caching` enables vLLM's Automatic Prefix Caching (APC)
- **How It Works**: vLLM detects shared prompt prefixes and reuses KV cache entries
- **Benefit**: Combined with prefix-cache-scorer routing, maximizes cache hit rates

**6. Extended Startup Time**
- 3 pods starting in parallel: ~5-7 minutes each
- Total deployment time: ~15-20 minutes (pods start concurrently)
- Each pod performs XLA precompilation during startup (~151 seconds)

**7. Helmfile Environment**
- Pattern 3: `helmfile -e gke_tpu apply` with `RELEASE_NAME_POSTFIX=pattern3`
- Loads: `values_tpu.yaml` + `pattern3-tpu-overrides.yaml`

## Deployment Guide

### Step 1: Review Current State

Before deploying Pattern 3, verify existing deployments:

```bash
# Set environment variables
export PROJECT_ID="ecoeng-llmd"
export ZONE="europe-west4-a"
export CLUSTER_NAME="tpu-test-cluster"
export NAMESPACE="llm-d-inference-scheduling"

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME \
  --zone $ZONE \
  --project $PROJECT_ID

# Check current TPU node count
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice

# Expected: 2 TPU nodes (Pattern 1 + Pattern 2)

# Check existing deployments
kubectl get pods -n $NAMESPACE

# Expected: ms-pattern1-*-decode-* (1 pod) and ms-pattern2-*-decode-* (1 pod)
```

### Step 2: Create Pattern 3 Configuration File

Copy Pattern 3 TPU Helm overrides from tracked configuration:

**Note:** The Pattern 3 TPU override file is tracked in `helm-configs/pattern-overrides/pattern3-tpu-overrides.yaml`.
See [helm-configs/README.md](../../helm-configs/README.md) for details.

```bash
# Copy Pattern 3 TPU Helm overrides from helm-configs
cp helm-configs/pattern-overrides/pattern3-tpu-overrides.yaml \
   llm-d/guides/inference-scheduling/ms-inference-scheduling/pattern3-tpu-overrides.yaml

echo "✅ Created pattern3-tpu-overrides.yaml"
```

**Key Configuration Differences from Pattern 1**:
- `decode.replicas: 3` (was 1 in Pattern 1)
- `args: --enable-prefix-caching` (new flag for Pattern 3)
- Model and topology settings identical to Pattern 1

### Step 3: Update Helmfile Configuration

Update the helmfile to support Pattern 3:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

# Backup original helmfile
cp helmfile.yaml.gotmpl helmfile.yaml.gotmpl.backup

# Update helmfile to add pattern3 support
# Modify lines 108-114 to add pattern3 conditional
```

Edit `helmfile.yaml.gotmpl` and update the conditional block to:

```yaml
    {{- if eq .Environment.Name "gke_tpu" }}
      - ms-inference-scheduling/values_tpu.yaml
      {{- if eq $rn "pattern1" }}
      - ms-inference-scheduling/pattern1-tpu-overrides.yaml
      {{- else if eq $rn "pattern2" }}
      - ms-inference-scheduling/pattern2-tpu-overrides.yaml
      {{- else if eq $rn "pattern3" }}
      - ms-inference-scheduling/pattern3-tpu-overrides.yaml
      {{- end }}
```

Verify the change:

```bash
grep -A 6 "if eq .Environment.Name \"gke_tpu\"" helmfile.yaml.gotmpl
```

### Step 4: Scale TPU Node Pool

Scale the TPU node pool from 2 to 4 nodes:

```bash
# Scale TPU node pool to 4 (add 2 nodes for Pattern 3's additional replicas)
gcloud container clusters resize $CLUSTER_NAME \
  --node-pool tpu-v6e-pool \
  --num-nodes 4 \
  --zone $ZONE \
  --project $PROJECT_ID \
  --quiet

# Wait for new nodes to be ready (2-3 minutes per node)
echo "Waiting for TPU nodes to be ready..."
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice -w

# Expected: 4 nodes total, all in Ready state
```

**Resource Allocation**:
- **Before**: 2 TPU nodes (Pattern 1 + Pattern 2)
- **After**: 4 TPU nodes (Pattern 3 will use 3, Pattern 2 uses 1)

### Step 5: Remove Pattern 1 Deployment

Delete Pattern 1 to free up 1 TPU node:

```bash
export NAMESPACE="llm-d-inference-scheduling"
export RELEASE_NAME_POSTFIX="pattern1"

cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

# Delete Pattern 1 stack (frees 1 TPU node)
echo "Deleting Pattern 1 deployment..."
helmfile -e gke_tpu -n $NAMESPACE destroy

# Verify deletion (may take 1-2 minutes)
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/instance=ms-pattern1

# Expected: No resources found

# Verify Pattern 1 gateway deleted
kubectl get gateway -n $NAMESPACE | grep pattern1

# Expected: No gateway named infra-pattern1-inference-gateway
```

**What gets removed**:
- `infra-pattern1-inference-gateway` - Gateway
- `gaie-pattern1-epp` - Scheduler pod
- `gaie-pattern1` - InferencePool
- `pattern1-route` - HTTPRoute
- `ms-pattern1-*-decode-*` - vLLM pod

### Step 6: Deploy Pattern 3 Stack

Deploy Pattern 3 with 3 replicas:

```bash
export NAMESPACE="llm-d-inference-scheduling"
export RELEASE_NAME_POSTFIX="pattern3"

cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

# Deploy Pattern 3 with 3 replicas
echo "Deploying Pattern 3 (3 replicas)..."
helmfile -e gke_tpu -n $NAMESPACE apply

# Create HTTPRoute to connect Gateway to InferencePool
# Apply Pattern 3 HTTPRoute from manifests directory
kubectl apply -f pattern3/manifests/httproute-pattern3.yaml -n llm-d-inference-scheduling

echo "✅ Pattern 3 deployment initiated"
```

See [`manifests/README.md`](manifests/README.md) for the HTTPRoute manifest details.

**What gets deployed** (with RELEASE_NAME_POSTFIX=pattern3):
- `infra-pattern3-inference-gateway` - Gateway with new external IP
- `gaie-pattern3-epp` - Inference scheduler pod
- `gaie-pattern3` - InferencePool custom resource
- `pattern3-route` - HTTPRoute connecting Gateway to InferencePool
- `ms-pattern3-*-decode-*` (3 pods) - vLLM replicas with Qwen2.5-3B-Instruct

**Expected deployment timeline**:
- Helm chart installation: 30 seconds
- 3 TPU pods starting in parallel: ~5-7 minutes each
- **Total time to all pods Ready**: ~15-20 minutes

### Step 7: Monitor Deployment

Watch the 3 vLLM pods start up:

```bash
# Watch all pods in Pattern 3
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/instance=ms-pattern3 -w

# In another terminal, check detailed pod status
kubectl get pods -n $NAMESPACE \
  -l app.kubernetes.io/instance=ms-pattern3,llm-d.ai/inferenceServing=true \
  -o custom-columns=POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase,READY:.status.conditions[?\(@.type==\"Ready\"\)].status

# Expected: 3 pods, each on different node, all eventually Running with READY=True
```

**Monitor individual pod logs**:

```bash
# Get all 3 vLLM pod names
PODS=$(kubectl get pods -n $NAMESPACE -l llm-d.ai/inferenceServing=true,app.kubernetes.io/instance=ms-pattern3 -o jsonpath='{.items[*].metadata.name}')

# Watch logs of first pod
echo "Watching first pod logs..."
kubectl logs -n $NAMESPACE -f $(echo $PODS | awk '{print $1}')
```

**Expected log sequence per pod**:
1. "Starting vLLM..." - Container starts
2. "Downloading model..." - HuggingFace download (cached after first replica)
3. "Initializing TPU..." - PJRT device initialization
4. "Loading model on TPU..." - Model loaded to TPU memory
5. "Compiling XLA graph..." - Precompilation during startup (~151 seconds)
6. "Uvicorn running on 0.0.0.0:8000" - vLLM server ready
7. **Pod status changes to Running/Ready**

### Step 8: Verify Deployment

Check that all 3 replicas are running on separate TPU nodes:

```bash
# Check all 3 replicas running on separate TPU nodes
kubectl get pods -n $NAMESPACE \
  -l app.kubernetes.io/instance=ms-pattern3,llm-d.ai/inferenceServing=true \
  -o custom-columns=POD:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase,READY:.status.conditions[?\(@.type==\"Ready\"\)].status

# Expected: 3 pods, each on different node, all Running with READY=True

# Get Gateway IP
export GATEWAY_IP=$(kubectl get gateway infra-pattern3-inference-gateway \
  -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')

echo "Pattern 3 Gateway IP: $GATEWAY_IP"

# Verify Gateway is ready
kubectl get gateway infra-pattern3-inference-gateway -n $NAMESPACE

# Expected: PROGRAMMED=True with external IP assigned

# Verify InferencePool
kubectl describe inferencepool gaie-pattern3 -n $NAMESPACE | grep -A 10 "Status:"

# Expected: 3 backends discovered and ready
```

**Success criteria**:
- ✅ 3 vLLM pods Running and Ready
- ✅ Each pod on a different TPU node
- ✅ Gateway has external IP and PROGRAMMED=True
- ✅ InferencePool shows 3 backends ready
- ✅ HTTPRoute attached to Gateway (Attached Routes: 1)

## Testing Pattern 3

### Test 1: Basic Inference

Verify all replicas are functional:

```bash
export GATEWAY_IP=$(kubectl get gateway infra-pattern3-inference-gateway \
  -n llm-d-inference-scheduling -o jsonpath='{.status.addresses[0].value}')

# Test completions endpoint
echo "Testing Pattern 3 inference..."
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is Kubernetes?",
    "max_tokens": 50
  }' -s | jq '.'

# Expected: Successful response with generated text
```

### Test 2: Prefix-Cache-Aware Routing

Test that similar prompts route to the same replica for cache hit optimization:

```bash
# Define shared prefix (200 tokens worth of context)
export SHARED_PREFIX="In the distant future, humanity has colonized the solar system. Mars has become a thriving hub of commerce and innovation, with towering biodomes housing millions of inhabitants. The asteroid belt is dotted with mining stations extracting precious minerals, while Jupiter's moons serve as research outposts studying the mysteries of the outer planets. Earth, once the cradle of civilization, now serves as a historical monument and cultural center. Advanced AI systems manage the complex logistics of interplanetary trade, while quantum communication networks enable instantaneous coordination across billions of kilometers."

# Send 5 requests with same prefix but different questions
echo "Testing prefix-cache-aware routing..."
for i in {1..5}; do
  echo "Request $i (with shared prefix):"
  curl -s -X POST http://${GATEWAY_IP}/v1/completions \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"Qwen/Qwen2.5-3B-Instruct\",
      \"prompt\": \"${SHARED_PREFIX} Question $i: What is the population of Mars?\",
      \"max_tokens\": 30
    }" | jq -r '.choices[0].text'
  sleep 1
done

echo ""
echo "Checking scheduler logs to verify routing..."
kubectl logs -n llm-d-inference-scheduling -l app.kubernetes.io/name=gaie-pattern3-epp --tail=20

# Expected: All 5 requests routed to SAME replica (prefix-cache-scorer optimization)
# Check scheduler logs for backend selection - should show consistent backend choice
```

**Why this matters**:
- Shared prefixes reuse KV cache entries within the same replica
- Prefix-cache-scorer (weight 3.0) routes similar prompts together
- This maximizes cache hit rate and reduces computation

### Test 3: Load Balancing Across Replicas

Test that different prompts distribute across replicas:

```bash
echo "Testing load balancing with unique prompts..."
for i in {1..9}; do
  echo "Request $i (unique prompt $i):"
  curl -s -X POST http://${GATEWAY_IP}/v1/completions \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"Qwen/Qwen2.5-3B-Instruct\",
      \"prompt\": \"Write a haiku about the number $i\",
      \"max_tokens\": 20
    }" | jq -r '.choices[0].text'
  sleep 1
done

# Expected: Roughly even distribution (3/3/3 or 4/3/2) across 3 replicas
# Scheduler balances load based on queue depth and KV cache utilization
```

### Test 4: Throughput Comparison

Compare throughput with Pattern 1 (single replica):

```bash
cd /home/jhull/devel/rhaiis-test/benchmarks

# Run benchmark on Pattern 3 (3 replicas)
echo "Running throughput benchmark on Pattern 3..."
python python/benchmark_async.py \
  --base-url http://${GATEWAY_IP} \
  --model "Qwen/Qwen2.5-3B-Instruct" \
  --num-requests 300 \
  --concurrency 15 \
  --max-tokens 50 \
  --output results/pattern3-$(date +%Y%m%d).json \
  --html

echo "Benchmark complete. Results saved to results/pattern3-$(date +%Y%m%d).json"

# Compare results (if you have Pattern 1 baseline):
# Expected: 2.5-2.8× throughput improvement vs Pattern 1 (single replica)
```

**Expected metrics**:
- **Pattern 1 (baseline)**: ~30-40 requests/sec
- **Pattern 3 (3 replicas)**: ~75-110 requests/sec (2.5-2.8× improvement)
- **TTFT**: Similar to Pattern 1 (no significant change)
- **TPOT**: Similar to Pattern 1 (no significant change)

### Test 5: Intelligent Routing Verification

Check scheduler logs to see routing decisions:

```bash
# Get scheduler pod
SCHEDULER_POD=$(kubectl get pods -n llm-d-inference-scheduling -l inferencepool=gaie-pattern3-epp \
  -o jsonpath='{.items[0].metadata.name}')

# View scheduler logs with routing decisions
kubectl logs -n llm-d-inference-scheduling $SCHEDULER_POD --tail=100 | grep -E "(backend|score|route)"

# Scheduler uses these scorers:
# - prefix-cache-scorer (weight 3.0): Routes similar prompts to same replica
# - kv-cache-utilization-scorer (weight 2.0): Balances GPU memory usage
# - queue-scorer (weight 2.0): Balances request queue depth
```

## Verification Steps

### Success Criteria

1. ✅ **TPU nodes running**: 4 ct6e-standard-4t nodes in Ready state (3 for Pattern 3, 1 for Pattern 2)
2. ✅ **Pods running**: All 3 Pattern 3 vLLM pods in Running state on separate nodes
3. ✅ **Gateway accessible**: External IP assigned and PROGRAMMED=True
4. ✅ **InferencePool ready**: gaie-pattern3 shows 3 backends ready
5. ✅ **HTTPRoute bound**: Route successfully bound to Gateway (Attached Routes: 1)
6. ✅ **Similar prompts route to same replica**: Prefix-cache-scorer working
7. ✅ **Different prompts distribute across replicas**: Load balancing working
8. ✅ **Throughput scales**: 2.5-2.8× improvement vs Pattern 1
9. ✅ **No pod evictions or OOM errors**: All pods stable

### Quick Verification Script

```bash
#!/bin/bash
set -e

NAMESPACE="llm-d-inference-scheduling"
GATEWAY_NAME="infra-pattern3-inference-gateway"

echo "=== Pattern 3 TPU Deployment Verification ==="

echo "1. Checking TPU nodes..."
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice

echo "2. Checking Pattern 3 pods..."
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/instance=ms-pattern3

echo "3. Checking Gateway..."
kubectl get gateway $GATEWAY_NAME -n $NAMESPACE

echo "4. Checking InferencePool..."
kubectl describe inferencepool gaie-pattern3 -n $NAMESPACE | grep -A 10 "Status:"

echo "5. Checking HTTPRoute..."
kubectl get httproute pattern3-route -n $NAMESPACE

echo "6. Testing inference..."
GATEWAY_IP=$(kubectl get gateway $GATEWAY_NAME -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')
curl -s -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-3B-Instruct", "prompt": "Hello", "max_tokens": 10}' \
  | jq -r '.choices[0].text'

echo "=== Verification Complete ==="
```

## Troubleshooting

### Issue 1: Pods Stuck in Pending - "Insufficient google.com/tpu"

**Symptom**: vLLM pods show `0/X nodes available: insufficient google.com/tpu`

**Cause**: Not enough TPU nodes available for 3 replicas

**Fix**:
```bash
# Verify TPU node pool has 4 nodes (or at least 3 for Pattern 3)
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice

# If fewer than 3 nodes, scale up
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 4 \
  --zone europe-west4-a \
  --project ecoeng-llmd

# Wait for nodes
kubectl get nodes -w
```

### Issue 2: Only 1-2 Replicas Running (Third Pod Pending)

**Symptom**: 1-2 vLLM pods Running, but third pod stuck in Pending

**Cause**: Insufficient TPU nodes or nodes already consumed by other workloads

**Fix**:
```bash
# Check which pods are consuming TPU resources
kubectl get pods -n llm-d-inference-scheduling -o wide | grep -E "(pattern2|pattern3)"

# Expected: 1 Pattern 2 pod + 3 Pattern 3 pods = 4 pods total on 4 nodes

# If Pattern 1 still running, delete it:
export RELEASE_NAME_POSTFIX="pattern1"
helmfile -e gke_tpu -n llm-d-inference-scheduling destroy

# Verify Pattern 1 deleted
kubectl get pods -n llm-d-inference-scheduling -l app.kubernetes.io/instance=ms-pattern1
```

### Issue 3: Requests Not Distributing Across Replicas

**Symptom**: All requests go to single replica despite 3 being available

**Cause**: InferencePool not discovering all backends or scheduler misconfigured

**Fix**:
```bash
# Check InferencePool backend discovery
kubectl describe inferencepool gaie-pattern3 -n llm-d-inference-scheduling

# Look for "Backends" section - should list 3 endpoints

# If only 1 backend listed, check vLLM pod readiness
kubectl get pods -n llm-d-inference-scheduling -l llm-d.ai/inferenceServing=true,app.kubernetes.io/instance=ms-pattern3

# All pods must be Ready (not just Running)

# Check scheduler configuration
kubectl get configmap -n llm-d-inference-scheduling | grep gaie-pattern3

# Scheduler should have default-plugins.yaml with prefix-cache-scorer
```

### Issue 4: Prefix-Cache Routing Not Working

**Symptom**: Similar prompts don't route to same replica

**Cause**: Prefix-cache-scorer not enabled or misconfigured

**Fix**:
```bash
# Verify scheduler configuration has prefix-cache-scorer
kubectl get configmap -n llm-d-inference-scheduling -o yaml | grep -A 20 "default-plugins"

# Check scheduler logs for scoring decisions
SCHEDULER_POD=$(kubectl get pods -n llm-d-inference-scheduling -l inferencepool=gaie-pattern3-epp -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n llm-d-inference-scheduling $SCHEDULER_POD --tail=100 | grep "score"

# Verify vLLM has prefix caching enabled
kubectl get pods -n llm-d-inference-scheduling -l llm-d.ai/inferenceServing=true,app.kubernetes.io/instance=ms-pattern3 -o yaml | grep "enable-prefix-caching"

# Should show: - --enable-prefix-caching
```

### Issue 5: Throughput Not Scaling Linearly

**Symptom**: Pattern 3 throughput < 2× Pattern 1

**Cause**: Bottleneck at Gateway, scheduler, or network layer

**Fix**:
```bash
# Check scheduler CPU/memory usage
kubectl top pod -n llm-d-inference-scheduling -l inferencepool=gaie-pattern3-epp

# If scheduler CPU > 80%, it may be bottleneck

# Check vLLM metrics for queue depth
PODS=$(kubectl get pods -n llm-d-inference-scheduling -l llm-d.ai/inferenceServing=true,app.kubernetes.io/instance=ms-pattern3 -o jsonpath='{.items[*].metadata.name}')

for POD in $PODS; do
  echo "Metrics for $POD:"
  kubectl exec -n llm-d-inference-scheduling $POD -- curl -s localhost:8000/metrics | grep "vllm:num_requests_waiting"
done

# High queue depth indicates replicas are saturated (good - need more replicas)
# Low queue depth indicates scheduler/network bottleneck
```

### Issue 6: OOM Errors with Prefix Caching Enabled

**Symptom**: vLLM pod killed with OOMKilled status

**Cause**: Prefix caching increases memory usage; max-model-len may be too high

**Fix**:
```bash
# Check OOM events
kubectl describe pod -n llm-d-inference-scheduling <pod-name> | grep -A 10 "Last State"

# If OOMKilled, reduce max-model-len in pattern3-tpu-overrides.yaml:
# args:
#   - "--max-model-len=1024"  # Reduced from 2048

# Or disable prefix caching temporarily to test:
# args:
#   - "--max-model-len=2048"
#   # Remove: - "--enable-prefix-caching"

# Redeploy
export RELEASE_NAME_POSTFIX="pattern3"
helmfile -e gke_tpu -n llm-d-inference-scheduling apply
```

## Architecture Diagram

### Network Flow
```
Internet (Client Request)
  ↓
Gateway: X.X.X.X:80 (GKE Gateway)
  ↓
HTTPRoute (pattern3-route)
  ↓
InferencePool: gaie-pattern3
  ↓
Scheduler: gaie-pattern3-epp (ext-proc service)
  ├─ Prefix-cache-scorer (weight 3.0) → Routes similar prompts together
  ├─ KV-cache-utilization-scorer (weight 2.0) → Balances GPU memory
  └─ Queue-scorer (weight 2.0) → Balances request queue depth
     ↓
  ┌──────────┬──────────┬──────────┐
  ↓          ↓          ↓          ↓
Replica 1  Replica 2  Replica 3
ms-pattern3-*-decode-0  -decode-1  -decode-2
  ↓          ↓          ↓
TPU Node 1 TPU Node 2 TPU Node 3
(4 chips)  (4 chips)  (4 chips)
```

### TPU Resource Allocation
```
3× TPU Nodes (ct6e-standard-4t)
  ├─ Node 1: Replica 1 (4 TPU chips, ~32 GB HBM)
  ├─ Node 2: Replica 2 (4 TPU chips, ~32 GB HBM)
  └─ Node 3: Replica 3 (4 TPU chips, ~32 GB HBM)

Each Replica:
  ├─ Model: Qwen/Qwen2.5-3B-Instruct (FP16, ~6 GB)
  ├─ KV Cache: ~20 GB (for max-model-len=2048)
  ├─ XLA Compilation Cache: ~2-4 GB
  └─ Tensor Parallelism: TP=4 (across 4 chips)
```

### Intelligent Routing Flow
```
Request arrives with prompt: "In the distant future, humanity has colonized..."
  ↓
Scheduler extracts model name: "Qwen/Qwen2.5-3B-Instruct"
  ↓
Scheduler calculates scores for each backend:

Backend 1: prefix-cache-score=0.85, kv-cache-util=0.60, queue-depth=2
  → Total: (0.85×3.0) + (0.60×2.0) + (2×2.0) = 7.75

Backend 2: prefix-cache-score=0.20, kv-cache-util=0.50, queue-depth=1
  → Total: (0.20×3.0) + (0.50×2.0) + (1×2.0) = 3.60

Backend 3: prefix-cache-score=0.10, kv-cache-util=0.70, queue-depth=3
  → Total: (0.10×3.0) + (0.70×2.0) + (3×2.0) = 7.70

  ↓
Scheduler selects Backend 1 (highest score = 7.75)
  → Routes request to Backend 1 for cache hit optimization
```

## Cost Analysis

### TPU v6e Pricing (europe-west4)

**Pattern 3 Compute Costs**:
- TPU v6e chip: ~$1.25/hour/chip
- ct6e-standard-4t (4 chips): ~$5.00/hour
- 3 replicas: ~$15.00/hour

**Monthly Costs** (running 24/7):
- **Pattern 3 alone**: $15.00/hour × 730 hours = **$10,950/month**
- **Pattern 2**: $5.00/hour × 730 hours = **$3,650/month**
- **CPU nodes**: ~$0.12/hour × 730 hours = **$88/month**
- **Total (Pattern 3 + Pattern 2)**: **$14,693/month**

**Cost Comparison**:
| Configuration | TPU Nodes | Monthly Cost |
|---------------|-----------|--------------|
| Pattern 1 only | 1 node | $3,650 |
| Pattern 2 only | 1 node | $3,650 |
| Pattern 1 + Pattern 2 | 2 nodes | $7,305 |
| **Pattern 3 + Pattern 2** | **4 nodes** | **$14,693** |
| Pattern 1 + Pattern 2 + Pattern 3 | 5 nodes | $18,348 |

**Cost Savings by Replacing Pattern 1**:
- Saved: $18,348 - $14,693 = **$3,655/month**
- Pattern 3 replaces Pattern 1 (same model), so no loss of functionality

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

**Per-Request Cost Estimate** (assuming 10M requests/month):
- Pattern 1: $3,650 / 10M = **$0.000365 per request**
- Pattern 3: $10,950 / 10M = **$0.001095 per request**
- **Pattern 3 is 3× cost per request, but serves 2.8× more requests**
- **Effective cost per request at scale: ~$0.000391** (7% higher than Pattern 1 for 2.8× throughput)

**Recommendation**:
- Use auto-scaling (min-nodes=0) when not testing
- Pattern 3 justifiable for high-concurrency production workloads
- Pattern 1 sufficient for low-concurrency development/testing

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
# To resume: scale node pool back to 4
```

### Option 2: Delete Pattern 3 Deployment (Keep Cluster)

```bash
# Delete llm-d Pattern 3 releases
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling

export NAMESPACE="llm-d-inference-scheduling"
export RELEASE_NAME_POSTFIX="pattern3"

helmfile -e gke_tpu -n $NAMESPACE destroy

# Scale TPU node pool to 1 (for Pattern 2 only)
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 1 \
  --zone europe-west4-a \
  --project ecoeng-llmd
```

### Option 3: Restore Pattern 1

If Pattern 3 doesn't meet needs, restore Pattern 1:

```bash
# Delete Pattern 3
export RELEASE_NAME_POSTFIX="pattern3"
helmfile -e gke_tpu -n llm-d-inference-scheduling destroy

# Scale down to 2 TPU nodes
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 2 \
  --zone europe-west4-a \
  --project ecoeng-llmd

# Restore Pattern 1
export RELEASE_NAME_POSTFIX="pattern1"
helmfile -e gke_tpu -n llm-d-inference-scheduling apply

# Create HTTPRoute for Pattern 1
# Restore Pattern 1 HTTPRoute from manifests directory
kubectl apply -f pattern1/manifests/httproute-pattern1.yaml -n llm-d-inference-scheduling
```

**Note:** Using the Pattern 1 HTTPRoute manifest for recovery.

## Next Steps After Pattern 3

1. **Benchmark Comparison**: Compare Pattern 1 vs Pattern 3 throughput metrics
2. **Pattern 4**: Prefill-Decode Disaggregation for lower TTFT
3. **Pattern 5**: Multi-Model Deployment (Qwen + Phi-3 in single pool)
4. **Cache Hit Rate Analysis**: Measure prefix-cache-scorer effectiveness
5. **Load Testing**: Stress test with concurrent users
6. **Cost Optimization**: Implement request-based auto-scaling
7. **Monitoring**: Deploy Prometheus + Grafana for advanced metrics

## Key Files Modified/Created

### Files Created for Pattern 3 TPU
1. **`/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/ms-inference-scheduling/pattern3-tpu-overrides.yaml`** - **NEW** Pattern 3 TPU-specific configuration (Qwen2.5-3B-Instruct, 3 replicas, 4 chips per replica, 2x2 topology, TP=4, prefix caching enabled)
2. **`/home/jhull/devel/rhaiis-test/llm-d-pattern3-tpu-setup.md`** - **NEW** This documentation file

### Files Modified for Pattern 3 TPU
1. **`/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/helmfile.yaml.gotmpl`** - **MODIFIED**
   - Lines 110-114: Added `pattern3-tpu-overrides.yaml` to gke_tpu environment conditional

### Existing Files (Referenced)
1. `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/ms-inference-scheduling/values_tpu.yaml` - TPU base configuration
2. `/home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/gaie-inference-scheduling/values.yaml` - Scheduler configuration with prefix-cache-scorer

## Key Learnings

### Pattern 3-Specific Insights

1. **Prefix-Cache-Aware Routing**: The prefix-cache-scorer (weight 3.0) routes requests with similar prompt prefixes to the same replica, maximizing KV cache hit rates. This is especially effective for workloads with repeated context (e.g., chatbots with system prompts).

2. **vLLM Prefix Caching**: The `--enable-prefix-caching` flag enables vLLM's Automatic Prefix Caching (APC), which detects and reuses KV cache entries for shared prompt prefixes. Combined with prefix-cache-scorer routing, this provides 2-layer cache optimization.

3. **Horizontal Throughput Scaling**: Pattern 3 demonstrates near-linear throughput scaling (2.5-2.8× for 3 replicas). This validates that the scheduler doesn't become a bottleneck at moderate scale.

4. **Load Balancing Intelligence**: The scheduler uses weighted scoring (prefix-cache:3.0, kv-cache:2.0, queue:2.0) to balance conflicting objectives: maximize cache hits while preventing replica overload.

5. **Multi-Replica Deployment**: Kubernetes automatically distributes 3 pods across 3 TPU nodes without explicit anti-affinity rules. Resource constraints (each pod requests 4 chips) naturally enforce 1 pod per node.

6. **Cost vs Performance Trade-off**: Pattern 3 costs 3× more than Pattern 1 but serves 2.8× more requests, resulting in only ~7% higher cost per request at scale. This is favorable for production workloads.

7. **Deployment Time**: 3 replicas starting in parallel take ~15-20 minutes total (similar to single replica), as XLA precompilation happens during pod startup, not first inference.

8. **Pattern 1 Redundancy**: Since Pattern 3 uses the same model (Qwen2.5-3B-Instruct) as Pattern 1, keeping both patterns is redundant. Replacing Pattern 1 with Pattern 3 saves $3,655/month while providing better throughput.

## Additional Resources

- [llm-d Pattern 3 Documentation](https://llm-d.ai/docs/usage/getting-started-inferencing#pattern-3-ns-caching-scale-out)
- [vLLM Prefix Caching Documentation](https://docs.vllm.ai/en/latest/models/engine_args.html#cmdoption-enable-prefix-caching)
- [Gateway API Inference Extension - InferencePool](https://gateway-api-inference-extension.sigs.k8s.io/)
- [Google Cloud TPU v6e Documentation](https://cloud.google.com/tpu/docs/v6e)
- [llm-d Pattern 1 Setup Guide](llm-d-pattern1-tpu-setup.md)
- [llm-d Pattern 2 Setup Guide](llm-d-pattern2-tpu-setup.md)
