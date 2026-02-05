# GKE BBR Deployment with Helm

**Status:** ✅ Official GKE deployment method for Body-Based Routing

**Last Updated:** 2026-02-04

---

## Overview

Google Cloud provides an official Helm chart for deploying Body-Based Router (BBR) as part of the GKE Inference Gateway ecosystem. BBR extracts model names from request bodies and injects them as HTTP headers for intelligent multi-model routing.

**What BBR Does:**
- Intercepts inference requests at the Gateway
- Parses JSON body to extract the `model` field
- Injects `X-Gateway-Base-Model-Name` header
- Enables HTTPRoute to route based on model name

**Deployment Benefits:**
- ✅ Single `helm install` command deployment
- ✅ Automated RBAC and health check configuration
- ✅ Version management with Helm releases
- ✅ Easy upgrades and rollbacks
- ✅ Official GKE support

---

## Prerequisites

### 1. Cluster Requirements

- **GKE Version:** 1.32 or later
- **Gateway API:** v1.3.0 installed (from Pattern 1)
- **Inference Extension CRDs:** Installed (InferencePool v1)
- **Existing Gateway:** Deployed and ready (e.g., `infra-pattern2-inference-gateway`)

Verify prerequisites:
```bash
# Check GKE version
kubectl version --short

# Check Gateway API CRDs
kubectl get crd gateways.gateway.networking.k8s.io -o jsonpath='{.spec.versions[*].name}'
# Expected: v1

# Check Gateway exists
kubectl get gateway -n llm-d
# Expected: Your gateway name and external IP
```

### 2. Helm Installation

Ensure Helm 3.x is installed:
```bash
helm version --short
# Expected: v3.x.x
```

### 3. Namespace and Gateway Context

Set environment variables for your deployment:
```bash
# For GPU deployments
export NAMESPACE="llm-d"
export GATEWAY_NAME="infra-pattern2-inference-gateway"

# For TPU deployments
export NAMESPACE="llm-d-inference-scheduling"
export GATEWAY_NAME="infra-pattern1-inference-gateway"
```

---

## Deployment Steps

### Step 1: Install BBR via Helm

Deploy BBR using the official GKE Helm chart:

```bash
helm install body-based-router \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing \
  --namespace $NAMESPACE \
  --set provider.name=gke \
  --set inferenceGateway.name=$GATEWAY_NAME
```

**What This Creates:**
- ✅ ServiceAccount with proper RBAC permissions
- ✅ Deployment running the BBR container
- ✅ Service exposing BBR on ports 9004 (ext-proc) and 9005 (health)
- ✅ `GCPRoutingExtension` linking BBR to your Gateway
- ✅ `GCPHealthCheckPolicy` for GKE load balancer health checks

**Expected Output:**
```
NAME: body-based-router
LAST DEPLOYED: [timestamp]
NAMESPACE: llm-d
STATUS: deployed
REVISION: 1
```

### Step 2: Verify BBR Deployment

Wait for BBR pod to become ready:
```bash
kubectl wait --for=condition=Ready pod \
  -l app.kubernetes.io/name=body-based-routing \
  -n $NAMESPACE \
  --timeout=120s
```

Check pod status:
```bash
kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing

# Expected output:
# NAME                                READY   STATUS    RESTARTS   AGE
# body-based-routing-xxxxxxxxx-xxxxx  1/1     Running   0          30s
```

Verify service:
```bash
kubectl get svc body-based-routing -n $NAMESPACE

# Expected: ClusterIP service with ports 9004 and 9005
```

### Step 3: Verify GCPRoutingExtension Accepted

Check that your Gateway has accepted the routing extension:

```bash
kubectl get gateway $GATEWAY_NAME -n $NAMESPACE -o yaml | grep -A10 "conditions:"
```

**Expected:** Look for `PROGRAMMED=True` status (may take 30-90 seconds)

**Troubleshooting:** If Gateway shows `PROGRAMMED=False`, check extension logs:
```bash
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing --tail=50
```

