# llm-d Pattern 1: Single Replica Deployment

Industry-standard Kubernetes-native distributed LLM inference framework with intelligent scheduling, providing a foundation for advanced deployment patterns.

> **🚀 Quick Start**: If you're deploying from scratch, jump to the [Quick Start Guide](#quick-start-guide-30-minutes) below. The detailed sections that follow provide background, troubleshooting, and reference information.

## Overview

This guide deploys **llm-d Pattern 1**: A single-replica vLLM deployment with intelligent inference scheduling on GKE with NVIDIA T4 GPUs.

**What is llm-d?**
- Kubernetes-native distributed LLM inference framework
- Intelligent load-aware and prefix-cache-aware routing
- Foundation for scale-out, multi-model, and MoE deployments
- Supports NVIDIA GPUs, AMD GPUs, Google TPUs, Intel XPUs

**Architecture**:
```
Internet → GKE Gateway → Inference Scheduler → vLLM Pod (google/gemma-2b-it)
                              ↓
                        Prometheus metrics
```

**Components**:
1. **vLLM**: Model serving engine (same as RHAIIS)
2. **Inference Gateway**: Request router with intelligent scheduling
3. **Gateway API**: Kubernetes-native load balancing (GKE built-in)

## Deployment Patterns Roadmap

**Pattern 1** (This Guide): Single replica deployment
- 1 vLLM instance with intelligent routing
- Foundation for exploring llm-d capabilities

**Pattern 2**: Multi-model deployment
- Multiple vLLM instances with different models
- Model selection via request routing

**Pattern 3**: N/S-caching scale-out
- Multiple replicas of same model
- Prefix-aware and load-aware routing
- Shared KV cache awareness

**Pattern 4**: MoE with LeaderWorkerSet
- Mixture of Experts models (DeepSeek, Mixtral)
- Data parallelism + Expert parallelism
- Multi-node coordination

**Pattern 5**: P/D disaggregation
- Separate prefill and decode phases
- Specialized scheduling for reduced TTFT
- KV cache transfer between phases

---

## Quick Start Guide (30 minutes)

This guide provides step-by-step instructions to deploy Pattern 1 from scratch. For detailed explanations and troubleshooting, see the full sections below.

### Prerequisites Checklist

Before starting, ensure you have:

- ✅ **GCP Project** with billing enabled
- ✅ **GCP IAM Roles** on your account:
  - `roles/container.admin` (required for RBAC and cluster management)
  - `roles/editor` or `roles/owner` (for resource creation)
- ✅ **Tools installed locally**:
  - `gcloud` CLI (Google Cloud SDK)
  - `kubectl` (Kubernetes CLI)
  - `helm` v3.12.0+
  - `helmfile` v1.1.0+
  - `git`
- ✅ **HuggingFace Token** from https://huggingface.co/settings/tokens

**Request IAM roles** (if needed):
```bash
# Ask your GCP project admin to run:
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:your-email@example.com" \
  --role="roles/container.admin"
```

**Verify permissions**:
```bash
export PROJECT_ID="your-gcp-project-id"

gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)" \
  --format="table(bindings.role)"

# Should show: roles/container.admin, roles/editor or roles/owner
```

### Step 1: Set Environment Variables

```bash
# GCP Configuration
export PROJECT_ID="your-gcp-project-id"
export CLUSTER_NAME="llm-d-cluster"
export REGION="us-central1"
export ZONE="us-central1-a"

# llm-d Configuration
export NAMESPACE="llm-d"
export RELEASE_NAME_POSTFIX="pattern1"

# HuggingFace Token
export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Set gcloud project
gcloud config set project $PROJECT_ID
```

### Step 2: Create GKE Cluster with GPU Support (5 min)

```bash
# Create cluster with CPU nodes
gcloud container clusters create $CLUSTER_NAME \
  --zone $ZONE \
  --machine-type n1-standard-4 \
  --num-nodes 2 \
  --enable-ip-alias \
  --project $PROJECT_ID

# Add GPU node pool with T4 GPUs
gcloud container node-pools create nvidia-t4-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 3 \
  --project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME \
  --zone $ZONE \
  --project $PROJECT_ID

# Verify cluster
kubectl get nodes
# Expected: 3 nodes (2 CPU + 1 GPU)
```

### Step 3: Enable Required GCP APIs (2 min)

```bash
# Enable Gateway API on cluster
gcloud container clusters update $CLUSTER_NAME \
  --gateway-api=standard \
  --zone $ZONE \
  --project $PROJECT_ID

# Enable Network Services API (required for intelligent routing)
gcloud services enable networkservices.googleapis.com --project $PROJECT_ID

# Verify Gateway API is available (takes 1-2 minutes)
sleep 60
kubectl api-resources | grep gateway.networking.k8s.io
# Should show: gateways, httproutes, gatewayclasses
```

### Step 4: Create Proxy-Only Subnet (1 min)

```bash
# Create subnet for GKE Gateway load balancer
gcloud compute networks subnets create proxy-only-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=$REGION \
  --network=default \
  --range=192.168.0.0/23 \
  --project=$PROJECT_ID

# Verify
gcloud compute networks subnets describe proxy-only-subnet \
  --region=$REGION \
  --project=$PROJECT_ID
# Should show: purpose: REGIONAL_MANAGED_PROXY, state: READY
```

### Step 5: Install Gateway Provider CRDs (1 min)

```bash
# Clone llm-d repository
cd ~
git clone https://github.com/llm-d/llm-d.git
cd llm-d/guides/prereq/gateway-provider

# Install CRDs
./install-gateway-provider-dependencies.sh

# Verify
kubectl api-resources --api-group=inference.networking.k8s.io
# Should show: inferencepools, inferenceobjectives
```

### Step 6: Create Namespace and Secrets (1 min)

```bash
# Create namespace
kubectl create namespace $NAMESPACE

# Create HuggingFace token secret
kubectl create secret generic huggingface-token \
  --from-literal=token=$HF_TOKEN \
  --namespace $NAMESPACE

# Verify
kubectl get secret huggingface-token -n $NAMESPACE
# Should show: huggingface-token created
```

### Step 7: Deploy llm-d Pattern 1 (10 min)

```bash
cd ~/llm-d/guides/inference-scheduling

# Deploy all components (infra, scheduler, model service)
helmfile -e gke -n $NAMESPACE apply

# This automatically uses pattern1-overrides.yaml which configures:
# - Model: google/gemma-2b-it
# - Replicas: 1
# - Context length: 2048 tokens
# - GPU utilization: 0.85
```

**Monitor deployment**:
```bash
# Watch all pods (takes 5-10 minutes for model download)
kubectl get pods -n $NAMESPACE -w

# In another terminal, watch model download progress:
kubectl logs -n $NAMESPACE -l llm-d.ai/inferenceServing=true -f
```

**Expected pods** (all should be 1/1 Running):
```
NAME                                     READY   STATUS
gaie-pattern1-epp-xxxxx                  1/1     Running
ms-pattern1-...-decode-xxxxx             1/1     Running
```

Press Ctrl+C when all pods are Running.

### Step 8: Configure Gateway and HTTPRoute (3 min)

```bash
# Force Gateway to detect proxy-only subnet
kubectl annotate gateway infra-pattern1-inference-gateway -n $NAMESPACE \
  force-reconcile="$(date +%s)" --overwrite

# Wait for Gateway to provision (2-3 minutes)
echo "Waiting for Gateway to provision..."
sleep 120

# Check Gateway status
kubectl get gateway infra-pattern1-inference-gateway -n $NAMESPACE -o wide
# Expected: ADDRESS populated, PROGRAMMED True
```

**Create HTTPRoute**:
```bash
cat > /tmp/httproute-pattern1.yaml <<'EOF'
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: llm-d-pattern1-inference-scheduling
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: infra-pattern1-inference-gateway
  rules:
    - backendRefs:
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: gaie-pattern1
        port: 54321
        weight: 1
      matches:
      - path:
          type: PathPrefix
          value: /
EOF

kubectl apply -f /tmp/httproute-pattern1.yaml -n $NAMESPACE

# Verify HTTPRoute
kubectl get httproute -n $NAMESPACE
# Expected: llm-d-pattern1-inference-scheduling created
```

### Step 9: Get Gateway IP and Test (2 min)

