# TPU VM Setup for RHAIIS vLLM

This document contains the steps to create and configure a Google Cloud TPU v6e VM for running RHAIIS vLLM inference.

## Prerequisites

- Red Hat registry credentials configured in `/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`
- Hugging Face token with access to model (e.g., google/gemma-2b-it)
- Google Cloud project with TPU quota enabled
- gcloud CLI installed and configured

## Cost Warning

**TPU v6e-1 costs approximately $1.28/hour ($30.72/day)**

TPU VMs cannot be paused or stopped - only deleted. Delete the VM when not in use to avoid charges.

## Step 1: Create TPU VM

```bash
# Create TPU v6e-1 VM with correct runtime image
gcloud compute tpus tpu-vm create test-tpu \
  --zone=us-east5-a \
  --accelerator-type=v6e-1 \
  --version=v2-alpha-tpuv6e \
  --project=ecoeng-llmd

# Verify creation
gcloud compute tpus tpu-vm list --zone=us-east5-a --project=ecoeng-llmd
```

**Important Notes:**
- Use `v2-alpha-tpuv6e` image - it has all TPU dependencies pre-configured
- Do NOT use `tpu-ubuntu2204-base` or `tpu-vm-pt-2.0` - they lack proper TPU runtime
- TPU v6e uses VFIO devices (`/dev/vfio/0`) not `/dev/accel*`
- The v2-alpha image automatically binds TPU PCI device to vfio-pci driver

## Step 2: SSH into TPU VM

```bash
# SSH into the VM
gcloud compute tpus tpu-vm ssh test-tpu --zone=us-east5-a --project=ecoeng-llmd
```

## Step 3: Install Podman (if not already installed)

```bash
# Update package list
sudo apt-get update

# Install podman
sudo apt-get install -y podman

# Verify installation
podman --version
```

## Step 4: Configure Red Hat Registry Authentication

```bash
# Copy your pull secret to the TPU VM
# Run this from your LOCAL machine (not in the TPU VM SSH session)
gcloud compute tpus tpu-vm scp \
  /home/jhull/devel/11009103-jhull-svc-pull-secret.yaml \
  test-tpu:~/ \
  --zone=us-east5-a \
  --project=ecoeng-llmd

# Back in the TPU VM SSH session, extract and configure Docker auth
grep 'dockerconfigjson:' ~/11009103-jhull-svc-pull-secret.yaml | \
  awk '{print $2}' | \
  base64 -d > ~/.docker-config-temp.json

# Move to proper location
mkdir -p ~/.docker
mv ~/.docker-config-temp.json ~/.docker/config.json

# Verify authentication works
podman login registry.redhat.io --get-login
```

## Step 5: Verify TPU Setup (Optional)

```bash
# Check TPU PCI device is detected
lspci | grep 1ae0

# Verify VFIO devices exist
ls -l /dev/vfio/

# Should see:
# /dev/vfio/vfio (character device)
# /dev/vfio/0 (IOMMU group for TPU)

# Check IOMMU group
ls /sys/kernel/iommu_groups/*/devices/*1ae0* 2>/dev/null
```

## Step 6: Run RHAIIS vLLM Container

```bash
# Run vLLM with google/gemma-2b-it model
podman run -d --name vllm-tpu --net=host --privileged \
  -e PJRT_DEVICE=TPU \
  -e TPU_CHIPS_PER_HOST_BOUNDS=1,1,1 \
  -e TPU_HOST_BOUNDS=1,1,1 \
  -e TPU_WORKER_HOSTNAMES=localhost \
  -e TPU_WORKER_ID=0 \
  -e TPU_NUM_DEVICES=1 \
  -e HF_TOKEN=$HF_TOKEN \
  -e HF_HUB_OFFLINE=0 \
  --device=/dev/vfio/vfio \
  --device=/dev/vfio/0 \
  registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5 \
  --model google/gemma-2b-it \
  --dtype half \
  --max-model-len 2048 \
  --port 8000

# Monitor startup (model download takes ~1-2 minutes, compilation another 1-2 minutes)
podman logs -f vllm-tpu
```

**Wait for this message:**
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Container Configuration:**
- Image: `registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5`
- Model: `google/gemma-2b-it` (2B parameters)
- Max context length: 2048 tokens
- TPU topology: Single chip (1x1x1)
- Backend: JAX/XLA for TPU

## Step 7: Configure Firewall (Run from LOCAL machine)