### Step 4: Create Model Allowlist ConfigMaps

**Critical:** BBR requires allowlist ConfigMaps to map model names to base model identifiers.

**For TPU (Qwen + Phi-3):**
```bash
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

**For GPU (Gemma + Phi-3):**
```bash
kubectl apply -f - <<EOF
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: gemma-allowlist
  namespace: $NAMESPACE
  labels:
    inference.networking.k8s.io/bbr-managed: "true"
data:
  baseModel: "google/gemma-2b-it"
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

**Verify BBR Reconciliation:**
```bash
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing --tail=20 | grep "Reconciling"
```

**Expected:**
```
Reconciling ConfigMap qwen-allowlist
Reconcile successful
Reconciling ConfigMap phi-allowlist
Reconcile successful
```

### Step 5: Deploy InferencePools and HTTPRoutes

Apply your model-specific InferencePools and header-based HTTPRoutes:

**For TPU:**
```bash
kubectl apply -f pattern2/manifests/inferencepools-bbr.yaml -n $NAMESPACE
kubectl apply -f pattern2/manifests/httproutes-bbr.yaml -n $NAMESPACE
kubectl apply -f pattern2/manifests/healthcheck-policy-fixed.yaml -n $NAMESPACE
```

**For GPU:**
```bash
kubectl apply -f pattern2/manifests/pattern2-bbr-gpu-working.yaml -n $NAMESPACE
kubectl apply -f pattern2/manifests/healthcheck-policies-gpu.yaml -n $NAMESPACE
```

Wait 2-3 minutes for GKE load balancer health checks to propagate.

### Step 6: Test Multi-Model Routing

Get the Gateway IP:
```bash
GATEWAY_IP=$(kubectl get gateway $GATEWAY_NAME -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')
echo "Gateway IP: $GATEWAY_IP"
```

Test both models:
```bash
# Test Model 1 (Qwen or Gemma depending on deployment)
curl -X POST http://$GATEWAY_IP/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is machine learning?",
    "max_tokens": 20
  }'

# Test Model 2 (Phi-3)
curl -X POST http://$GATEWAY_IP/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "prompt": "What is machine learning?",
    "max_tokens": 20
  }'
```

**Expected:** Both requests return HTTP 200 with model-specific responses.

---

## Verification

### Check BBR Header Injection

View BBR logs to confirm header injection:
```bash
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing --tail=30 | grep "Response generated"
```

**Expected Output:**
```
Response generated: "request_headers:{response:{header_mutation:{set_headers:{header:{key:\"X-Gateway-Model-Name\"  raw_value:\"Qwen/Qwen2.5-3B-Instruct\"}}  set_headers:{header:{key:\"X-Gateway-Base-Model-Name\"  raw_value:\"Qwen/Qwen2.5-3B-Instruct\"}}}  clear_route_cache:true}}"
```

**Key Indicators:**
- ✅ `X-Gateway-Model-Name` header present
- ✅ `X-Gateway-Base-Model-Name` header has `raw_value` populated (from allowlist)
- ✅ `clear_route_cache:true` forces HTTPRoute re-evaluation

### Check HTTPRoute Status

```bash
kubectl get httproute -n $NAMESPACE -o wide
```

**Expected:** All routes show `Accepted=True, ResolvedRefs=True, Reconciled=True`

### Check InferencePool Endpoints

```bash
kubectl get inferencepool -n $NAMESPACE -o yaml | grep -A10 "status:"
```

**Expected:** Each pool shows backend endpoint IPs

---

## Helm Chart Configuration Options

### View Default Values

```bash
helm show values oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing
```

### Custom Values File (Advanced)

Create a `values.yaml` file for advanced configuration:

```yaml
# values.yaml
provider:
  name: gke

inferenceGateway:
  name: infra-pattern2-inference-gateway

# Optional: Custom resource limits
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

# Optional: Replica count for high availability
replicaCount: 2

# Optional: Custom logging verbosity
args:
  - --streaming
  - --v
  - "5"
```