```bash
# Get Gateway external IP
export GATEWAY_IP=$(kubectl get gateway infra-pattern1-inference-gateway \
  -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')

echo "Gateway IP: $GATEWAY_IP"

# Test health endpoint
curl http://$GATEWAY_IP/health
# Expected: No output (200 OK) or empty response

# List available models
curl http://$GATEWAY_IP/v1/models
# Expected: JSON with "google/gemma-2b-it" model

# Test inference
curl -X POST http://$GATEWAY_IP/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "What is Kubernetes?",
    "max_tokens": 50
  }'
# Expected: JSON response with generated text
```

### Step 10: Verify Intelligent Routing (1 min)

```bash
# Check scheduler logs
kubectl logs -n $NAMESPACE -l inferencepool=gaie-pattern1-epp --tail=20

# Should show routing plugins loaded:
# - prefix-cache-scorer (weight: 3)
# - kv-cache-utilization-scorer (weight: 2)
# - queue-scorer (weight: 2)
```

### ✅ Deployment Complete!

You now have llm-d Pattern 1 running with:
- **Gateway endpoint**: `http://$GATEWAY_IP` (intelligent routing via scheduler)
- **Model**: google/gemma-2b-it (2B parameters)
- **Intelligent routing**: Prefix-cache-aware, load-aware, queue-aware
- **Ready for**: Benchmarking, scaling to Pattern 2/3

### Quick Reference Commands

**Check status**:
```bash
kubectl get pods -n $NAMESPACE
kubectl get gateway infra-pattern1-inference-gateway -n $NAMESPACE
```

**View logs**:
```bash
# Scheduler logs
kubectl logs -n $NAMESPACE -l inferencepool=gaie-pattern1-epp -f

# vLLM logs
kubectl logs -n $NAMESPACE -l llm-d.ai/inferenceServing=true -f
```

**Scale down (cost savings)**:
```bash
# Scale to 0 (keeps configuration)
kubectl scale deployment --all -n $NAMESPACE --replicas=0

# Scale GPU nodes to 0
gcloud container clusters resize $CLUSTER_NAME \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone $ZONE --project $PROJECT_ID
```

**Scale back up**:
```bash
# Scale GPU nodes to 1
gcloud container clusters resize $CLUSTER_NAME \
  --node-pool nvidia-t4-pool --num-nodes 1 \
  --zone $ZONE --project $PROJECT_ID

# Scale deployments to 1
kubectl scale deployment ms-pattern1-llm-d-modelservice-decode -n $NAMESPACE --replicas=1
```

**Full cleanup**:
```bash
# Delete deployment
helmfile -e gke -n $NAMESPACE destroy

# Delete cluster
gcloud container clusters delete $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID

# Delete proxy-only subnet
gcloud compute networks subnets delete proxy-only-subnet --region=$REGION --project=$PROJECT_ID
```

### Troubleshooting

**Problem: RBAC permission denied during deployment**
- **Solution**: Ensure you have `roles/container.admin` (see Prerequisites)

**Problem: Gateway not getting IP address**
- **Check**: `kubectl describe gateway infra-pattern1-inference-gateway -n $NAMESPACE`
- **Solution**: Verify proxy-only subnet exists and Network Services API is enabled

**Problem: Pod stuck in Pending**
- **Check**: `kubectl describe pod <pod-name> -n $NAMESPACE`
- **Solution**: Verify GPU nodes are running: `kubectl get nodes`

**Problem: "fault filter abort" error when testing Gateway**
- **Solution**: Wait 2-3 minutes for load balancer to fully provision, then retry

For detailed troubleshooting, see the full Troubleshooting section below.

---

## Common Issues (Resolved in Quick Start)

The Quick Start Guide above addresses these common issues. This section documents them for reference.

### Issue 1: RBAC Permission Error ✅ RESOLVED

**Symptom**: The inference scheduler pod (`gaie-pattern1-epp`) fails with CrashLoopBackOff:
```
User "your-email@redhat.com" cannot create resource "clusterroles" in API group "rbac.authorization.k8s.io"
```

**Root Cause**: GCP account has `roles/editor` which doesn't include Kubernetes RBAC admin permissions. The gaie Helm chart creates ClusterRoles and ClusterRoleBindings which require `roles/container.admin`.

**Resolution**: The Quick Start Guide (Step 1) includes obtaining `roles/container.admin` before deployment. Request this role from your GCP project admin:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:your-email@example.com" \
  --role="roles/container.admin"
```

### Issue 2: GPU Out of Memory During Initialization ✅ RESOLVED

**Symptom**: vLLM pod crashes during startup with:
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 500.00 MiB.
GPU 0 has a total capacity of 14.58 GiB of which 471.56 MiB is free.
```

**Root Cause**: T4 GPU (14.58 GiB total) runs out of memory during CUDA graph capture when using default settings:
- Default: `max-model-len=4096`, `gpu-memory-utilization=0.90`
- Memory breakdown: ~12.7 GiB for model/KV cache + ~2 GiB for CUDA graphs/sampler = OOM

**Resolution**: The `pattern1-overrides.yaml` (automatically used by Quick Start) configures:
```yaml
decode:
  containers:
  - args:
      - "--max-model-len"
      - "2048"  # Reduced from 4096
      - "--gpu-memory-utilization"
      - "0.85"  # Reduced from 0.90
```

**Result**: Successfully fits google/gemma-2b-it on T4 GPU with headroom for CUDA graphs.

**Trade-off**: Max sequence length reduced from 4096→2048 tokens. For longer contexts, consider:
- Using larger GPU (L4, A100)
- Enabling quantization (`--quantization bitsandbytes`)
- Using smaller model (Qwen2-0.5B)

### Issue 3: Gateway Not Getting External IP ✅ RESOLVED

**Symptom**: Gateway stuck without external IP address.

**Root Cause**: Missing proxy-only subnet required for GKE regional external Application Load Balancer.

**Resolution**: The Quick Start Guide (Step 4) creates the proxy-only subnet before deployment:
```bash
gcloud compute networks subnets create proxy-only-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=$REGION \
  --network=default \
  --range=192.168.0.0/23
```

### Issue 4: "fault filter abort" Error ✅ RESOLVED

**Symptom**: Requests to Gateway fail with "fault filter abort" error.

**Root Cause**: Network Services API not enabled (required for ext-proc traffic extensions).

**Resolution**: The Quick Start Guide (Step 3) enables this API before deployment:
```bash
gcloud services enable networkservices.googleapis.com --project=$PROJECT_ID
```

## Prerequisites

### Hardware Requirements
- **GKE Cluster**: nvidia-test-cluster (us-central1-a)
- **GPU**: 1x NVIDIA T4 (for single replica)
- **CPU Nodes**: 2x e2-standard-4 (for scheduler and control plane)

### Software Requirements
- **kubectl**: v1.28.0+ (GKE client)
- **helm**: v3.12.0+ (Kubernetes package manager)
- **helmfile**: v1.1.0+ (Helm orchestration)
- **yq**: v4+ (YAML processor)
- **git**: v2.30.0+ (version control)

**Optional but recommended**:
- **stern**: v1.30+ (pod log streaming)
- **helm diff plugin**: v3.10.0+ (preview changes)

### Accounts and Tokens
- **HuggingFace Token**: For model downloads (google/gemma-2b-it)
- **GCP Project**: ecoeng-llmd with GKE access

### Existing Infrastructure
- GKE cluster: nvidia-test-cluster (already created)
- Red Hat registry pull secret (already configured)
- Benchmark suite (already configured)

## Step 1: Verify kubectl Context

**IMPORTANT**: Ensure you're connected to the GPU cluster, not the TPU cluster.

```bash
# Check current context
kubectl config current-context

# Should show: gke_ecoeng-llmd_us-central1-a_nvidia-test-cluster
# If it shows the TPU cluster (europe-west4-a_tpu-test-cluster), switch:

kubectl config use-context gke_ecoeng-llmd_us-central1-a_nvidia-test-cluster

# Verify cluster access
kubectl get nodes
```

**Expected output**: Nodes from nvidia-test-cluster in us-central1-a

## Step 2: Check Existing Tools

Verify you have the required tools installed:

```bash
# Check current versions
kubectl version --client
helm version
git --version

# Check for tools that may need installation
which yq
which helmfile
which stern
```

**Expected**:
- kubectl: Already installed (using GKE)
- helm: May need installation or upgrade
- git: Already installed
- yq: Likely needs installation
- helmfile: Likely needs installation

## Step 3: Scale Up GPU Cluster (if needed)

Check if the cluster is already running. If it's scaled to 0 nodes, scale it back up:

```bash
# First, check current node status
kubectl get nodes

# If no nodes (scaled to 0), scale up:

# Scale up GPU node pool (1 T4 GPU)
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool \
  --num-nodes 1 \
  --zone us-central1-a \
  --project ecoeng-llmd \
  --quiet

# Scale up default node pool (CPU nodes)
gcloud container clusters resize nvidia-test-cluster \
  --node-pool default-pool \
  --num-nodes 2 \
  --zone us-central1-a \
  --project ecoeng-llmd \
  --quiet

# Wait for nodes to be ready (2-3 minutes)
kubectl get nodes -w
```

**Expected output** (once running):
```
NAME                                                  STATUS   ROLES    AGE     VERSION
gke-nvidia-test-cluste-nvidia-t4-pool-...             Ready    <none>   4m      v1.33.5-gke.2019000
gke-nvidia-test-cluster-default-pool-...              Ready    <none>   3m      v1.33.5-gke.2019000
gke-nvidia-test-cluster-default-pool-...              Ready    <none>   3m      v1.33.5-gke.2019000
```

**Note**: If nodes are already running, you can skip the resize commands. Press Ctrl+C if watching nodes.

## Step 4: Clone llm-d Repository

Clone the llm-d repository to your local working directory:

```bash
cd /home/jhull/devel/rhaiis-test
git clone https://github.com/llm-d/llm-d.git
cd llm-d

# Check out latest stable release (or main for latest)
git checkout main

# Verify repository structure
ls -la guides/
```

**Expected directories**:
- `guides/inference-scheduling/` - Pattern 1 deployment
- `guides/prereq/` - Prerequisites setup
- `docker/` - Container definitions
- `docs/` - Architecture documentation

## Step 5: Install Required Client Tools

Use the llm-d installation script to install missing tools:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/prereq/client-setup

# Review the installation script
cat install-deps.sh

# Run installation (installs helm, helmfile, yq, stern)
./install-deps.sh

# Verify installations
helm version      # Should be v3.12.0+
helmfile version  # Should be v1.1.0+
yq --version      # Should be v4+
stern --version   # Should be v1.30+ (optional)
```

**Note**: The script detects your OS and installs appropriate binaries. It's safe to run multiple times.

## Step 6: Enable GKE Gateway API

GKE provides Gateway API natively, but it needs to be enabled:

```bash
# Enable Gateway API on the cluster
gcloud container clusters update nvidia-test-cluster \
  --gateway-api=standard \
  --zone=us-central1-a \
  --project=ecoeng-llmd

# Verify Gateway API is available (takes 1-2 minutes)
kubectl api-resources | grep gateway.networking.k8s.io
```

**Expected output**:
```
gatewayclasses    gc           gateway.networking.k8s.io/v1
gateways          gtw          gateway.networking.k8s.io/v1
httproutes                     gateway.networking.k8s.io/v1
```

**Check GatewayClasses**:
```bash
kubectl get gatewayclass
```

**Expected**:
- `gke-l7-global-external-managed` - Global external load balancer
- `gke-l7-regional-external-managed` - Regional external (we'll use this)
- `gke-l7-rilb` - Regional internal load balancer

## Step 7: Install Gateway Provider CRDs

Install llm-d's Gateway API Inference Extension CRDs:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/prereq/gateway-provider

# Install CRDs
./install-gateway-provider-dependencies.sh

# Verify CRDs installed
kubectl api-resources --api-group=inference.networking.k8s.io
```

**Expected output**:
```
NAME                 SHORTNAMES   APIVERSION                              NAMESPACED   KIND
inferencepools       ip           inference.networking.k8s.io/v1          true         InferencePool
inferenceobjectives  io           inference.networking.k8s.io/v1alpha2    true         InferenceObjective
```

These CRDs enable intelligent routing features:
- **InferencePool**: Manages pools of inference endpoints
- **InferenceObjective**: Defines routing objectives (load-aware, prefix-cache-aware)

## Step 8: Create Namespace and Secrets

Create the llm-d namespace and apply the HuggingFace token secret:

```bash
# Set environment variable
export NAMESPACE="llm-d"

# Create namespace
kubectl create namespace ${NAMESPACE}

# Apply existing HuggingFace token secret
kubectl apply -f /home/jhull/devel/rhaiis-test/huggingface-token-secret.yaml -n ${NAMESPACE}

# Verify secret created
kubectl get secret huggingface-token -n ${NAMESPACE}
```

**Note**:
- The secret file (`huggingface-token-secret.yaml`) already exists with a valid HuggingFace token
- Secret name is `huggingface-token` (matches the name in the YAML file)
- google/gemma-2b-it is a public model, so the existing token is sufficient

**If you need to update the token**:
```bash
# Edit the YAML file
nano /home/jhull/devel/rhaiis-test/huggingface-token-secret.yaml

# Re-apply
kubectl apply -f /home/jhull/devel/rhaiis-test/huggingface-token-secret.yaml -n ${NAMESPACE}
```

## Step 9: Review Configuration and Create Custom Values File

Navigate to the inference scheduling guide and review configuration:

```bash
cd /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling
ls -la
```

**Key files**:
- `helmfile.yaml.gotmpl`: Orchestrates 3 Helm releases
- `httproute.gke.yaml`: GKE-specific traffic routing
- `ms-inference-scheduling/values.yaml`: Model service defaults
- `gaie-inference-scheduling/values.yaml`: Inference scheduler config

**Review default model configuration**:
```bash
# Check default model and settings
cat ms-inference-scheduling/values.yaml | head -20
```

**Default settings that need customization**:
- **Model**: `Qwen/Qwen3-0.6B` → Need: `google/gemma-2b-it`
- **Replicas**: 2 → Need: 1 (Pattern 1 single replica)
- **Secret name**: `llm-d-hf-token` → Need: `huggingface-token` (our existing secret)

**Custom values file created**:

Location: `/home/jhull/devel/rhaiis-test/llm-d-pattern1-values.yaml`

**Key overrides**:
```yaml
modelArtifacts:
  uri: "hf://google/gemma-2b-it"
  name: "google/gemma-2b-it"
  size: 10Gi
  authSecretName: "huggingface-token"

decode:
  replicas: 1
  containers:
  - name: "vllm"
    args:
      - "--max-model-len"
      - "4096"
      - "--gpu-memory-utilization"
      - "0.90"
```

**View the full custom values file**:
```bash
cat /home/jhull/devel/rhaiis-test/llm-d-pattern1-values.yaml
```

## Step 10: Deploy Pattern 1 with Helmfile

