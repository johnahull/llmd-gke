# Pattern 1 Istio + KServe + llm-d Deployment Issues

## Deployment Session: 2026-02-05

### Issues Encountered

#### 1. Manifest Configuration Errors (Fixed)

**Issue:** Initial manifest had incorrect secret references and health probe schemes
- Secret name mismatch: `hf-token` vs actual `huggingface-token`
- Pull secret mismatch: `redhat-pull-secret` vs actual `11009103-jhull-svc-pull-secret`
- Health probes using `HTTPS` instead of `HTTP` (vLLM standard)

**Resolution:** Fixed in `llmisvc-pattern1-tpu.yaml` before deployment
- Updated secret references to match actual secret names
- Changed health probe schemes from HTTPS to HTTP

**Files Modified:**
- `pattern1/manifests/llmisvc-pattern1-tpu.yaml:43` - HF token secret name
- `pattern1/manifests/llmisvc-pattern1-tpu.yaml:80` - Pull secret name
- `pattern1/manifests/llmisvc-pattern1-tpu.yaml:58,68` - Health probe schemes

---

## Deployment Deviations from Plan

### Phase 1: Cluster Creation

**Deviation 1: Cluster Name Change**
- **Plan:** Create cluster named `tpu-test-cluster`
- **Actual:** Created cluster named `istio-kserve-cluster`
- **Reason:** Cluster `tpu-test-cluster` already existed in the project
- **Impact:** None - just a naming difference

**Deviation 2: Gateway API CRD Installation**
- **Plan:** Install Gateway API CRDs using experimental bundle
  ```bash
  kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/experimental-install.yaml
  ```
- **Actual:** GKE 1.35 already has standard Gateway API CRDs installed
- **Issue:** GKE 1.35 enforces ValidatingAdmissionPolicy that blocks experimental CRDs
  ```
  Error: All Gateway API CRDs must belong to the 'standard' channel.
  Experimental CRDs are not permitted.
  ```
- **Resolution:**
  - Standard Gateway API CRDs already present (GatewayClass, Gateway, HTTPRoute, etc.)
  - Installed only InferencePool CRDs from Gateway API Inference Extension v1.0.0
  ```bash
  kubectl apply -f https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.0.0/manifests.yaml
  ```
- **Impact:** No functional impact - all required CRDs are available

**Verification:**
```bash
# Gateway API CRDs (pre-installed by GKE)
kubectl get crd | grep gateway
# Output: backendtlspolicies, gatewayclasses, gateways, httproutes, referencegrants

# InferencePool CRDs (manually installed)
kubectl api-resources --api-group=inference.networking.x-k8s.io
# Output: inferenceobjectives, inferencepools
```

## Known Issues

### Phase 3: KServe Deployment - ✅ RESOLVED

**Issue: kubectl kustomize crash on odh-xks overlay**
- **Error:** Segmentation fault when processing `config/overlays/odh-xks`
  ```
  panic: runtime error: invalid memory address or nil pointer dereference
  ```
- **Initial Root Cause Hypothesis:** Missing `vars` section in kustomization.yaml
- **Actual Root Cause:** Bug in kustomize v5.5.0-v5.7.x in `RNode.Content()` method
  - Nil pointer dereference when processing `$patch: delete` patches
  - Fixed in kustomize v5.8.0 (commit 87617912b, released November 9, 2025)

**Resolution:**
1. **Upgraded to kustomize v5.8.0**
   ```bash
   curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.8.0/kustomize_v5.8.0_linux_amd64.tar.gz" | tar xz -C ~/.local/bin/
   ```
2. **Fixed odh-xks overlay** - Added missing `vars:` section to `/home/jhull/devel/kserve/config/overlays/odh-xks/kustomization.yaml`
   - Lines 62-112: Added 7 variable definitions (NAMESPACE, ISSUER_REF_*, CA_SECRET_*, ISTIO_CA_CERTIFICATE_PATH)
   - Lines 42, 51: Updated inline patches to use `$(NAMESPACE)` instead of hardcoded `opendatahub`
3. **Verification:** Overlay builds successfully with all variables properly substituted

**Status:** ✅ RESOLVED - See [KUSTOMIZE-FIX.md](./KUSTOMIZE-FIX.md) for complete analysis and fix details

