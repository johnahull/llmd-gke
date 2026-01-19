# GKE Cluster Setup for RHAIIS vLLM with TPU v6e (Trillium)

This document contains the steps to create and configure the GKE cluster for running RHAIIS vLLM with Google Cloud TPU v6e (Trillium) accelerators.

## Prerequisites

- Red Hat registry credentials configured in `/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`
- Hugging Face token with access to google/gemma-2b-it model
- Google Cloud project with TPU quota in europe-west4-a

## Step 1: Create GKE Cluster with TPU Node Pool

```bash
# Create the base cluster
gcloud container clusters create tpu-test-cluster \
  --zone europe-west4-a \
  --machine-type e2-standard-4 \
  --num-nodes 2 \
  --project ecoeng-llmd

# Add TPU v6e node pool (ct6e-standard-4t = 4 chips, 2x2 topology)
gcloud container node-pools create tpu-v6e-pool \
  --cluster tpu-test-cluster \
  --zone europe-west4-a \
  --machine-type ct6e-standard-4t \
  --num-nodes 1 \
  --enable-autoscaling \
  --min-nodes 0 --max-nodes 2 \
  --project ecoeng-llmd

# Get cluster credentials and set kubectl context
gcloud container clusters get-credentials tpu-test-cluster --zone europe-west4-a --project ecoeng-llmd

# Verify kubectl context is set correctly
kubectl config current-context
```

**Note:** GKE automatically handles TPU device access. Do NOT manually mount VFIO devices or use privileged mode.

## Step 2: Create Red Hat Registry Pull Secret

```bash
# Apply the pre-configured secret
kubectl apply -f /home/jhull/devel/11009103-jhull-svc-pull-secret.yaml
```

## Step 3: Deploy RHAIIS vLLM

```bash
# Apply the deployment
kubectl apply -f /home/jhull/devel/rhaiis-test/rhaiis-tpu.yaml

# Wait for pod to be ready (model download + XLA compilation takes ~3-4 minutes)
kubectl get pods -l app=rhaiis-tpu-inference -w
```

**Note:** First startup includes model download (~1-2 min) and XLA compilation (~1-2 min). Subsequent restarts only need model loading.

## Step 4: Expose the Service

```bash
# Create LoadBalancer service
kubectl expose deployment rhaiis-tpu-test \
  --port=8000 \
  --target-port=8000 \
  --type=LoadBalancer

# Wait for external IP (takes ~30 seconds)
kubectl get svc rhaiis-tpu-test -w
```

## Step 5: Test the Deployment

```bash
# Get the external IP
EXTERNAL_IP=$(kubectl get svc rhaiis-tpu-test -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test the API (first request triggers XLA compilation - may take 60-120 seconds)
curl -X POST http://$EXTERNAL_IP:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
  }'

# Health check
curl http://$EXTERNAL_IP:8000/health

# List models
curl http://$EXTERNAL_IP:8000/v1/models
```

## Suspend Cluster (Save Costs)

When not in use, scale down to zero nodes:

```bash
# Scale deployment to zero
kubectl scale deployment rhaiis-tpu-test --replicas=0

# Scale TPU node pool to zero
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 0 \
  --zone europe-west4-a

# Optional: Scale default pool to zero
gcloud container clusters resize tpu-test-cluster \
  --node-pool default-pool \
  --num-nodes 0 \
  --zone europe-west4-a
```

## Resume Cluster

```bash
# Scale TPU node pool back up
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 1 \
  --zone europe-west4-a

# Wait for node to be ready (TPU initialization takes 2-3 minutes)
kubectl get nodes -w

# Scale deployment back up
kubectl scale deployment rhaiis-tpu-test --replicas=1

# Wait for pod to be ready (model download + XLA compilation ~3-4 minutes)
kubectl get pods -l app=rhaiis-tpu-inference -w
```

## Delete Everything (Maximum Cost Savings)

```bash
# Delete deployment and service
kubectl delete -f /home/jhull/devel/rhaiis-test/rhaiis-tpu.yaml
kubectl delete service rhaiis-tpu-test

# Delete the entire cluster
gcloud container clusters delete tpu-test-cluster --zone europe-west4-a
```

## Key Configuration Details

**Deployment Configuration:**
- Image: `registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5`
- Model: `google/gemma-2b-it`
- TPU: v6e Trillium (4 chips in 2x2 topology)
- Max Context: 2048 tokens
- Tensor Parallelism: 4-way across TPU chips
- Backend: JAX with XLA compilation
- Performance: 3x better inference throughput vs v5e

**TPU Machine Types:**
- `ct6e-standard-1t`: 1 chip (1x1 topology) - minimal cost
- `ct6e-standard-4t`: 4 chips (2x2 topology) - recommended for most workloads
- `ct6e-standard-8t`: 8 chips (2x4 topology) - larger models

**Environment Variables:**
- `HF_TOKEN`: Hugging Face API token
- `PJRT_DEVICE`: TPU (enables TPU runtime)
- `TPU_CHIPS_PER_HOST_BOUNDS`: 2,2,1 (defines 2x2 topology for 4 chips)
- `TPU_HOST_BOUNDS`: 1,1,1 (single-host configuration)
- `VLLM_LOGGING_LEVEL`: DEBUG
- `HF_HUB_OFFLINE`: 0 (allow model downloads)

**Important Notes:**
- TPU v6e (Trillium) has **broad availability** across 9+ zones including europe-west4-a/b, us-central1-b, us-east1-d, europe-west4-a, asia-northeast1-b
- TPU v6e provides 3x better inference throughput compared to TPU v5e
- First inference request triggers XLA compilation (1-2 minutes delay) - this is normal
- Subsequent inference requests use compiled graph and are fast
- Do NOT override the container's `command` - only use `args`
- GKE automatically handles TPU device access (no manual VFIO mounting needed)
- Must request ALL TPU chips in the node (partial allocation not supported)
- Node selector must match machine type topology (2x2 for ct6e-standard-4t)