> **Note**: The simplified deployment process is documented in the [Quick Start Guide](#quick-start-guide-30-minutes) above. This section provides additional context.

Deploy the three Helm releases using helmfile:

```bash
cd ~/llm-d/guides/inference-scheduling

# Set environment variables
export NAMESPACE="llm-d"
export RELEASE_NAME_POSTFIX="pattern1"

# Deploy all components
# helmfile automatically uses pattern1-overrides.yaml for GKE environment
helmfile -e gke -n $NAMESPACE apply
```

**What pattern1-overrides.yaml configures**:
- Model: `google/gemma-2b-it` (instead of default Qwen3-0.6B)
- Replicas: 1 (instead of default 2)
- Context length: 2048 tokens (optimized for T4 GPU)
- GPU utilization: 0.85 (prevents OOM during CUDA graph capture)
- Secret name: `huggingface-token` (matches our secret)

**What this deploys**:
1. **infra-pattern1**: Gateway infrastructure configuration
2. **gaie-pattern1**: Inference scheduler/router
3. **ms-pattern1**: vLLM model service (1 replica)

**Deployment takes 5-10 minutes**:
- Infrastructure components: ~30 seconds
- Inference scheduler: ~1 minute
- vLLM model service: ~5-8 minutes (model download ~2-3 min + GPU loading ~2-3 min)

**Monitor deployment**:
```bash
# Watch all pods
kubectl get pods -n $NAMESPACE -w

# Check vLLM pod logs (model download progress)
kubectl logs -n $NAMESPACE -l llm-d.ai/inferenceServing=true -f
```

**Expected pods** (all 1/1 Running):
- `gaie-pattern1-epp-*`: Inference scheduler
- `ms-pattern1-*-decode-*`: vLLM model service

## Step 11: Configure Gateway and HTTPRoute

> **Note**: The complete Gateway setup is documented in the [Quick Start Guide](#quick-start-guide-30-minutes) above. This section provides additional context.

The HTTPRoute connects the Gateway to the intelligent scheduler via InferencePool.

**Create HTTPRoute**:
```bash
cat > /tmp/httproute-pattern1.yaml <<'EOF'
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: llm-d-pattern1-inference-scheduling
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: infra-pattern1-inference-gateway
  rules:
    - backendRefs:
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: gaie-pattern1
        port: 54321  # InferencePool service port (not vLLM target port 8000)
        weight: 1
      matches:
      - path:
          type: PathPrefix
          value: /
EOF

kubectl apply -f /tmp/httproute-pattern1.yaml -n $NAMESPACE

# Verify HTTPRoute created
kubectl get httproute -n $NAMESPACE
```

**What this does**:
- Creates HTTPRoute named `llm-d-pattern1-inference-scheduling`
- Attaches to Gateway: `infra-pattern1-inference-gateway`
- Routes traffic to InferencePool: `gaie-pattern1` on port 54321
- InferencePool routes to vLLM backends (labeled with `llm-d.ai/inferenceServing: "true"`)

**Key detail**: Must specify `port: 54321` (InferencePool service port), not 8000 (vLLM target port)

## Step 12: Get Gateway External IP

The Gateway provisions a GKE external load balancer. Get the external IP:

```bash
# Wait for Gateway to be ready (if just deployed)
kubectl get gateway infra-pattern1-inference-gateway -n $NAMESPACE -o wide
# Expected: ADDRESS populated, PROGRAMMED True

# Get Gateway IP
export GATEWAY_IP=$(kubectl get gateway infra-pattern1-inference-gateway \
  -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')

echo "Gateway IP: $GATEWAY_IP"
```

**If Gateway shows no ADDRESS**: Wait 2-3 minutes and check again. See [Quick Start troubleshooting](#troubleshooting) if issues persist.

## Step 13: Test Inference Endpoint

Test the deployment through the Gateway:

```bash
# Test health endpoint
curl http://$GATEWAY_IP/health
# Expected: No output (200 OK)

# List models
curl http://$GATEWAY_IP/v1/models
# Expected: JSON with "google/gemma-2b-it"

# Test inference
curl -X POST http://$GATEWAY_IP/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "What is Kubernetes?",
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

**Expected inference response**:
```json
{
  "id": "cmpl-...",
  "object": "text_completion",
  "model": "google/gemma-2b-it",
  "choices": [{
    "text": "Kubernetes is an open-source container orchestration platform...",
    "index": 0,
    "finish_reason": "length"
  }],
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 100,
    "total_tokens": 105
  }
}
```

**✅ Success!** If you get valid responses, Pattern 1 is fully operational with intelligent routing.

## Step 14: Run Benchmarks

Use your existing benchmark suite to test llm-d:

```bash
# Quick validation test
cd /home/jhull/devel/rhaiis-test
./benchmarks/scripts/quick_test.sh http://${EXTERNAL_IP}

# Full async benchmark
python benchmarks/python/benchmark_async.py \
  --base-url http://${EXTERNAL_IP} \
  --model google/gemma-2b-it \
  --num-requests 100 \
  --concurrency 10 \
  --max-tokens 100 \
  --output benchmarks/results/llm-d-pattern1-$(date +%Y%m%d).json \
  --html
```

**Expected performance** (similar to RHAIIS):
- TTFT (p50): 0.3-0.8s
- TPOT (p50): 20-50ms
- Throughput: 500-1500 tokens/sec
- Success rate: >99%

## Step 15: Verify Intelligent Scheduling

Check that the inference scheduler is actively routing requests:

```bash
# View inference scheduler logs
kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/name=gateway-api-inference-extension --tail=100

# Check InferencePool status
kubectl get inferencepool -n ${NAMESPACE} -o yaml

# View routing metrics (if exposed)
kubectl get svc -n ${NAMESPACE}
# Look for metrics service, then port-forward:
kubectl port-forward -n ${NAMESPACE} svc/<metrics-service> 9090:9090
curl http://localhost:9090/metrics | grep inference
```

**Look for**:
- Request routing decisions in scheduler logs
- Load balancing metrics
- Backend health checks
- Prefix cache hits (if available)

## Comparison: llm-d vs RHAIIS

**Architecture differences**:

| Aspect | RHAIIS (Standalone) | llm-d Pattern 1 |
|--------|---------------------|-----------------|
| Load Balancer | Direct LoadBalancer service | Gateway API (GKE L7) |
| Routing | Direct to pod | Via Inference Scheduler |
| Intelligence | None | Load-aware, prefix-cache-aware |
| Metrics | vLLM only | vLLM + scheduler + gateway |
| Scalability | Manual replicas | Intelligent pool management |
| Multi-model | Requires multiple services | Built-in routing |
| Cost | Same GPU cost | +minimal scheduler overhead |

**When to use each**:
- **RHAIIS**: Simple single-model deployments, minimal overhead
- **llm-d Pattern 1**: Foundation for advanced patterns, intelligent routing
- **llm-d Pattern 2+**: Multi-model, scale-out, MoE, P/D disaggregation

## Cost Analysis

**Pattern 1 running cost**:
- 1x T4 GPU node: ~$0.35/hour + VM ~$0.19/hour = ~$0.54/hour
- 2x e2-standard-4 (CPU): ~$0.27/hour
- **Total**: ~$0.81/hour (~$583/month)

**Cost savings when idle**:
```bash
# Scale to zero (preserves configuration)
kubectl scale deployment -n llm-d --all --replicas=0
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd
gcloud container clusters resize nvidia-test-cluster \
  --node-pool default-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd
```

**Savings**: ~$0.71/hour or ~$17/day (only control plane remains at ~$0.10/hour)

## Troubleshooting

### Pod Pending - No GPU Available

**Symptom**: vLLM pod stuck in Pending state

**Check**:
```bash
kubectl describe pod <vllm-pod> -n llm-d | grep -A5 Events
kubectl get nodes -o wide
```

**Common causes**:
- GPU node pool scaled to 0
- Another pod using the GPU (check RHAIIS: `kubectl get pods -n default`)
- Resource requests exceed capacity

**Fix**:
```bash
# Ensure GPU nodes available
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 1 \
  --zone us-central1-a --project ecoeng-llmd

# Scale down RHAIIS if needed
kubectl scale deployment rhaiis-t4-test --replicas=0 -n default
```

### Model Download Fails (403/404)

**Symptom**: vLLM pod CrashLoopBackOff, logs show HuggingFace errors

**Check**:
```bash
kubectl logs <vllm-pod> -n llm-d
```

**Common causes**:
- HuggingFace token secret not created
- Token doesn't have model access
- Network issues

**Fix**:
```bash
# Verify secret exists
kubectl get secret huggingface-token -n llm-d
kubectl describe secret huggingface-token -n llm-d

# Recreate if needed
kubectl delete secret huggingface-token -n llm-d
kubectl apply -f /home/jhull/devel/rhaiis-test/huggingface-token-secret.yaml -n llm-d

# Restart deployment
kubectl rollout restart deployment <vllm-deployment> -n llm-d
```

### Gateway No External IP

**Symptom**: Gateway stuck without external IP

**Check**:
```bash
kubectl get gateway -n llm-d
kubectl describe gateway <name> -n llm-d
kubectl get gatewayclass
```

**Common causes**:
- Gateway API not enabled
- Wrong GatewayClass
- External IP quota exceeded

**Fix**:
```bash
# Check Gateway API enabled
gcloud container clusters describe nvidia-test-cluster \
  --zone us-central1-a --project ecoeng-llmd \
  --format="value(addonsConfig.httpLoadBalancing)"

# Enable if needed
gcloud container clusters update nvidia-test-cluster \
  --gateway-api=standard \
  --zone=us-central1-a --project=ecoeng-llmd

# Check quota
gcloud compute project-info describe --project=ecoeng-llmd \
  | grep -A2 IN_USE_ADDRESSES
```

### HTTPRoute Not Routing (404/502)

**Symptom**: Gateway has IP but requests fail

**Check**:
```bash
kubectl get httproute -n llm-d -o yaml
kubectl describe httproute <name> -n llm-d
kubectl get inferencepool -n llm-d
kubectl get endpoints -n llm-d
```

**Common causes**:
- HTTPRoute not attached to Gateway
- Backend service not ready
- InferencePool has no backends

**Fix**:
```bash
# Verify HTTPRoute parentRefs
kubectl get httproute <name> -n llm-d -o jsonpath='{.spec.parentRefs}'

# Check backend readiness
kubectl get pods -n llm-d
kubectl logs <vllm-pod> -n llm-d

# Verify service endpoints
kubectl get endpoints -n llm-d
# Should show vLLM pod IP
```

### Helmfile Apply Fails

**Symptom**: Deployment errors during `helmfile apply`

**Common errors and fixes**:

1. **CRDs not installed**:
   ```bash
   cd /home/jhull/devel/rhaiis-test/llm-d/guides/prereq/gateway-provider
   ./install-gateway-provider-dependencies.sh
   ```

2. **Namespace doesn't exist**:
   ```bash
   kubectl create namespace llm-d
   ```

3. **Missing environment variable**:
   ```bash
   export NAMESPACE="llm-d"
   export RELEASE_NAME_POSTFIX="pattern1"
   ```

4. **Helm version too old**:
   ```bash
   helm version  # Must be v3.12.0+
   # Upgrade if needed via install-deps.sh
   ```

## Next Steps: Patterns 2-5

### Pattern 2: Multi-Model Deployment

Deploy a second model alongside google/gemma-2b-it:

```bash
# Deploy second model (e.g., Llama-3.1-8B-Instruct)
export RELEASE_NAME_POSTFIX="pattern2-llama"
helmfile -e gke -n ${NAMESPACE} apply \
  --set modelService.model=meta-llama/Llama-3.1-8B-Instruct

# Route based on model in request
curl -X POST http://${EXTERNAL_IP}/v1/completions \
  -d '{"model": "meta-llama/Llama-3.1-8B-Instruct", "prompt": "..."}'
```

### Pattern 3: Scale-Out with Caching

Increase replicas for higher throughput:

```bash
# Scale to 3 replicas
kubectl scale deployment <vllm-deployment> -n llm-d --replicas=3

# Intelligent routing distributes load
# Prefix-cache-aware routing shares KV cache across requests
```

**Expected improvements**:
- 3x throughput for different prompts
- Cache hits reduce latency for similar prompts
- Load balancing maintains availability

### Pattern 4: MoE with LeaderWorkerSet

Deploy Mixture of Experts models (requires multi-node coordination):

1. Install LeaderWorkerSet operator
2. Configure data parallelism + expert parallelism
3. Deploy DeepSeek-V3 or Mixtral-8x7B
4. Enable IB/RoCE for fast inter-node communication

### Pattern 5: P/D Disaggregation

Split prefill and decode phases:

1. Deploy separate prefill pool (high throughput)
2. Deploy separate decode pool (low latency)
3. Configure scheduler to route accordingly
4. Enable KV cache transfer

**Benefits**: 40% TTFT reduction, better resource utilization

## Monitoring and Observability

### Prometheus Metrics

llm-d exposes Prometheus metrics for both vLLM and the scheduler:

```bash
# Port-forward to metrics endpoint
kubectl port-forward -n llm-d svc/<vllm-service> 8000:8000
curl http://localhost:8000/metrics

# Key metrics:
# - vllm:e2e_request_latency_seconds_bucket
# - vllm:num_requests_running
# - vllm:kv_cache_usage_perc
# - inference_pool_backend_health
# - inference_pool_request_count
```

### Grafana Dashboard

Use vLLM's official Grafana dashboard:
- Dashboard ID: 23991
- URL: https://grafana.com/grafana/dashboards/23991-vllm/

Import into your Grafana instance and point to your Prometheus data source.

## Deployment Status (2026-01-20)

### ✅ Successfully Deployed

**Deployment Configuration**:
- **Model**: google/gemma-2b-it (2B parameters, instruction-tuned)
- **Context Length**: 2048 tokens (reduced from 4096 due to T4 GPU constraints)
- **GPU Utilization**: 0.85 (reduced from 0.90 to prevent OOM)
- **Replicas**: 1 (Pattern 1: single replica)
- **GPU**: 1x NVIDIA T4 (14.58 GiB)
- **Cluster**: nvidia-test-cluster (us-central1-a)

**Deployed Components**:
- ✅ **ms-pattern1** (Model Service): vLLM pod running google/gemma-2b-it
- ✅ **vllm-loadbalancer**: LoadBalancer service exposing port 8000
- ⚠️ **gaie-pattern1** (Inference Scheduler): Skipped due to RBAC permissions
- ⚠️ **infra-pattern1** (Gateway Infrastructure): Deployed but not used without gaie

**Inference Endpoint**:
```
External IP: 136.112.200.85
Port: 8000
Health: http://136.112.200.85:8000/health
Models: http://136.112.200.85:8000/v1/models
```

**Test Results**:
```bash
# Model listing - PASSED
curl http://136.112.200.85:8000/v1/models
# Returns: {"data":[{"id":"google/gemma-2b-it","max_model_len":2048,...}]}

# Inference test - PASSED
curl -X POST http://136.112.200.85:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "What is Kubernetes?",
    "max_tokens": 100
  }'
# Returns: Coherent 100-token response about Kubernetes (2.5s latency)
```

### Known Limitations

1. **No Intelligent Routing**: Deployed without gaie scheduler due to RBAC constraints
   - Missing: Load-aware routing
   - Missing: Prefix-cache-aware routing
   - Workaround: Direct LoadBalancer access to vLLM pod

2. **Reduced Context Length**: 2048 tokens instead of 4096
   - Reason: T4 GPU memory constraints during CUDA graph capture
   - Impact: Shorter prompts/responses
   - Mitigation: Use larger GPU (L4, A100) or enable quantization

3. **Single Replica Only**: Pattern 1 deployment
   - No horizontal scaling yet (Patterns 2-3 address this)
   - No multi-model support yet (Pattern 2 addresses this)

### Cost Analysis

**Current deployment** (as of 2026-01-20):
- 1x GPU node (n1-standard-4 + T4): ~$0.54/hour
- 2x CPU nodes (e2-standard-4): ~$0.27/hour
- **Total**: ~$0.81/hour (~$583/month if running 24/7)

**Cost optimization**:
- Scale GPU node pool to 0 when idle: Saves ~$0.54/hour
- Scale default node pool to 1: Saves ~$0.13/hour
- **Idle cost**: ~$0.14/hour (~$100/month, just control plane)

### RBAC Fix and Scheduler Deployment (2026-01-21)

### Overview

The RBAC permission issue preventing the inference scheduler deployment has been resolved. The gaie-pattern1-epp scheduler is now running successfully with full intelligent routing capabilities.

### ✅ Steps Completed

#### 1. Obtained Required GCP IAM Permissions

Requested and received the following GCP IAM roles from project admin:
- `roles/container.admin` - Full Kubernetes cluster management including RBAC
- `roles/owner` - Full project access

**Verification**:
```bash
# Check current IAM roles
gcloud projects get-iam-policy ecoeng-llmd \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:jhull@redhat.com" \
  --format="table(bindings.role)"
```

**Result**:
```
ROLE
roles/editor
roles/container.admin
roles/owner
```

#### 2. Verified RBAC Permissions

Tested ability to create RBAC resources before proceeding with deployment:

```bash
# Test ClusterRole creation
kubectl create clusterrole test-rbac-cluster --verb=get --resource=pods --dry-run=client -o yaml | kubectl apply -f -
kubectl delete clusterrole test-rbac-cluster

# Test ClusterRoleBinding creation
kubectl create clusterrolebinding test-rbac-binding --clusterrole=view --serviceaccount=default:default --dry-run=client -o yaml | kubectl apply -f -
kubectl delete clusterrolebinding test-rbac-binding

# Test Role creation
kubectl create role test-rbac-role --verb=get --resource=pods -n llm-d --dry-run=client -o yaml | kubectl apply -f -
kubectl delete role test-rbac-role -n llm-d

# Test RoleBinding creation
kubectl create rolebinding test-rbac-rolebinding --role=test-rbac-role --serviceaccount=llm-d:default -n llm-d --dry-run=client -o yaml | kubectl apply -f -
kubectl delete rolebinding test-rbac-rolebinding -n llm-d
```

**Result**: All RBAC resource creation tests passed successfully.

#### 3. Deleted Failed gaie-pattern1 Release

The previous deployment attempt had left the scheduler in CrashLoopBackOff with 431 restarts. Cleaned up before redeployment:

```bash
# Delete the failed release
helm delete gaie-pattern1 -n llm-d

# Verify cleanup
helm list -n llm-d
kubectl get pods -n llm-d
```

**Result**: gaie-pattern1 release deleted, namespace cleaned.

#### 4. Redeployed gaie-pattern1 Scheduler

Deployed the inference scheduler using Helm directly (helmfile had command execution issues):

```bash
# Deploy gaie-pattern1 with Helm
helm upgrade --install gaie-pattern1 \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/inferencepool \
  --version v1.2.0 \
  --namespace llm-d \
  --values /home/jhull/devel/rhaiis-test/llm-d/guides/inference-scheduling/gaie-inference-scheduling/values.yaml \
  --set provider.name=gke \
  --set inferenceExtension.monitoring.gke.enabled=true \
  --set inferenceExtension.monitoring.prometheus.enabled=false

# Monitor deployment
kubectl get pods -n llm-d -w
```

**Result**: Deployment successful.

#### 5. Verified Scheduler Pod Running

Checked scheduler pod status and confirmed successful startup:

```bash
# Check pod status
kubectl get pods -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp

# Expected output:
# NAME                                 READY   STATUS    RESTARTS   AGE
# gaie-pattern1-epp-7b8c9d5f6-xyz      1/1     Running   0          2m
```

**Result**:
- Pod status: 1/1 Running
- Restarts: 0 (down from 431 in failed deployment)
- No CrashLoopBackOff errors

#### 6. Verified RBAC Resources Created

Confirmed all required RBAC resources were created successfully:

```bash
# List ClusterRoles
kubectl get clusterrole | grep gaie-pattern1

# List ClusterRoleBindings
kubectl get clusterrolebinding | grep gaie-pattern1

# List Roles in llm-d namespace
kubectl get role -n llm-d

# List RoleBindings in llm-d namespace
kubectl get rolebinding -n llm-d

# List ServiceAccounts
kubectl get serviceaccount -n llm-d
```

**Resources Created**:
- ClusterRole: `llm-d-gaie-pattern1-metrics-reader`
- ClusterRoleBinding: `llm-d-gaie-pattern1-metrics-reader-role-binding`
- Role: `gaie-pattern1-epp` (namespace: llm-d)
- RoleBinding: `gaie-pattern1-epp` (namespace: llm-d)
- ServiceAccount: `gaie-pattern1-epp`

**Permissions Granted**:
```bash
# Check ServiceAccount permissions
kubectl describe clusterrole llm-d-gaie-pattern1-metrics-reader
kubectl describe role gaie-pattern1-epp -n llm-d
```

**Result**: All RBAC resources created with correct permissions for InferencePool management.

#### 7. Verified InferencePool Created

Checked that the InferencePool custom resource was created and detecting vLLM backend:

```bash
# List InferencePools
kubectl get inferencepool -n llm-d

# Describe InferencePool
kubectl describe inferencepool gaie-pattern1 -n llm-d

# Check InferencePool backend service
kubectl get svc -n llm-d | grep gaie-pattern1
```

**Result**:
- InferencePool: `gaie-pattern1` created
- Backend service: `gaie-pattern1-ips-b68768ac` created
- Backend detection: Successfully detecting vLLM pod (labeled with `llm-d.ai/inferenceServing: "true"`)

#### 8. Confirmed Intelligent Routing Plugins Loaded

Verified that the scheduler loaded intelligent routing algorithms:

```bash
# Check scheduler logs for plugin initialization
kubectl logs -n llm-d -l app.kubernetes.io/name=gaie-pattern1-epp --tail=100 | grep -i "plugin\|scorer"
```

**Routing Plugins Loaded**:
- **prefix-cache-scorer** (weight: 3) - Routes similar prompts to same backend for KV cache efficiency
- **kv-cache-utilization-scorer** (weight: 2) - Balances based on cache usage
- **queue-scorer** (weight: 2) - Routes based on request queue depth

**Result**: All intelligent routing capabilities initialized successfully.

#### 9. Verified vLLM Endpoint Still Working

Confirmed the vLLM model service remained operational during scheduler deployment:

```bash
# Test model listing
curl http://136.112.200.85:8000/v1/models

# Test inference
curl -X POST http://136.112.200.85:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "What is Kubernetes?",
    "max_tokens": 50
  }'