**Warnings (informational only):**
  ```
  Warning: 'vars' is deprecated. Please use 'replacements' instead.
  Warning: 'commonLabels' is deprecated. Please use 'replacements' instead.
  ```

---

### Historical Context: Manual Deployment Workaround (No Longer Needed)

**Note:** The following workaround was used before the kustomize issue was fixed. With kustomize v5.8.0 and the fixed overlay, you can now use `kustomize build config/overlays/odh-xks` directly.

<details>
<summary>Click to view historical manual deployment steps</summary>

Before the kustomize fix was implemented, we used the standard KServe v0.15.2 manifest with manual patches:

```bash
# Deploy standard KServe
kubectl apply -f /home/jhull/devel/kserve/install/v0.15.2/kserve.yaml --server-side

# Add LLM-specific CRDs
kubectl apply -f /home/jhull/devel/kserve/config/crd/full/serving.kserve.io_llminferenceserviceconfigs.yaml --server-side
kubectl apply -f /home/jhull/devel/kserve/config/crd/full/serving.kserve.io_llminferenceservices.yaml --server-side

# Add LLM templates
for f in /home/jhull/devel/kserve/config/llmisvc/config-*.yaml; do
  kubectl apply -f "$f" --server-side
done

# Apply pull secret
kubectl apply -f /home/jhull/devel/11009103-jhull-svc-pull-secret.yaml -n kserve

# Enable LLM controller
kubectl patch deployment kserve-controller-manager -n kserve --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "ENABLE_LLMISVC_CONTROLLER", "value": "true"}}
]'

# Configure Gateway API
kubectl patch configmap inferenceservice-config -n kserve --type='json' -p='[
  {"op": "replace", "path": "/data/ingress", "value": "{\n    \"enableGatewayApi\": true,\n    \"kserveIngressGateway\": \"opendatahub/inference-gateway\",\n    \"ingressClassName\": \"istio\",\n    \"ingressDomain\": \"example.com\"\n}"}
]'
```

**Result:** KServe controller deployed successfully in `kserve` namespace (not `opendatahub` as originally planned).

---

### Phase 3 (Continued): Standard Manifest Deployment Issues

After using the standard manifest workaround, discovered multiple critical issues:

#### Issue 1: Wrong Controller Image
- **Problem:** Standard manifest uses upstream KServe image `kserve/kserve-controller:v0.15.2`
- **Root Cause:** Upstream KServe does NOT include LLMInferenceService controller - this is an OpenDataHub extension
- **Symptom:** Controller logs showed no "Setting up LLMInferenceService controller" message
- **Fix:** Changed image to `quay.io/opendatahub/kserve-controller:v0.15-latest`
- **Verification:** After image change, logs showed "Setting up LLMInferenceService controller"

#### Issue 2: Missing RBAC Permissions
After switching to OpenDataHub controller image, discovered extensive missing permissions:

**Missing ClusterRole permissions for `kserve-manager-role`:**
- LLMInferenceService resources (list, create, update, delete, watch)
- LLMInferenceServiceConfig resources (list, create, update, delete, watch)
- InferencePool resources (list, create, update, delete, watch)
- Gateway API resources (gateways, httproutes)
- Istio resources (destinationrules, virtualservices)
- Secrets (create, delete, patch, update - only had get, list, watch)

**Error Messages:**
```
failed to list *v1alpha1.LLMInferenceService: llminferenceservices.serving.kserve.io is forbidden
failed to list *v1alpha2.InferencePool: inferencepools.inference.networking.x-k8s.io is forbidden
failed to create v1.Secret: secrets is forbidden
```

**Fix Applied:**
```bash
kubectl patch clusterrole kserve-manager-role --type='json' -p='[
  # Add LLM resources
  {"op": "add", "path": "/rules/-", "value": {
    "apiGroups": ["serving.kserve.io"],
    "resources": ["llminferenceservices", "llminferenceserviceconfigs"],
    "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]
  }},
  # Add InferencePool
  {"op": "add", "path": "/rules/-", "value": {
    "apiGroups": ["inference.networking.x-k8s.io"],
    "resources": ["inferencepools", "inferencemodels", "inferenceobjectives"],
    "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]
  }},
  # Add Gateway API
  {"op": "add", "path": "/rules/-", "value": {
    "apiGroups": ["gateway.networking.k8s.io"],
    "resources": ["gateways", "httproutes"],
    "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]
  }},
  # Add Istio
  {"op": "add", "path": "/rules/-", "value": {
    "apiGroups": ["networking.istio.io"],
    "resources": ["destinationrules", "virtualservices"],
    "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]
  }},
  # Extend secret permissions
  {"op": "add", "path": "/rules/-", "value": {
    "apiGroups": [""],
    "resources": ["secrets"],
    "verbs": ["create", "delete", "patch", "update"]
  }}
]'
```

