# Pattern 1: Istio + KServe + llm-d + vLLM on TPU v6e

Complete architecture and deployment guide for Pattern 1 using Istio Ingress Gateway, KServe LLMInferenceService, llm-d EPP scheduler, and vLLM on Google Cloud TPU v6e accelerators.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Component Details](#component-details)
- [Prerequisites](#prerequisites)
- [Deployment Guide](#deployment-guide)
- [Configuration Reference](#configuration-reference)
- [Verification and Testing](#verification-and-testing)
- [Troubleshooting](#troubleshooting)
- [Key Differences from Current Pattern 1](#key-differences-from-current-pattern-1)

## Architecture Overview

### High-Level Traffic Flow

```
Internet
  ↓
Istio Ingress Gateway (LoadBalancer Service)
  ↓
Gateway (Gateway API CRD, managed by Istio)
  ↓
HTTPRoute (auto-created by KServe)
  ↓
InferencePool v1alpha2 (auto-created by KServe)
  ↓
EPP Scheduler (intelligent routing)
  ↓
vLLM Pods on TPU v6e (managed by KServe LLMInferenceService)
```

### Core Components

| Component | Type | Purpose | Created By |
|-----------|------|---------|------------|
| **Istio Ingress Gateway** | Deployment | External traffic entry, TLS termination, observability | sail-operator |
| **Gateway (Gateway API)** | CRD | Configures ingress gateway listeners | Infrastructure |
| **HTTPRoute** | CRD | Routing rules to InferencePool | KServe controller |
| **InferencePool** | CRD (v1alpha2) | Manages pool of inference endpoints | KServe controller |
| **EPP Scheduler** | Service | Intelligent endpoint selection (queue depth, KV cache aware) | KServe controller |
| **LLMInferenceService** | CRD | Declarative model deployment | User |
| **vLLM Pods** | Pod | Model serving on TPU v6e with JAX/XLA backend | KServe controller |

### Key Design Decisions

1. **Istio via sail-operator (OSSM 3.1.x)** - Required for InferencePool v1alpha2 API compatibility with KServe v0.15
2. **KServe LLMInferenceService** - Manages vLLM lifecycle (autoscaling, canary, monitoring, HTTPRoute creation)
3. **Gateway API (not Istio VirtualService)** - Kubernetes-native routing, required by llm-d InferencePool
4. **EPP Scheduler** - Enabled via `router.scheduler: {}` in LLMInferenceService spec
5. **Istio Ingress Gateway only** - No service mesh sidecars (minimize resource overhead)

## Component Details

### Request Path Detail

```
1. Client → Istio Ingress Gateway
   - External LoadBalancer IP (GCP L4 LB)
   - Port 80/443 (HTTP/HTTPS)
   - TLS termination handled by cert-manager certificates
   - Observability: Envoy access logs, metrics, distributed traces

2. Gateway CRD → HTTPRoute Matching
   - Gateway API listeners on port 80/443
   - HTTPRoute matches path prefix "/"
   - Routes to InferencePool backend

3. HTTPRoute → InferencePool (v1alpha2)
   - InferencePool manages vLLM endpoint discovery
   - If EPP enabled: routes to EPP scheduler
   - If EPP disabled: direct round-robin to pods

4. EPP Scheduler → vLLM Pod Selection
   - Evaluates all available vLLM endpoints
   - Scoring based on:
     * Queue depth (lower is better)
     * KV cache utilization (higher is better)
     * Prefix cache hit rate (higher is better)
   - Selects optimal endpoint

5. vLLM Container → Model Inference
   - Container: registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5
   - vLLM exposes OpenAI-compatible API on port 8000
   - TPU v6e: 4 chips (2x2 topology), JAX/XLA backend
   - Model: Qwen/Qwen2.5-3B-Instruct
```

### Observability Flow

```
vLLM (port 8000/metrics) → Prometheus (if monitoring enabled)
EPP Scheduler (port 9090/metrics) → Prometheus
Istio Ingress Gateway (port 15090/stats/prometheus) → Prometheus
All components → Jaeger (distributed tracing via Istio)
```

### API Version Compatibility

**Critical:** KServe v0.15 requires OSSM 3.1.x for InferencePool API compatibility.

| Sail Operator | Istio Version | InferencePool API | KServe Compatibility |
|---------------|---------------|-------------------|----------------------|
| 3.1.x | v1.26.x | inference.networking.x-k8s.io/v1alpha2 | KServe v0.15 ✅ |
| 3.2.x | v1.27.x | inference.networking.k8s.io/v1 | Future KServe versions |

## Prerequisites

### Google Cloud Platform

- **GKE Cluster:** `tpu-test-cluster` in zone `europe-west4-a`
- **TPU Node Pool:** `ct6e-standard-4t` machine type (4 TPU v6e chips)
- **Project:** `ecoeng-llmd`
- **Quotas:** Minimum 4 TPU v6e chips in europe-west4-a

### Local Tools

```bash
# Required CLI tools
kubectl version --client
helm version
helmfile --version
kustomize version  # v5.7+
podman version  # or docker
```

### Red Hat Pull Secret

All operators and vLLM images require Red Hat registry authentication.

**Option 1: Registry Service Account (Recommended)**

1. Go to: https://access.redhat.com/terms-based-registry/
2. Click "New Service Account"
3. Create account and note credentials
4. Login:
   ```bash
   podman login registry.redhat.io
   Username: {REGISTRY-SERVICE-ACCOUNT-USERNAME}
   Password: {REGISTRY-SERVICE-ACCOUNT-PASSWORD}
   ```

**Option 2: Red Hat Account Credentials**

```bash
podman login registry.redhat.io
Username: {YOUR-REDHAT-USERNAME}
Password: {YOUR-REDHAT-PASSWORD}
```

**Configure Persistent Storage:**

```bash
mkdir -p ~/.config/containers
# Podman stores credentials in ~/.config/containers/auth.json automatically

# Verify access
podman pull registry.redhat.io/ubi8/ubi-minimal --quiet && echo "OK"
```

### HuggingFace Token

Required for downloading models from HuggingFace Hub.

1. Create account at https://huggingface.co
2. Generate token at https://huggingface.co/settings/tokens
3. For gated models (e.g., Llama), accept the model license agreement

## Deployment Guide

### Phase 1: Deploy Operators (llm-d-infra-xks)

**Step 1: Clone Infrastructure Repository**

```bash
git clone https://github.com/aneeshkp/llm-d-infra-xks.git
cd llm-d-infra-xks
```

**Step 2: Configure values.yaml**

```bash
cat > values.yaml <<EOF
useSystemPodmanAuth: true

certManager:
  enabled: true

sailOperator:
  enabled: true
  istioVersion: "v1.26.6"  # OSSM 3.1.x for InferencePool v1alpha2 compatibility

lwsOperator:
  enabled: false  # Not needed for Pattern 1 (single replica)
EOF
```

**Step 3: Deploy Operators**

```bash
make deploy  # Deploys cert-manager + istio
```

Expected output:
```
Installing cert-manager-operator...
Installing sail-operator...
Waiting for operators to be ready...
```

**Step 4: Verify Operators**

```bash
make status
```

Expected output:
```
=== cert-manager ===
NAME                                       READY   STATUS    RESTARTS   AGE
cert-manager-operator-xyz-123              1/1     Running   0          2m
cert-manager-xyz-456                       1/1     Running   0          1m
cert-manager-cainjector-xyz-789           1/1     Running   0          1m
cert-manager-webhook-xyz-012              1/1     Running   0          1m

=== sail-operator (istio) ===
NAME                                       READY   STATUS    RESTARTS   AGE
servicemesh-operator3-xyz-345             1/1     Running   0          2m
istiod-xyz-678                            1/1     Running   0          1m

=== Custom Resources ===
NAME      VERSION   AGE
cluster   1.15.2    2m

NAME      VERSION   AGE
default   v1.26.6   1m
```

### Phase 2: Deploy KServe Controller

**Step 1: Clone KServe Repository**

```bash
cd ~
git clone https://github.com/opendatahub-io/kserve.git
cd kserve
git checkout release-v0.15
```

**Step 2: Create OpenDataHub Namespace**

```bash
kubectl create namespace opendatahub --dry-run=client -o yaml | kubectl apply -f -
```

**Step 3: Apply cert-manager PKI Resources**

This must be done **BEFORE** deploying KServe controller to avoid webhook certificate issues.

```bash
kubectl apply -k config/overlays/odh-xks/cert-manager
kubectl wait --for=condition=Ready clusterissuer/opendatahub-ca-issuer --timeout=120s
```

Expected output:
```
clusterissuer.cert-manager.io/opendatahub-ca-issuer condition met
```

**Step 4: Deploy KServe Controller**

```bash
kustomize build config/overlays/odh-xks | kubectl apply --server-side -f -
```

The `odh-xks` overlay disables OpenShift-specific features:
- `LLMISVC_MONITORING_DISABLED=true` - No Prometheus Operator dependency
- `LLMISVC_AUTH_DISABLED=true` - No Authorino/Kuadrant dependency
- `LLMISVC_SCC_DISABLED=true` - No OpenShift SecurityContextConstraints

**Step 5: Wait for Controller**

```bash
kubectl wait --for=condition=Available deployment/kserve-controller-manager \
  -n opendatahub --timeout=300s
```

**Step 6: Verify LLMInferenceServiceConfig Templates**

```bash
kubectl get llminferenceserviceconfig -n opendatahub
```

Expected output:
```
NAME                  AGE
default-predictor     1m
vllm-default          1m
```

### Phase 3: Setup Gateway

**Step 1: Run Gateway Setup Script**

```bash
cd ~/llm-d-infra-xks
./scripts/setup-gateway.sh
```

This creates:
- Gateway resource in opendatahub namespace
- Mounts CA bundle at `/var/run/secrets/opendatahub/ca.crt` for mTLS

**Step 2: Verify Gateway**

```bash
kubectl get gateway -n opendatahub
kubectl get pods -n opendatahub -l gateway.networking.k8s.io/gateway-name=inference-gateway
```

Expected output:
```
NAME                ADDRESSES      PROGRAMMED   AGE
inference-gateway   34.xxx.xxx.xxx  True         1m

NAME                                    READY   STATUS    RESTARTS   AGE
inference-gateway-istio-xyz-123         1/1     Running   0          1m
```

**Step 3: Fix Gateway Pull Secret (if needed)**

If the Gateway pod shows `ErrImagePull`:

```bash
kubectl get secret redhat-pull-secret -n istio-system -o yaml | \
  sed 's/namespace: istio-system/namespace: opendatahub/' | kubectl apply -f -

kubectl patch sa inference-gateway-istio -n opendatahub \
  -p '{"imagePullSecrets": [{"name": "redhat-pull-secret"}]}'

kubectl delete pod -n opendatahub -l gateway.networking.k8s.io/gateway-name=inference-gateway
```

### Phase 4: Setup Application Namespace

**Step 1: Create Namespace**

```bash
export NAMESPACE=llm-d-inference-scheduling
kubectl create namespace $NAMESPACE
```

**Step 2: Create Red Hat Pull Secret**

```bash
kubectl create secret generic redhat-pull-secret \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson=~/.config/containers/auth.json \
  -n $NAMESPACE
```

**Step 3: Patch Default ServiceAccount**

```bash
kubectl patch serviceaccount default -n $NAMESPACE \
  -p '{"imagePullSecrets": [{"name": "redhat-pull-secret"}]}'
```

**Step 4: Create HuggingFace Token Secret**

```bash
kubectl create secret generic hf-token \
  --from-literal=HF_TOKEN=<your-huggingface-token> \
  -n $NAMESPACE
```

### Phase 5: Deploy Pattern 1 LLMInferenceService

**Step 1: Create LLMInferenceService Manifest**

Save as `pattern1/manifests/llmisvc-pattern1-tpu.yaml`:

```yaml
apiVersion: serving.kserve.io/v1alpha1
kind: LLMInferenceService
metadata:
  name: qwen2-3b-pattern1
  namespace: llm-d-inference-scheduling
spec:
  model:
    uri: hf://Qwen/Qwen2.5-3B-Instruct
    name: Qwen/Qwen2.5-3B-Instruct
  replicas: 1  # Pattern 1: single replica baseline

  # Router configuration
  router:
    route: {}      # Auto-create HTTPRoute
    gateway: {}    # Bind to Gateway
    scheduler: {}  # Enable EPP scheduler for intelligent routing

  # vLLM container template
  template:
    containers:
    - name: main
      image: registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5

      # vLLM arguments
      args:
      - --model=Qwen/Qwen2.5-3B-Instruct
      - --dtype=half
      - --max-model-len=2048
      - --tensor-parallel-size=4  # Match TPU chip count
      - --disable-log-requests

      # TPU environment variables
      env:
      - name: TPU_CHIPS_PER_HOST_BOUNDS
        value: "2,2,1"  # 2x2 topology for 4 chips
      - name: TPU_HOST_BOUNDS
        value: "1,1,1"  # Single host
      - name: PJRT_DEVICE
        value: "TPU"
      - name: HF_TOKEN
        valueFrom:
          secretKeyRef:
            name: hf-token
            key: HF_TOKEN

      # Resource allocation
      resources:
        limits:
          google.com/tpu: "4"  # MUST request all 4 chips
        requests:
          google.com/tpu: "4"

      # Health probes
      livenessProbe:
        httpGet:
          path: /health
          port: 8000
          scheme: HTTPS
        initialDelaySeconds: 240  # TPU init (2-3 min) + model download + compilation
        periodSeconds: 30
        timeoutSeconds: 30
        failureThreshold: 5

      readinessProbe:
        httpGet:
          path: /v1/models
          port: 8000
          scheme: HTTPS
        initialDelaySeconds: 240
        periodSeconds: 10
        timeoutSeconds: 10

    # TPU node selector
    nodeSelector:
      cloud.google.com/gke-tpu-topology: 2x2
      cloud.google.com/gke-tpu-accelerator: tpu-v6e

    # Pull secret
    imagePullSecrets:
    - name: redhat-pull-secret
```

**Step 2: Apply Manifest**

```bash
kubectl apply -f pattern1/manifests/llmisvc-pattern1-tpu.yaml
```

**Step 3: Monitor Deployment**

```bash
# Watch LLMInferenceService status
kubectl get llmisvc -n llm-d-inference-scheduling -w

# Check pods
kubectl get pods -n llm-d-inference-scheduling

# View logs
kubectl logs -n llm-d-inference-scheduling \
  -l serving.kserve.io/llminferenceservice=qwen2-3b-pattern1 -f
```

Expected startup sequence:
1. **Pod creation:** 30-60 seconds
2. **TPU initialization:** 2-3 minutes
3. **Model download:** 1-2 minutes (first time)
4. **XLA compilation:** 60-120 seconds (on first inference)

## Configuration Reference

### TPU v6e Configuration

#### Critical TPU Constraints

| Constraint | Requirement | Why |
|------------|-------------|-----|
| **Chip allocation** | Must request all 4 chips | GKE Warden enforces ct6e-standard-4t node topology |
| **Topology bounds** | `TPU_CHIPS_PER_HOST_BOUNDS=2,2,1` | MUST match requested chip count |
| **Startup time** | 4-7 minutes | TPU init (2-3 min) + model download + XLA compilation |
| **First inference** | 60-120s delay | JIT compilation (one-time per model load) |
| **Health probe delay** | `initialDelaySeconds: 240` | Allow time for full TPU initialization |
| **Backend** | JAX/XLA | Different from GPU (PyTorch/CUDA) |
| **Requests = Limits** | Must match exactly | GKE requirement for TPU resources |

#### TPU Environment Variables

```yaml
env:
- name: TPU_CHIPS_PER_HOST_BOUNDS
  value: "2,2,1"  # 2x2 topology for 4 chips (ct6e-standard-4t)

- name: TPU_HOST_BOUNDS
  value: "1,1,1"  # Single host (Pattern 1)

- name: PJRT_DEVICE
  value: "TPU"  # Use TPU backend (JAX/XLA)
```

#### TPU Node Selector

```yaml
nodeSelector:
  cloud.google.com/gke-tpu-topology: 2x2
  cloud.google.com/gke-tpu-accelerator: tpu-v6e
```

#### vLLM Arguments for TPU

```yaml
args:
- --model=Qwen/Qwen2.5-3B-Instruct
- --dtype=half  # FP16 precision
- --max-model-len=2048  # Context window
- --tensor-parallel-size=4  # MUST match TPU chip count
- --disable-log-requests  # Reduce log verbosity
```

### GKE Cluster Configuration

**Verify TPU Node Pool:**

```bash
gcloud container node-pools list \
  --cluster=tpu-test-cluster \
  --zone=europe-west4-a \
  --project=ecoeng-llmd
```

Expected output:
```
NAME            MACHINE_TYPE        DISK_SIZE_GB  NODE_VERSION
tpu-v6e-pool    ct6e-standard-4t    100           1.XX.X-gke.XXX
```

**Create TPU Node Pool (if missing):**

```bash
gcloud container node-pools create tpu-v6e-pool \
  --cluster=tpu-test-cluster \
  --zone=europe-west4-a \
  --machine-type=ct6e-standard-4t \
  --num-nodes=1 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=2 \
  --project=ecoeng-llmd
```

### KServe Controller Configuration

The `odh-xks` overlay sets these environment variables:

```yaml
env:
- name: LLMISVC_MONITORING_DISABLED
  value: "true"  # Disable Prometheus Operator dependency

- name: LLMISVC_AUTH_DISABLED
  value: "true"  # Disable Authorino/Kuadrant dependency

- name: LLMISVC_SCC_DISABLED
  value: "true"  # Disable OpenShift SecurityContextConstraints
```

To enable monitoring:

```bash
# Deploy Prometheus Operator first, then:
kubectl set env deployment/kserve-controller-manager \
  -n opendatahub \
  LLMISVC_MONITORING_DISABLED=false
```

## Verification and Testing

### Step 1: Verify Infrastructure

```bash
# Check operators
kubectl get pods -n cert-manager-operator
kubectl get pods -n cert-manager
kubectl get pods -n istio-system

# Check KServe controller
kubectl get pods -n opendatahub -l control-plane=kserve-controller-manager

# Check Gateway
kubectl get gateway -n opendatahub
kubectl get pods -n opendatahub -l gateway.networking.k8s.io/gateway-name=inference-gateway
```

All pods should show `Running` status.

### Step 2: Check LLMInferenceService Status

```bash
kubectl get llmisvc qwen2-3b-pattern1 -n llm-d-inference-scheduling
```

Expected output:
```
NAME                 READY   URL
qwen2-3b-pattern1    True    http://qwen2-3b-pattern1.llm-d-inference-scheduling.svc.cluster.local
```

### Step 3: Verify Auto-Created Resources

```bash
# InferencePool (created by KServe)
kubectl get inferencepool -n llm-d-inference-scheduling

# HTTPRoute (created by KServe)
kubectl get httproute -n llm-d-inference-scheduling

# Pods
kubectl get pods -n llm-d-inference-scheduling
```

### Step 4: Test Inference

**Get Gateway IP:**

```bash
GATEWAY_IP=$(kubectl get gateway inference-gateway -n opendatahub \
  -o jsonpath='{.status.addresses[0].value}')

echo "Gateway IP: $GATEWAY_IP"
```

**Send Test Request:**

```bash
curl -X POST "http://${GATEWAY_IP}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Host: qwen2-3b-pattern1.llm-d-inference-scheduling.svc.cluster.local" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [{"role": "user", "content": "What is Kubernetes?"}],
    "max_tokens": 100
  }'
```

**Expected response:**

```json
{
  "id": "cmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "Qwen/Qwen2.5-3B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Kubernetes is an open-source container orchestration platform..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

**Note:** First inference will be slow (60-120 seconds) due to XLA compilation. Subsequent requests should complete in <1 second.

### Step 5: Check Metrics

**vLLM Metrics:**

```bash
kubectl port-forward -n llm-d-inference-scheduling \
  svc/qwen2-3b-pattern1 8000:8000

curl http://localhost:8000/metrics
```

**Istio Gateway Metrics:**

```bash
kubectl exec -n istio-system deploy/istio-ingressgateway -- \
  curl -s localhost:15090/stats/prometheus | grep istio
```

**EPP Scheduler Metrics (if enabled):**

```bash
kubectl logs -n llm-d-inference-scheduling -l app=epp-scheduler
```

## Troubleshooting

### Gateway Pod ImagePullBackOff

**Symptom:** Gateway pod fails to pull Istio proxy image

```
NAME                                    READY   STATUS             RESTARTS   AGE
inference-gateway-istio-xyz-123         0/1     ImagePullBackOff   0          2m
```

**Fix:**

```bash
# Copy pull secret to opendatahub namespace
kubectl get secret redhat-pull-secret -n istio-system -o yaml | \
  sed 's/namespace: istio-system/namespace: opendatahub/' | kubectl apply -f -

# Patch ServiceAccount
kubectl patch sa inference-gateway-istio -n opendatahub \
  -p '{"imagePullSecrets": [{"name": "redhat-pull-secret"}]}'

# Restart pod
kubectl delete pod -n opendatahub -l gateway.networking.k8s.io/gateway-name=inference-gateway
```

### vLLM Pod Stuck in ContainerCreating

**Symptom:** Pod waiting for TPU resources

```
NAME                                    READY   STATUS              RESTARTS   AGE
qwen2-3b-pattern1-predictor-xyz-123    0/1     ContainerCreating   0          5m
```

**Check:**

```bash
kubectl describe pod <pod-name> -n llm-d-inference-scheduling
```

Look for events like:
```
Events:
  Warning  FailedScheduling  0/3 nodes are available: 3 Insufficient google.com/tpu
```

**Fix:** Ensure TPU node pool has capacity:

```bash
gcloud container node-pools describe tpu-v6e-pool \
  --cluster=tpu-test-cluster \
  --zone=europe-west4-a \
  --project=ecoeng-llmd
```

If `currentNodeCount: 0`, scale up:

```bash
gcloud container clusters resize tpu-test-cluster \
  --node-pool tpu-v6e-pool \
  --num-nodes 1 \
  --zone europe-west4-a \
  --project=ecoeng-llmd
```

### vLLM Pod CrashLoopBackOff

**Symptom:** Pod starts but crashes repeatedly

```bash
kubectl logs -n llm-d-inference-scheduling <pod-name>
```

**Common causes:**

1. **Out of memory:** Reduce `--max-model-len`
2. **Wrong topology:** Check `TPU_CHIPS_PER_HOST_BOUNDS` matches requested chips
3. **Model download failure:** Check HuggingFace token and model access

### KServe Controller Webhook Issues

**Symptom:** `kubectl apply` hangs or fails with webhook timeout

```
Error from server (InternalError): error when creating "llmisvc.yaml":
Internal error occurred: failed calling webhook...
```

**Fix:**

```bash
# Delete problematic webhook configurations
kubectl delete validatingwebhookconfiguration \
  llminferenceservice.serving.kserve.io \
  llminferenceserviceconfig.serving.kserve.io

# Re-apply KServe
kustomize build config/overlays/odh-xks | kubectl apply --server-side --force-conflicts -f -
```

### InferencePool Not Created

**Symptom:** LLMInferenceService shows Ready but no InferencePool exists

**Check Istio version:**

```bash
kubectl get istio -n istio-system -o yaml | grep version
```

**Requirement:** Must use OSSM 3.1.x (Istio 1.26.x) for InferencePool v1alpha2 compatibility.

If using OSSM 3.2.x, downgrade:

```bash
cd ~/llm-d-infra-xks
# Edit values.yaml and set istioVersion: "v1.26.6"
make deploy-istio
```

### First Inference Timeout

**Symptom:** First request to vLLM takes 60-120 seconds or times out

**Explanation:** This is **expected behavior** on TPU. XLA compilation happens on first inference. Subsequent requests will be fast (<1s).

**Solution:** Increase request timeout for first inference:

```bash
curl -X POST "http://${GATEWAY_IP}/v1/chat/completions" \
  --max-time 180 \  # 3 minute timeout
  -H "Content-Type: application/json" \
  ...
```

### HTTPRoute Not Routing to InferencePool

**Symptom:** Requests return 404 or connection refused

**Check HTTPRoute:**

```bash
kubectl get httproute -n llm-d-inference-scheduling -o yaml
```

Ensure `backendRefs` points to InferencePool:

```yaml
backendRefs:
- group: inference.networking.x-k8s.io
  kind: InferencePool
  name: qwen2-3b-pattern1-pool
```

**Check InferencePool endpoints:**

```bash
kubectl describe inferencepool -n llm-d-inference-scheduling
```

Should show discovered vLLM endpoints.

## Key Differences from Current Pattern 1

### Current Architecture (Helm-based)

```
GKE Gateway → HTTPRoute → InferencePool → EPP → vLLM pods
(deployed via llm-d Helm charts)
```

### New Architecture (KServe-based)

```
Istio Ingress Gateway → Gateway (API) → HTTPRoute → InferencePool → EPP → vLLM pods
(HTTPRoute + InferencePool auto-created by KServe LLMInferenceService)
```

### What Changes

| Component | Current | New |
|-----------|---------|-----|
| **Ingress** | GKE Gateway (gke-l7-gxlb) | Istio Ingress Gateway (sail-operator) |
| **vLLM Deployment** | Helm chart (llm-d-modelservice) | KServe LLMInferenceService CRD |
| **HTTPRoute** | Manual manifest | Auto-created by KServe |
| **InferencePool** | Created by llm-d Helm chart | Auto-created by KServe |
| **EPP Scheduler** | Deployed via Helm | Enabled via `router.scheduler: {}` |
| **Certificate Management** | GKE managed | cert-manager |

### What Stays the Same

- vLLM container image (registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5)
- TPU configuration (4 chips, 2x2 topology)
- Model (Qwen/Qwen2.5-3B-Instruct)
- OpenAI-compatible API endpoints
- InferencePool API (inference.networking.x-k8s.io/v1alpha2)
- Intelligent routing via EPP scheduler

### Migration Path

To migrate from Helm-based to KServe-based Pattern 1:

1. **Deploy operators** (Phase 1-3)
2. **Create namespace and secrets** (Phase 4)
3. **Deploy LLMInferenceService** (Phase 5)
4. **Verify auto-created resources** (InferencePool, HTTPRoute)
5. **Delete old Helm-based deployment** (optional)

## Related Documentation

- [llm-d Official Docs](https://llm-d.ai/)
- [KServe LLMInferenceService](https://github.com/opendatahub-io/kserve/tree/release-v0.15)
- [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/)
- [Istio Gateway API](https://istio.io/latest/docs/tasks/traffic-management/ingress/gateway-api/)
- [GKE TPU Documentation](https://cloud.google.com/kubernetes-engine/docs/how-to/tpus)
- [vLLM Documentation](https://docs.vllm.ai/)

## References

- **llm-d-infra-xks:** https://github.com/aneeshkp/llm-d-infra-xks
- **cert-manager-operator-chart:** https://github.com/aneeshkp/cert-manager-operator-chart
- **sail-operator-chart:** https://github.com/aneeshkp/sail-operator-chart
- **KServe:** https://github.com/opendatahub-io/kserve
- **Current Pattern 1 Guide:** [llm-d-pattern1-tpu-setup.md](./llm-d-pattern1-tpu-setup.md)