```

**Result**: Both model listing and inference endpoints working correctly.

#### 10. Discovered Gateway Networking Issue

Investigated the GKE Gateway status and found networking issue:

```bash
# Check Gateway status
kubectl get gateway -n llm-d -o wide

# Describe Gateway for errors
kubectl describe gateway infra-pattern1-inference-gateway -n llm-d
```

**Finding**:
- Gateway status: `Programmed=False`
- Error: "An active proxy-only subnetwork is required in the same region and VPC as the forwarding rule"
- Root cause: GKE regional external Application Load Balancer requires a proxy-only subnet in us-central1

**Impact**:
- Direct LoadBalancer endpoint (136.112.200.85:8000) works fine
- Gateway endpoint not available - prevents intelligent routing through scheduler
- HTTPRoute cannot be applied until Gateway is programmed

### Current Architecture

With the scheduler now running, the architecture is:

```
Internet → LoadBalancer (136.112.200.85:8000) → vLLM Pod
                                                     ↑
                                                     | (monitored)
                                              llm-d Scheduler (gaie-pattern1-epp)
                                                     ↑
                                                     | (detects via InferencePool)
                                                 Backend Pod
```

**Status** (Updated 2026-01-21 after Gateway fix):
- ✅ vLLM pod: Running (google/gemma-2b-it)
- ✅ Scheduler pod: Running (gaie-pattern1-epp)
- ✅ InferencePool: Created and detecting backend
- ✅ Intelligent routing plugins: Loaded
- ✅ Gateway: Programmed=True, External IP 35.209.201.202
- ✅ HTTPRoute: Bound to Gateway, routing to InferencePool gaie-pattern1:54321
- ✅ Backend health: HEALTHY (vLLM + ext-proc)

**Complete intelligent routing now active!**

---

## Gateway Fix Completed (2026-01-21)

### Overview

The GKE Gateway networking issue has been resolved. The Gateway is now fully operational with intelligent routing enabled, allowing traffic to flow through the llm-d scheduler for load-aware and prefix-cache-aware request distribution.

### Issues Fixed

Three critical issues were preventing the Gateway from working:

1. **Missing proxy-only subnet** - GKE regional external Application Load Balancer requires a dedicated subnet
2. **Network Services API not enabled** - Required for ext-proc traffic extensions (intelligent scheduler integration)
3. **HTTPRoute missing port specification** - InferencePool backend requires explicit port 54321

### Resolution Summary

**Initial State**:
- Cluster: nvidia-test-cluster (us-central1-a)
- VPC: default (auto-mode, reserves 10.128.0.0/9)
- Proxy-only subnet: None
- Network Services API: Disabled
- Gateway status: Programmed=False, error about missing proxy-only subnet

**Final State**:
- Proxy-only subnet: proxy-only-subnet (192.168.0.0/23)
- Network Services API: Enabled
- Gateway status: Programmed=True, External IP: **35.209.201.202**
- HTTPRoute: Bound to Gateway, routing to InferencePool gaie-pattern1:54321
- Backend health: HEALTHY (vLLM:8000 + ext-proc:9002)

### ✅ Steps Completed

#### Step 1: Verified Network Configuration

Checked existing subnets in the default VPC:

```bash
# Listed all subnets
gcloud compute networks subnets list --network=default --project=ecoeng-llmd