Install with custom values:
```bash
helm install body-based-router \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing \
  --namespace $NAMESPACE \
  -f values.yaml
```

---

## Lifecycle Management

### Upgrade BBR

```bash
helm upgrade body-based-router \
  oci://registry.k8s.io/gateway-api-inference-extension/charts/body-based-routing \
  --namespace $NAMESPACE \
  --set provider.name=gke \
  --set inferenceGateway.name=$GATEWAY_NAME \
  --reuse-values
```

### Check Deployment Status

```bash
helm status body-based-router -n $NAMESPACE
```

### Rollback to Previous Version

```bash
helm rollback body-based-router -n $NAMESPACE
```

### Uninstall BBR

```bash
helm uninstall body-based-router -n $NAMESPACE
```

**Note:** This removes all BBR resources including ServiceAccount, Deployment, Service, and GCPRoutingExtension.

---

## Troubleshooting

### Issue: BBR Pod CrashLoopBackOff

**Diagnosis:**
```bash
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing
```

**Common Causes:**
1. Missing RBAC permissions (Helm should auto-configure, but verify)
2. Gateway not found (check `inferenceGateway.name` value)

**Solution:** Verify Gateway exists and redeploy:
```bash
kubectl get gateway $GATEWAY_NAME -n $NAMESPACE
helm upgrade body-based-router [same install command] --reuse-values
```

### Issue: Gateway PROGRAMMED=False

**Diagnosis:**
```bash
kubectl describe gateway $GATEWAY_NAME -n $NAMESPACE | grep -A10 "Conditions:"
```

**Common Cause:** Service port missing `appProtocol: HTTP2`

**Solution:** Helm chart should configure this automatically. Verify:
```bash
kubectl get svc body-based-routing -n $NAMESPACE -o yaml | grep appProtocol
```

If missing, patch manually:
```bash
kubectl patch svc body-based-routing -n $NAMESPACE --type='json' \
  -p='[{"op":"add","path":"/spec/ports/0/appProtocol","value":"HTTP2"}]'
```

### Issue: Requests Return 404 "fault filter abort"

**Root Cause:** Missing allowlist ConfigMaps → BBR can't populate `X-Gateway-Base-Model-Name` header

**Diagnosis:**
```bash
kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=body-based-routing --tail=20 | grep "raw_value"
```

**If you see:**
```
set_headers:{header:{key:\"X-Gateway-Base-Model-Name\"}}  # ← NO raw_value!
```

**Solution:** Create allowlist ConfigMaps (see Step 4)

### Issue: Helm Install Fails with "OCI not found"

**Cause:** Helm version < 3.8 doesn't support OCI registries

**Solution:** Upgrade Helm:
```bash
# Check version
helm version --short

# Upgrade if needed (example for Linux)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

---

## References

**Official Documentation:**
- [GKE Body-Based Routing Configuration](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/configure-body-based-routing)
- [GKE Inference Gateway Overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-gke-inference-gateway)
- [Deploy GKE Inference Gateway](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/deploy-gke-inference-gateway)

**Related Pattern 2 Documentation:**
- [Pattern 2 TPU Setup Guide](./llm-d-pattern2-tpu-setup.md)
- [Pattern 2 GPU Setup Guide](./llm-d-pattern2-gpu-setup.md)
- [Pattern 2 Benchmark Results](./PATTERN2_BBR_BENCHMARK_RESULTS.md)

---

## Summary

✅ **Official GKE deployment method** - Helm-based BBR deployment
✅ **Simple deployment** - Single `helm install` command
✅ **100% routing accuracy** - Header-based model routing
✅ **Automated configuration** - RBAC, health checks, extensions
✅ **Easy lifecycle management** - Upgrades, rollbacks, version tracking

**Next Steps:**
1. Deploy BBR via Helm (10 minutes)
2. Create allowlist ConfigMaps for your models
3. Deploy InferencePools and HTTPRoutes
4. Test multi-model routing
5. Monitor and maintain with Helm commands