#### Issue 3: Missing Environment Variables
Standard manifest missing critical ODH-specific environment variables:

**Required env vars from odh-xks overlay:**
```yaml
- ENABLE_ISVC_CONTROLLER: "false"           # Disable standard InferenceService controller
- ENABLE_LLMISVC_CONTROLLER: "true"         # Enable LLM controller
- ENABLE_TRAINED_MODEL_CONTROLLER: "false"  # Disable TrainedModel controller
- ENABLE_INFERENCE_GRAPH_CONTROLLER: "false" # Disable InferenceGraph controller
- LLMISVC_AUTH_DISABLED: "true"             # Disable Kuadrant/RHCL auth
- LLMISVC_MONITORING_DISABLED: "true"       # Disable Prometheus Operator
- LLMISVC_SCC_DISABLED: "true"              # Disable OpenShift SCC
- SERVICE_CA_SIGNING_SECRET_NAME: "opendatahub-ca"
- SERVICE_CA_SIGNING_SECRET_NAMESPACE: "cert-manager"
- ISTIO_CA_CERTIFICATE_PATH: "/var/run/secrets/opendatahub/ca.crt"
```

**Symptom:** Standard InferenceService controller was running alongside LLM controller, causing conflicts

**Fix Applied:**
```bash
kubectl patch deployment kserve-controller-manager -n opendatahub --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "SERVICE_CA_SIGNING_SECRET_NAME", "value": "opendatahub-ca"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "SERVICE_CA_SIGNING_SECRET_NAMESPACE", "value": "cert-manager"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "ISTIO_CA_CERTIFICATE_PATH", "value": "/var/run/secrets/opendatahub/ca.crt"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "ENABLE_ISVC_CONTROLLER", "value": "false"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "ENABLE_TRAINED_MODEL_CONTROLLER", "value": "false"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "ENABLE_INFERENCE_GRAPH_CONTROLLER", "value": "false"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "LLMISVC_AUTH_DISABLED", "value": "true"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "LLMISVC_MONITORING_DISABLED", "value": "true"}},
  {"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "LLMISVC_SCC_DISABLED", "value": "true"}}
]'
```

</details>

---

### Investigation Completed ✅

**Previous Status:** The odh-xks kustomize overlay was segfaulting due to a kustomize bug.

**Current Status:** Issue resolved - see resolution above and [KUSTOMIZE-FIX.md](./KUSTOMIZE-FIX.md) for details.

**Historical Context - Why Standard Manifest Approach Was Insufficient:**
1. **Image version mismatch** - Standard manifest uses wrong image
2. **Missing RBAC** - Extensive manual patching required (error-prone)
3. **Missing environment variables** - 10+ critical env vars need manual addition
4. **Namespace inconsistency** - Standard manifest deploys to `kserve`, overlay expects `opendatahub`
5. **No ingress configuration** - Gateway API settings missing from inferenceservice-config

**Recommended Investigation Path:**
1. Fix the kustomize overlay's `vars` → `replacements` migration
2. Test with kustomize v5.x after fixing vars
3. Validate all RBAC, env vars, and configurations are correctly applied
4. Document any additional manual steps required

**Files to Investigate:**
- `/home/jhull/devel/kserve/config/overlays/odh-xks/kustomization.yaml` - Fix vars → replacements
- `/home/jhull/devel/kserve/config/overlays/odh/kustomization.yaml` - Parent overlay (also uses vars)
- `/home/jhull/devel/kserve/config/overlays/odh-xks/params.env` - Image and parameter definitions

---

## References

- [vLLM Model-Aware Readiness Probes](https://llm-d.ai/docs/usage/readiness-probes)
- [vLLM KServe Integration](https://docs.vllm.ai/en/latest/deployment/integrations/kserve.html)
- [Using Kubernetes - vLLM](https://docs.vllm.ai/en/stable/deployment/k8s/)