# Confirmed no proxy-only subnet existed
gcloud compute networks subnets list --network=default --project=ecoeng-llmd \
  --filter="purpose:REGIONAL_MANAGED_PROXY"
```

**Result**: Found default subnet (10.128.0.0/20) in us-central1, no proxy-only subnets.

#### Step 2: Created Proxy-Only Subnet

Created proxy-only subnet for GKE Gateway load balancer:

```bash
gcloud compute networks subnets create proxy-only-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=us-central1 \
  --network=default \
  --range=192.168.0.0/23 \
  --project=ecoeng-llmd
```

**Key decisions**:
- Used `192.168.0.0/23` (512 IPs) instead of `10.129.0.0/23` because auto-mode VPC reserves `10.128.0.0/9`
- `/23` provides sufficient capacity for load balancer proxies

**Result**: Subnet created successfully with purpose=REGIONAL_MANAGED_PROXY, state=READY.

#### Step 3: Enabled Network Services API

Discovered Gateway error: "NetworkServices API is not enabled" - required for ext-proc integration:

```bash
gcloud services enable networkservices.googleapis.com --project=ecoeng-llmd
```

**Result**: API enabled successfully.

#### Step 4: Forced Gateway Reconciliation

Triggered Gateway to detect new subnet and API:

```bash
kubectl annotate gateway infra-pattern1-inference-gateway -n llm-d \
  force-reconcile="$(date +%s)" --overwrite
