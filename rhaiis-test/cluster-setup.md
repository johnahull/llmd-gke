# GKE Cluster Setup for RHAIIS vLLM

This document contains the steps to create and configure the GKE cluster for running RHAIIS vLLM with NVIDIA T4 GPUs.

## Prerequisites

- Red Hat registry credentials configured in `/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`
- Hugging Face token with access to google/gemma-2b-it model

## Step 1: Create GKE Cluster with GPU Node Pool

```bash
# Create the base cluster
gcloud container clusters create nvidia-test-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --num-nodes 2

# Add GPU node pool with NVIDIA T4
gcloud container node-pools create nvidia-t4-pool \
  --cluster nvidia-test-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1 \
  --enable-autoscaling \
  --min-nodes 0 --max-nodes 3

# Get cluster credentials and set kubectl context
gcloud container clusters get-credentials nvidia-test-cluster --zone us-central1-a

# Verify kubectl context is set correctly
kubectl config current-context
```

**Note:** GKE automatically installs NVIDIA drivers. Do NOT install GPU Operator as it conflicts with GKE's native GPU support.

## Step 2: Create Red Hat Registry Pull Secret

```bash
# Apply the pre-configured secret
kubectl apply -f /home/jhull/devel/11009103-jhull-svc-pull-secret.yaml
```

## Step 3: Deploy RHAIIS vLLM

```bash
# Apply the deployment
kubectl apply -f /home/jhull/devel/rhaiis-test/rhaiis-nvidia.yaml

# Wait for pod to be ready (model download takes ~1-2 minutes)
kubectl get pods -l app=rhaiis-inference -w
```

## Step 4: Expose the Service

```bash
# Create LoadBalancer service
kubectl expose deployment rhaiis-t4-test \
  --port=8000 \
  --target-port=8000 \
  --type=LoadBalancer

# Wait for external IP (takes ~30 seconds)
kubectl get svc rhaiis-t4-test -w
```

## Step 5: Test the Deployment

```bash
# Get the external IP
EXTERNAL_IP=$(kubectl get svc rhaiis-t4-test -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test the API
curl -X POST http://$EXTERNAL_IP:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
  }'
```

## Suspend Cluster (Save Costs)

When not in use, scale down to zero nodes:

```bash
# Scale deployment to zero
kubectl scale deployment rhaiis-t4-test --replicas=0

# Scale GPU node pool to zero
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool \
  --num-nodes 0 \
  --zone us-central1-a

# Optional: Scale default pool to zero
gcloud container clusters resize nvidia-test-cluster \
  --node-pool default-pool \
  --num-nodes 0 \
  --zone us-central1-a
```

## Resume Cluster

```bash
# Scale GPU node pool back up
gcloud container clusters resize nvidia-test-cluster \
  --node-pool nvidia-t4-pool \
  --num-nodes 1 \
  --zone us-central1-a

# Wait for node to be ready
kubectl get nodes -w

# Scale deployment back up
kubectl scale deployment rhaiis-t4-test --replicas=1

# Wait for pod to be ready
kubectl get pods -l app=rhaiis-inference -w
```

## Delete Everything (Maximum Cost Savings)

```bash
# Delete deployment and service
kubectl delete -f /home/jhull/devel/rhaiis-test/rhaiis-nvidia.yaml
kubectl delete service rhaiis-t4-test

# Delete the entire cluster
gcloud container clusters delete nvidia-test-cluster --zone us-central1-a
```

## Key Configuration Details

**Deployment Configuration:**
- Image: `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.0.0`
- Model: `google/gemma-2b-it`
- GPU: NVIDIA T4 (1x)
- Memory: 13.12 GiB GPU memory (90% utilization)
- KV Cache: 6.08 GiB
- Max Concurrency: ~86x for 4096 token requests
- Backend: XFormers (T4 doesn't support FlashAttention-2)

**Environment Variables:**
- `HF_TOKEN`: Hugging Face API token
- `NVIDIA_VISIBLE_DEVICES`: all
- `NVIDIA_DRIVER_CAPABILITIES`: compute,utility
- `VLLM_LOGGING_LEVEL`: DEBUG
- `LD_LIBRARY_PATH`: /usr/local/nvidia/lib64:/usr/local/nvidia/lib:/usr/lib64:/usr/lib

**Important Notes:**
- Do NOT override the container's `command` - it breaks module imports
- Only use `args` to pass vLLM parameters
- GKE's native GPU support handles driver installation automatically
- Model downloads from Hugging Face on first run (~1-2 minutes)

## API Endpoints

Once deployed, the following OpenAI-compatible endpoints are available:

- `/v1/completions` - Text completion
- `/v1/chat/completions` - Chat completion
- `/v1/embeddings` - Text embeddings
- `/health` - Health check
- `/metrics` - Prometheus metrics
- `/v1/models` - List available models

## Troubleshooting

**Pod in CrashLoopBackOff:**
- Check logs: `kubectl logs <pod-name>`
- Common issues: Module not found (don't override `command`), NVIDIA libraries not found (check `LD_LIBRARY_PATH`)

**Image Pull Error:**
- Verify secret exists: `kubectl get secret 11009103-jhull-svc-pull-secret`
- Test credentials: `kubectl get pods -l app=rhaiis-inference` and check events

**GPU Not Detected:**
- Verify GPU node exists: `kubectl get nodes -o wide`
- Check GPU allocation: `kubectl describe nodes | grep nvidia.com/gpu`
- Don't install GPU Operator on GKE

**Model Access Denied (403):**
- Authorize access to gated models on Hugging Face
- Verify HF_TOKEN is correct and has proper permissions