## Alternative Configurations

### Single Chip (Minimal Cost)

For smaller models or testing, use 1 TPU chip:

```yaml
# In rhaiis-tpu.yaml, modify:
nodeSelector:
  cloud.google.com/gke-tpu-topology: "1x1"
  cloud.google.com/gke-tpu-accelerator: "tpu-v6e-slice"
resources:
  requests:
    google.com/tpu: 1
  limits:
    google.com/tpu: 1
env:
  - name: TPU_CHIPS_PER_HOST_BOUNDS
    value: "1,1,1"
args:
  - "--tensor-parallel-size"
  - "1"
```

Update node pool:
```bash
gcloud container node-pools create tpu-v5e-1chip-pool \
  --cluster tpu-test-cluster \
  --zone europe-west4-a \
  --machine-type ct6e-standard-1t \
  --num-nodes 1
```

### 8 Chips (Larger Models)

For larger models requiring more memory:

```yaml
# In rhaiis-tpu.yaml, modify:
nodeSelector:
  cloud.google.com/gke-tpu-topology: "2x4"
  cloud.google.com/gke-tpu-accelerator: "tpu-v6e-slice"
resources:
  requests:
    google.com/tpu: 8
  limits:
    google.com/tpu: 8
env:
  - name: TPU_CHIPS_PER_HOST_BOUNDS
    value: "2,4,1"
args:
  - "--tensor-parallel-size"
  - "8"
  - "--max-model-len"
  - "4096"
```

Update node pool:
```bash
gcloud container node-pools create tpu-v5e-8chip-pool \
  --cluster tpu-test-cluster \
  --zone europe-west4-a \
  --machine-type ct6e-standard-8t \
  --num-nodes 1
```

## API Endpoints

Once deployed, the following OpenAI-compatible endpoints are available:

- `/v1/completions` - Text completion
- `/v1/chat/completions` - Chat completion
- `/v1/embeddings` - Text embeddings
- `/health` - Health check
- `/metrics` - Prometheus metrics
- `/v1/models` - List available models

## Troubleshooting

**Pod Pending - No Nodes Available:**
- Check TPU node pool exists: `kubectl get nodes -o wide`
- Verify topology label: `kubectl describe node | grep tpu-topology`
- Ensure auto-scaling is enabled or min-nodes > 0
- TPU nodes take 2-3 minutes to initialize

**Resource Allocation Error:**
- Verify requesting ALL TPU chips: `resources.limits.google.com/tpu: 4` for ct6e-standard-4t
- Ensure requests == limits (GKE requirement for TPU)
- Check node selector matches machine type topology (2x2 for 4 chips)

**First Inference Takes 60-120 Seconds:**
- This is NORMAL - XLA compilation happens on first request
- Check logs: `kubectl logs <pod-name> | grep -i "compilation\|xla"`
- Subsequent requests will be fast (use compiled graph)
- Increase client timeout to 3+ minutes for first request

**Model Compilation Errors:**
- Check logs for XLA errors: `kubectl logs <pod-name> | grep XLA`
- Verify `--tensor-parallel-size` matches TPU chip count (4 for ct6e-standard-4t)
- Ensure `--max-model-len` is appropriate for chip count (2048 safe for 4 chips)

**TPU Not Detected:**
- Verify node selector: `cloud.google.com/gke-tpu-accelerator: tpu-v6e-slice`
- Check node labels: `kubectl get nodes --show-labels | grep tpu`
- Ensure using correct zone (europe-west4-a for v5e)
- Verify `PJRT_DEVICE=TPU` environment variable is set

**Image Pull Error:**
- Verify secret exists: `kubectl get secret 11009103-jhull-svc-pull-secret`
- Re-apply secret if needed: `kubectl apply -f /home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`

**Pod CrashLoopBackOff:**
- Check logs: `kubectl logs <pod-name>`
- Common: Don't override `command`, only use `args`
- Verify environment variables (especially PJRT_DEVICE=TPU)
- Check TPU topology matches machine type

**Model Access Denied (403):**
- Authorize access to gated models on Hugging Face
- Verify HF_TOKEN is correct and has proper permissions

**Zone Not Supporting TPU v6e:**
- TPU v6e is available in: europe-west4-a/b, us-central1-b, us-east1-d, europe-west4-a, asia-northeast1-b, southamerica-west1-a
- TPU v6e has much broader availability than v5e
- If stockout occurs, try different zone from the list above

## Performance Characteristics

**Startup Time:**
- TPU node initialization: 2-3 minutes
- Model download (first time): 1-2 minutes
- XLA compilation (first inference): 1-2 minutes
- **Total cold start**: 4-7 minutes

**Runtime Performance:**
- First inference: 60-120 seconds (XLA compilation)
- Subsequent inference: Fast (uses compiled graph)
- Tensor parallelism: 4-way across TPU chips
- Max context: 2048 tokens (conservative for 4 chips)

## Cost Comparison

**TPU v6e (ct6e-standard-4t):**
- Check current GCP pricing for europe-west4-a
- Latest generation Trillium TPU
- 3x better inference throughput vs TPU v5e
- Cost-effective for inference workloads

**GPU (NVIDIA T4):**
- Lower per-hour cost but less optimized for large models
- Better for smaller models and mixed workloads

**Cost Optimization:**
- Scale to 0 nodes when not in use (stops all charges)
- Use auto-scaling to match demand
- Consider 1-chip configuration for development/testing