```bash
# Create firewall rule to allow external access to port 8000
gcloud compute firewall-rules create allow-vllm-tpu \
  --allow tcp:8000 \
  --source-ranges 0.0.0.0/0 \
  --description "Allow vLLM TPU API access" \
  --project=ecoeng-llmd

# If rule already exists, verify it:
gcloud compute firewall-rules describe allow-vllm-tpu --project=ecoeng-llmd
```

## Step 8: Get External IP and Test

```bash
# Get the external IP address (run from LOCAL machine)
EXTERNAL_IP=$(gcloud compute tpus tpu-vm describe test-tpu \
  --zone=us-east5-a \
  --project=ecoeng-llmd \
  --format='get(networkEndpoints[0].accessConfig[0].externalIp)')

echo "TPU VM External IP: $EXTERNAL_IP"

# Test the API endpoint
curl -X POST http://$EXTERNAL_IP:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-2b-it",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
  }' | python3 -m json.tool

# List available models
curl -s http://$EXTERNAL_IP:8000/v1/models | python3 -m json.tool

# Health check
curl http://$EXTERNAL_IP:8000/health
```

## Alternative Models

To use a different model, stop the container and restart with a new model:

```bash
# Stop current container
podman stop vllm-tpu
podman rm vllm-tpu

# Start with a different model (example: Mistral-7B)
podman run -d --name vllm-tpu --net=host --privileged \
  -e PJRT_DEVICE=TPU \
  -e TPU_CHIPS_PER_HOST_BOUNDS=1,1,1 \
  -e TPU_HOST_BOUNDS=1,1,1 \
  -e TPU_WORKER_HOSTNAMES=localhost \
  -e TPU_WORKER_ID=0 \
  -e TPU_NUM_DEVICES=1 \
  -e HF_TOKEN=$HF_TOKEN \
  -e HF_HUB_OFFLINE=0 \
  --device=/dev/vfio/vfio \
  --device=/dev/vfio/0 \
  registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5 \
  --model mistralai/Mistral-7B-Instruct-v0.3 \
  --dtype half \
  --max-model-len 4096 \
  --port 8000
```

### Recommended Models for TPU v6e-1:

**Small (2-3B):**
- `google/gemma-2b-it` - Current default
- `google/gemma-7b-it` - Larger Gemma
- `microsoft/Phi-3-mini-4k-instruct` - 3.8B, strong reasoning

**Medium (7-8B):**
- `mistralai/Mistral-7B-Instruct-v0.3` - Popular production choice
- `meta-llama/Llama-3.1-8B-Instruct` - State-of-the-art (requires license)
- `google/gemma-2-9b-it` - Latest Gemma

**Specialized:**
- `codellama/CodeLlama-7b-Instruct-hf` - Code generation

## Cost Management

### Delete TPU VM (Recommended when not in use)

```bash
# Delete the TPU VM to stop all charges
gcloud compute tpus tpu-vm delete test-tpu \
  --zone=us-east5-a \
  --project=ecoeng-llmd \
  --quiet

# Verify deletion
gcloud compute tpus tpu-vm list --zone=us-east5-a --project=ecoeng-llmd
```

**Cost Savings:** 100% - no charges while deleted

### Recreate When Needed

Simply run Step 1 again to recreate the VM, then follow steps 2-6. Model will be downloaded fresh (~2-3 minutes total startup time).

### Alternative: Stop Container (NOT recommended)

```bash
# Stop container (but still paying for TPU)
podman stop vllm-tpu

# Restart container
podman start vllm-tpu
```

**Cost Savings:** 0% - TPU charges continue even with container stopped

## API Endpoints

Once deployed, the following OpenAI-compatible endpoints are available:

- `POST /v1/completions` - Text completion
- `POST /v1/chat/completions` - Chat completion
- `POST /v1/embeddings` - Text embeddings (if using embedding model)
- `GET /v1/models` - List available models
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /tokenize` - Tokenize text
- `POST /detokenize` - Detokenize tokens

## Troubleshooting

### Container Won't Start - Missing VFIO Devices

**Issue:** `Error: VFIO device /dev/vfio/0 not found`

**Fix:** You're likely using the wrong TPU VM image. Delete and recreate with `v2-alpha-tpuv6e`:

```bash
gcloud compute tpus tpu-vm delete test-tpu --zone=us-east5-a --quiet
# Then recreate with --version=v2-alpha-tpuv6e
```

### Container Won't Start - Module Not Found

**Issue:** `ModuleNotFoundError: No module named 'jax'`

**Fix:** Same as above - wrong base image. Use `v2-alpha-tpuv6e`.

### Image Pull Error

**Issue:** `Error: unable to retrieve auth token: invalid username/password`

**Fix:** Re-extract Docker config:

```bash
grep 'dockerconfigjson:' ~/11009103-jhull-svc-pull-secret.yaml | \
  awk '{print $2}' | \
  base64 -d > ~/.docker/config.json