```

**Result**: Gateway reconciled after 90 seconds, Programmed=True.

#### Step 5: Verified Gateway Status

Confirmed Gateway provisioned successfully:

```bash
kubectl get gateway infra-pattern1-inference-gateway -n llm-d -o wide
```

**Result**:
- Gateway status: Programmed=True
- External IP: **35.209.201.202**
- Load balancer provisioned in us-central1

#### Step 6: Created HTTPRoute with Explicit Port

Created HTTPRoute to route traffic through InferencePool:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: llm-d-pattern1-inference-scheduling
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: infra-pattern1-inference-gateway
  rules:
    - backendRefs:
      - group: inference.networking.k8s.io
        kind: InferencePool
        name: gaie-pattern1
        port: 54321  # Critical: InferencePool service port
        weight: 1
      matches:
      - path:
          type: PathPrefix
          value: /
```

**Key fix**: Added explicit `port: 54321` - InferencePool backend service uses this port, not the vLLM target port (8000).

**Result**: HTTPRoute accepted and bound to Gateway.

#### Step 7: Verified Backend Health

Checked GKE backend service health:

```bash
# InferencePool backend
gcloud compute backend-services get-health \
  gkegw1-on7z-llm-d-gaie-pattern1-ips-b68768ac-54321-0izcufp50m0a \
  --region=us-central1 --project=ecoeng-llmd

# Ext-proc backend
gcloud compute backend-services get-health \
  gkegw1-on7z-llm-d-gaie-pattern1-epp-9002-g975d708ktks \
  --region=us-central1 --project=ecoeng-llmd
```

**Result**:
- InferencePool backend: HEALTHY (10.0.0.6:8000 - vLLM pod)
- Ext-proc backend: HEALTHY (10.0.1.8:9002 - scheduler pod)

#### Step 8: Tested Routing Through Gateway

Verified end-to-end routing:

```bash
export GATEWAY_IP=35.209.201.202

# Test health endpoint
curl http://${GATEWAY_IP}/health

# Test model listing
curl http://${GATEWAY_IP}/v1/models

# Test inference
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "google/gemma-2b-it", "prompt": "What is load-aware routing?", "max_tokens": 50}'
```

**Result**: All endpoints working, inference responses returned successfully.

#### Step 9: Verified Intelligent Routing Active

Confirmed scheduler loaded routing plugins:

```bash
kubectl logs -n llm-d gaie-pattern1-epp-6cdc8cfc4b-wmwbt --tail=100 | grep scheduler-config
```

**Result**: Scheduler initialized with:
- **prefix-cache-scorer** (weight: 3) - Routes similar prompts to same backend
- **kv-cache-utilization-scorer** (weight: 2) - Balances based on cache usage
- **queue-scorer** (weight: 2) - Routes based on request queue depth

#### Step 10: Confirmed Two Endpoints Available

**Gateway Endpoint** (Intelligent Routing - Recommended):
```bash
curl http://35.209.201.202/v1/models
# Returns: google/gemma-2b-it via intelligent scheduler
```

**Direct LoadBalancer** (Bypass Scheduler - Backup):
```bash
curl http://136.112.200.85:8000/v1/models
# Returns: google/gemma-2b-it directly from vLLM pod
```

**Both working**, Gateway enables intelligent routing for multi-replica scenarios.

### Final Architecture

With Gateway working, the complete architecture is:

```
Internet → GKE Gateway (35.209.201.202:80)
              ↓
         HTTPRoute (llm-d-pattern1-inference-scheduling)
              ↓
     GKE Load Balancer (ext-proc integration)
              ↓
     llm-d Scheduler (gaie-pattern1-epp:9002)
              ↓ (intelligent routing via ext-proc gRPC)
         InferencePool Backend (port 54321)
              ↓
         vLLM Pod (10.0.0.6:8000 - google/gemma-2b-it)
```

**Routing flow**:
1. Request arrives at Gateway (35.209.201.202)
2. HTTPRoute directs to InferencePool gaie-pattern1:54321
3. GKE load balancer invokes ext-proc service (scheduler:9002)
4. Scheduler scores backends using intelligent routing algorithms
5. Request forwarded to selected vLLM pod (10.0.0.6:8000)
6. Response returned via same path

### Success Criteria - All Met ✅

1. ✅ **Proxy-only subnet created**: proxy-only-subnet (192.168.0.0/23) in us-central1
2. ✅ **Network Services API enabled**: networkservices.googleapis.com active
3. ✅ **Gateway programmed**: Programmed=True, External IP 35.209.201.202
4. ✅ **HTTPRoute accepted**: llm-d-pattern1-inference-scheduling bound to Gateway
5. ✅ **Backend health**: Both vLLM (8000) and ext-proc (9002) backends HEALTHY
6. ✅ **Gateway accessible**: `/health`, `/v1/models`, `/v1/completions` all working
7. ✅ **Intelligent routing active**: Scheduler processing requests with weighted scoring

### Key Lessons Learned

**1. Auto-mode VPC IP Restrictions**
- Auto-mode VPCs reserve `10.128.0.0/9` for automatic subnet creation
- Cannot use `10.129.0.0/23` for proxy-only subnet - conflicts with reserved range
- Solution: Use private IP ranges outside reserved space (e.g., `192.168.0.0/23`)

**2. Network Services API Dependency**
- GKE Gateway ext-proc integration requires `networkservices.googleapis.com`
- Not enabled by default - causes "fault filter abort" errors
- Must be explicitly enabled before ext-proc traffic extensions work

**3. InferencePool Port Specification**
- InferencePool backend service uses port 54321, not vLLM target port 8000
- HTTPRoute must explicitly specify `port: 54321` in backendRefs
- Port mismatch causes routing failures even when backends are healthy

**4. Gateway Reconciliation Timing**
- Gateway controller doesn't immediately detect infrastructure changes
- Requires manual reconciliation trigger via annotation
- Takes 90-120 seconds to fully provision load balancer after changes

### Usage Instructions

#### Using the Gateway Endpoint (Recommended)

**Set environment variable**:
```bash
export GATEWAY_IP=35.209.201.202
```

**Health check**:
```bash
curl http://${GATEWAY_IP}/health
```

**List models**:
```bash
curl http://${GATEWAY_IP}/v1/models
```

**Text completion**:
```bash
curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "What is Kubernetes?",
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

**Chat completion**:
```bash
curl -X POST http://${GATEWAY_IP}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "messages": [{"role": "user", "content": "Explain load-aware routing"}],
    "max_tokens": 100
  }'
```

#### Using Direct LoadBalancer (Backup)

**For comparison or if Gateway has issues**:
```bash
export DIRECT_IP=136.112.200.85

curl http://${DIRECT_IP}:8000/v1/models
curl -X POST http://${DIRECT_IP}:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "google/gemma-2b-it", "prompt": "Hello", "max_tokens": 50}'
```

#### Monitoring Intelligent Routing

**View scheduler metrics**:
```bash
kubectl port-forward -n llm-d svc/gaie-pattern1-epp 9090:9090
curl http://localhost:9090/metrics | grep inference
```

**Watch scheduler logs**:
```bash
kubectl logs -n llm-d -l inferencepool=gaie-pattern1-epp -f
```

**Check backend health**:
```bash
gcloud compute backend-services get-health \
  gkegw1-on7z-llm-d-gaie-pattern1-ips-b68768ac-54321-0izcufp50m0a \
  --region=us-central1 --project=ecoeng-llmd
```

### Cost Impact

**Proxy-only subnet**: $0/month (network configuration only)

**GKE Gateway** (Regional External Application Load Balancer):
- Forwarding rules: ~$18/month
- Data processing: ~$0.008/GB
- Total: Similar to existing LoadBalancer service cost

**Recommendation**:
- Keep both endpoints initially for testing and comparison
- Delete LoadBalancer service once Gateway is validated (saves ~$18/month)
- Or keep LoadBalancer as emergency fallback

**Optional: Remove Direct LoadBalancer**:
```bash
# After validating Gateway works for your workload
kubectl delete svc vllm-loadbalancer -n llm-d
```

---

## Next Steps

### 1. Test with Benchmarks

Run benchmarks against both endpoints to compare performance:

**Test Gateway endpoint (with intelligent routing)**:
```bash
export GATEWAY_IP=35.209.201.202
cd /home/jhull/devel/rhaiis-test/benchmarks
./scripts/quick_test.sh http://$GATEWAY_IP

# Full async benchmark
python python/benchmark_async.py \
  --base-url http://$GATEWAY_IP \
  --model google/gemma-2b-it \
  --num-requests 100 \
  --concurrency 10 \
  --max-tokens 100 \
  --output results/llm-d-gateway-$(date +%Y%m%d).json \
  --html