```

### Model Download Fails (403 Forbidden)

**Issue:** `GatedRepoError: Access to model requires authorization`

**Fix:**
1. Go to the model page on HuggingFace
2. Accept the license/terms
3. Verify your `HF_TOKEN` has access

### Port Not Accessible Externally

**Issue:** `curl: (7) Failed to connect to <IP> port 8000: Connection timed out`

**Fixes:**
1. Verify firewall rule exists: `gcloud compute firewall-rules list --filter="name=allow-vllm-tpu"`
2. Check container is running: `podman ps`
3. Verify container is binding to 0.0.0.0: `podman logs vllm-tpu | grep "0.0.0.0:8000"`
4. Test locally first: SSH into VM and `curl localhost:8000/health`

### Container Logs Show "Failed to get global TPU topology"

**Issue:** `RuntimeError: INTERNAL: Failed to get global TPU topology`

**Fix:** Wrong TPU VM image. The v2-alpha-tpuv6e image has proper metadata services configured.

## Container Management Commands

```bash
# View running containers
podman ps

# View all containers (including stopped)
podman ps -a

# View container logs
podman logs vllm-tpu

# Follow logs in real-time
podman logs -f vllm-tpu

# Stop container
podman stop vllm-tpu

# Start stopped container
podman start vllm-tpu

# Restart container
podman restart vllm-tpu

# Remove container (must be stopped first)
podman stop vllm-tpu
podman rm vllm-tpu

# View container resource usage
podman stats vllm-tpu
```

## Key Technical Details

**TPU v6e Architecture:**
- Uses VFIO (Virtual Function I/O) interface
- Single chip provides 1 TPU device
- PCI Device ID: 1ae0:006f (Google TPU v6e)
- Requires v2-alpha-tpuv6e runtime image

**RHAIIS vLLM Configuration:**
- Backend: JAX with XLA compilation for TPU
- Compilation mode: DYNAMO_TRACE_ONCE
- First request triggers model compilation (slower)
- Subsequent requests use compiled graph (fast)

**Environment Variables:**
- `PJRT_DEVICE=TPU` - Enables TPU runtime
- `TPU_CHIPS_PER_HOST_BOUNDS=1,1,1` - Single chip topology
- `TPU_HOST_BOUNDS=1,1,1` - Single host
- `TPU_NUM_DEVICES=1` - Total devices
- `HF_HUB_OFFLINE=0` - Allow model downloads
- `HF_TOKEN` - HuggingFace authentication

**Performance:**
- Model loading: ~1-2 minutes (download + compilation)
- Inference latency: ~100-500ms per request (model dependent)
- Throughput: Depends on model size and batch size
- Context length: Configurable via `--max-model-len`

## Quick Reference Card

```bash
# CREATE TPU
gcloud compute tpus tpu-vm create test-tpu --zone=us-east5-a --accelerator-type=v6e-1 --version=v2-alpha-tpuv6e --project=ecoeng-llmd

# SSH
gcloud compute tpus tpu-vm ssh test-tpu --zone=us-east5-a --project=ecoeng-llmd

# RUN VLLM (inside TPU VM)
podman run -d --name vllm-tpu --net=host --privileged -e PJRT_DEVICE=TPU -e TPU_CHIPS_PER_HOST_BOUNDS=1,1,1 -e TPU_HOST_BOUNDS=1,1,1 -e TPU_WORKER_HOSTNAMES=localhost -e TPU_WORKER_ID=0 -e TPU_NUM_DEVICES=1 -e HF_TOKEN=$HF_TOKEN -e HF_HUB_OFFLINE=0 --device=/dev/vfio/vfio --device=/dev/vfio/0 registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5 --model google/gemma-2b-it --dtype half --max-model-len 2048 --port 8000

# GET IP (from local machine)
gcloud compute tpus tpu-vm describe test-tpu --zone=us-east5-a --project=ecoeng-llmd --format='get(networkEndpoints[0].accessConfig[0].externalIp)'

# DELETE TPU
gcloud compute tpus tpu-vm delete test-tpu --zone=us-east5-a --project=ecoeng-llmd --quiet
```