```

**Test direct LoadBalancer endpoint (baseline)**:
```bash
export DIRECT_IP=136.112.200.85
./scripts/quick_test.sh http://$DIRECT_IP:8000

python python/benchmark_async.py \
  --base-url http://$DIRECT_IP:8000 \
  --model google/gemma-2b-it \
  --num-requests 100 \
  --concurrency 10 \
  --max-tokens 100 \
  --output results/llm-d-direct-$(date +%Y%m%d).json \
  --html
```

**Compare results**: For single replica, performance should be similar. Benefits appear with multi-replica scaling.

### 2. Scale to Pattern 2: Multi-Model Deployment

Deploy a second model alongside google/gemma-2b-it:

```bash
# Scale up GPU nodes if needed
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 2 \
  --zone us-central1-a --project ecoeng-llmd

# Deploy second model (e.g., microsoft/Phi-3-mini-4k-instruct)
# Create pattern2-values.yaml with different model
# Deploy with RELEASE_NAME_POSTFIX=pattern2

# Test model selection via request
curl -X POST http://35.209.201.202/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "microsoft/Phi-3-mini-4k-instruct", "prompt": "...", "max_tokens": 50}'
```

### 3. Scale to Pattern 3: N-replica Scale-Out

Increase replicas to test load-aware and prefix-cache-aware routing:

```bash
# Scale vLLM deployment to 3 replicas
kubectl scale deployment ms-pattern1-llm-d-modelservice-decode -n llm-d --replicas=3

# Ensure sufficient GPU nodes
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 3 \
  --zone us-central1-a --project ecoeng-llmd

# Wait for all replicas to be ready
kubectl get pods -n llm-d -l llm-d.ai/inferenceServing=true -w

# Verify InferencePool detects all backends
kubectl get inferencepool gaie-pattern1 -n llm-d -o yaml

# Test with concurrent requests to see load balancing
for i in {1..10}; do
  curl -X POST http://35.209.201.202/v1/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"google/gemma-2b-it\", \"prompt\": \"Request $i\", \"max_tokens\": 20}" &
done
wait

# Watch scheduler logs to see routing decisions
kubectl logs -n llm-d -l inferencepool=gaie-pattern1-epp --tail=50
```

**Expected**: Requests distributed across replicas based on load, queue depth, and KV cache state.

### 4. Monitor Metrics and Set Up Dashboards

**View Prometheus metrics**:
```bash
# Port-forward to scheduler metrics
kubectl port-forward -n llm-d svc/gaie-pattern1-epp 9090:9090

# View available metrics
curl http://localhost:9090/metrics

# Key metrics to monitor:
# - inference_pool_backend_health
# - inference_pool_request_count
# - vllm:num_requests_running
# - vllm:kv_cache_usage_perc
```

**Set up Grafana** (if available):
- Import vLLM dashboard: https://grafana.com/grafana/dashboards/23991-vllm/
- Add InferencePool metrics
- Monitor scheduler routing decisions

### 5. Cost Management

**When not using the cluster**:
```bash
# Scale deployments to 0
kubectl scale deployment --all -n llm-d --replicas=0

# Scale GPU nodes to 0 (saves ~$0.54/hour per node)
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool --num-nodes 0 \
  --zone us-central1-a --project ecoeng-llmd

# Scale CPU nodes to 1 (keep control plane)
gcloud container clusters resize nvidia-test-cluster \
  --node-pool default-pool --num-nodes 1 \
  --zone us-central1-a --project ecoeng-llmd
```

**Cost savings**: From ~$0.81/hour (full) to ~$0.14/hour (idle)

### 6. Explore Advanced Patterns

**Pattern 4: MoE with LeaderWorkerSet** (requires multi-node setup)
**Pattern 5: P/D Disaggregation** (separate prefill/decode pools)

See llm-d documentation: https://github.com/llm-d/llm-d

---

## Current Deployment Status Summary

### ✅ Pattern 1: Complete and Operational (2026-01-21)

**Model Deployed**: google/gemma-2b-it (2B parameters, instruction-tuned)
**Replicas**: 1 (Pattern 1: single replica deployment)
**GPU**: 1x NVIDIA T4 (14.58 GiB)
**Context Length**: 2048 tokens (optimized for T4 memory)

### Components Status

| Component | Status | Details |
|-----------|--------|---------|
| vLLM Pod | ✅ Running | ms-pattern1-llm-d-modelservice-decode-6f7899f5c5-bbtfg |
| Scheduler Pod | ✅ Running | gaie-pattern1-epp-6cdc8cfc4b-wmwbt |
| InferencePool | ✅ Active | gaie-pattern1, detecting vLLM backend |
| Gateway | ✅ Programmed | 35.209.201.202 (regional external LB) |
| HTTPRoute | ✅ Bound | llm-d-pattern1-inference-scheduling |
| Proxy Subnet | ✅ Created | proxy-only-subnet (192.168.0.0/23) |
| LoadBalancer | ✅ Running | 136.112.200.85:8000 (backup endpoint) |

### Infrastructure

**GCP Resources**:
- Project: ecoeng-llmd
- Cluster: nvidia-test-cluster (us-central1-a)
- VPC: default
- Subnets: default (10.128.0.0/20) + proxy-only-subnet (192.168.0.0/23)
- APIs: Gateway API, Network Services API enabled

**Kubernetes Resources**:
- Namespace: llm-d
- Deployments: 2 (vLLM + scheduler)
- Services: 3 (LoadBalancer + InferencePool + ext-proc)
- Gateway: infra-pattern1-inference-gateway
- HTTPRoute: llm-d-pattern1-inference-scheduling

### Endpoints

**Primary** (Gateway with Intelligent Routing):
```
http://35.209.201.202/v1/models
http://35.209.201.202/v1/completions
http://35.209.201.202/v1/chat/completions
```

**Backup** (Direct LoadBalancer):
```
http://136.112.200.85:8000/v1/models
http://136.112.200.85:8000/v1/completions
```

### Intelligent Routing Configuration

**Active Scoring Algorithms**:
- Prefix-cache-scorer (weight: 3) - Routes similar prompts to same backend
- KV-cache-utilization-scorer (weight: 2) - Balances cache usage
- Queue-scorer (weight: 2) - Routes based on queue depth

**Benefits** (become apparent with multi-replica scaling):
- Load-aware distribution across backends
- Prefix-cache-aware routing for KV cache efficiency
- Backend health monitoring
- Advanced routing policies

### Cost Analysis

**Current hourly cost** (1 GPU node, 2 CPU nodes):
- GPU node (n1-standard-4 + T4): ~$0.54/hour
- CPU nodes (2x e2-standard-4): ~$0.27/hour
- **Total**: ~$0.81/hour (~$583/month if running 24/7)

**Idle cost** (scaled to minimal):
- Control plane only: ~$0.14/hour (~$100/month)
- **Savings**: ~$0.67/hour (~$483/month)

### Known Limitations

1. **Reduced context length**: 2048 tokens (down from 4096) due to T4 GPU memory constraints
2. **Single replica**: Pattern 1 design - intelligent routing benefits appear with multi-replica
3. **No multi-model support**: Pattern 1 - single model deployment only

### Performance Expectations

**Expected metrics** (single replica):
- TTFT (p50): 0.3-0.8s
- TPOT (p50): 20-50ms
- Throughput: 500-1500 tokens/sec
- Max concurrent requests: ~10-20 (depends on prompt/completion length)

### Ready for Next Steps

✅ Benchmarking (compare Gateway vs direct LoadBalancer)
✅ Pattern 2 deployment (multi-model)
✅ Pattern 3 scaling (3+ replicas for load balancing)
✅ Metrics monitoring (Prometheus + Grafana)

## References

- [llm-d GitHub Repository](https://github.com/llm-d/llm-d)
- [llm-d Official Website](https://llm-d.ai/)
- [Inference Scheduling Guide](https://github.com/llm-d/llm-d/blob/main/guides/inference-scheduling/README.md)
- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/)
- [GKE Gateway API Documentation](https://cloud.google.com/kubernetes-engine/docs/concepts/gateway-api)
- [vLLM Documentation](https://docs.vllm.ai/)
- [MLPerf Inference 5.1](https://mlcommons.org/2025/09/small-llm-inference-5-1/)

## Support

For issues or questions:
- llm-d GitHub Issues: https://github.com/llm-d/llm-d/issues
- Review existing RHAIIS setup: `/home/jhull/devel/rhaiis-test/cluster-setup.md`
- Check benchmarking guide: `/home/jhull/devel/rhaiis-test/benchmarks.md`
