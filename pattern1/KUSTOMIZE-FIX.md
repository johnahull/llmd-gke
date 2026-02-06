# KServe odh-xks Overlay Kustomize Fix

## Problem Summary

The KServe `config/overlays/odh-xks` overlay was crashing with a segmentation fault when building with kustomize v5.5.0 and v5.6.0 (including kubectl's embedded kustomize).

```
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x40 pc=0x97fde5]
```

## Root Cause Analysis

### Initial Hypothesis (Incorrect)
Initially suspected the issue was due to missing `vars:` section in the kustomization.yaml file, which prevented variable substitution for values like `$(NAMESPACE)`, `$(ISSUER_REF_GROUP)`, etc.

### Actual Root Cause (Discovered)
The segfault was caused by **a bug in kustomize v5.5.0-v5.7.x** in the `RNode.Content()` method:

**File:** `kyaml/yaml/rnode.go:720-724`

**Buggy code (v5.5.0-v5.7.x):**
```go
func (rn *RNode) Content() []*yaml.Node {
    if rn == nil {
        return nil
    }
    return rn.YNode().Content  // <-- Bug: YNode() can return nil
}
```

**Problem:** When processing `$patch: delete` patches, kustomize tries to match resources. If `YNode()` returns nil (resource not found or partially resolved), calling `.Content` on nil causes a segfault.

**Fixed code (v5.8.0):**
```go
func (rn *RNode) Content() []*yaml.Node {
    yNode := rn.YNode()
    if yNode == nil {
        return nil
    }
    return yNode.Content
}
```

**Fix commit:** [87617912b](https://github.com/kubernetes-sigs/kustomize/commit/87617912bf172c6e03097683e47b07fac72cde8d)
**Fixed in:** kustomize v5.8.0 (released November 9, 2025)

### Why It Happened
The odh-xks overlay uses `$patch: delete` to remove resources like:
- `clusterservingruntime.serving.kserve.io` ValidatingWebhookConfiguration
- Various CRDs not needed in GKE environments

These patches failed to match resources (because they exist as patches in the base, not full resources), causing kustomize to process nil RNodes, which triggered the segfault.

## Solution Implemented

### Step 1: Upgrade to Kustomize v5.8.0
```bash
# Download and install kustomize v5.8.0
curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.8.0/kustomize_v5.8.0_linux_amd64.tar.gz" | tar xz -C ~/.local/bin/

# Verify installation
kustomize version
# Output: v5.8.0

# Add to PATH (if not already)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Step 2: Fix the odh-xks Overlay
Even with v5.8.0, the overlay was incomplete - it had `configMapGenerator` and `configurations` sections but was missing the `vars:` section needed to perform variable substitution.

**Changes made to `/home/jhull/devel/kserve/config/overlays/odh-xks/kustomization.yaml`:**

#### 2a. Added vars section (lines 62-112)
```yaml
# Define variables for substitution
vars:
- name: NAMESPACE
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.NAMESPACE
- name: ISSUER_REF_GROUP
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.ISSUER_REF_GROUP
- name: ISSUER_REF_KIND
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.ISSUER_REF_KIND
- name: ISSUER_REF_NAME
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.ISSUER_REF_NAME
- name: CA_SECRET_NAME
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.CA_SECRET_NAME
- name: CA_SECRET_NAMESPACE
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.CA_SECRET_NAMESPACE
- name: ISTIO_CA_CERTIFICATE_PATH
  objref:
    apiVersion: v1
    kind: ConfigMap
    name: odh-xks-kserve-parameters
  fieldref:
    fieldpath: data.ISTIO_CA_CERTIFICATE_PATH
```

#### 2b. Updated inline patches to use variables (lines 42, 51)
Changed hardcoded namespace values to use `$(NAMESPACE)` variable:

**Before:**
```yaml
- target:
    kind: ValidatingWebhookConfiguration
    name: llminferenceservice.serving.kserve.io
  patch: |
    - op: add
      path: /metadata/annotations/cert-manager.io~1inject-ca-from
      value: opendatahub/kserve-webhook-server
```

**After:**
```yaml
- target:
    kind: ValidatingWebhookConfiguration
    name: llminferenceservice.serving.kserve.io
  patch: |
    - op: add
      path: /metadata/annotations/cert-manager.io~1inject-ca-from
      value: "$(NAMESPACE)/kserve-webhook-server"
```

Same change applied to the second ValidatingWebhookConfiguration patch for `llminferenceserviceconfig.serving.kserve.io`.

## Verification

### Test 1: Overlay builds successfully
```bash
cd /home/jhull/devel/kserve
kustomize build config/overlays/odh-xks > /tmp/odh-xks-output.yaml
echo $?
# Output: 0 (success)
```

### Test 2: All variables substituted
```bash
grep '\$(NAMESPACE)\|\$(ISSUER_REF\|\$(CA_SECRET\|\$(ISTIO_CA' /tmp/odh-xks-output.yaml
# Output: (empty - no unsubstituted variables)
```

### Test 3: Verify substituted values
```bash
# Certificate should use opendatahub namespace
grep -A5 "kind: Certificate" /tmp/odh-xks-output.yaml | grep commonName
# Output: commonName: kserve-webhook-server-service.opendatahub.svc

# Webhook annotations should reference opendatahub namespace
grep "cert-manager.io/inject-ca-from:" /tmp/odh-xks-output.yaml
# Output: cert-manager.io/inject-ca-from: opendatahub/kserve-webhook-server

# IssuerRef should use cert-manager.io ClusterIssuer
grep -A3 "issuerRef:" /tmp/odh-xks-output.yaml
# Output:
#   issuerRef:
#     group: cert-manager.io
#     kind: ClusterIssuer
#     name: opendatahub-ca-issuer
```

### Test 4: Critical components present
```bash
# LLMInferenceService CRD exists
grep -c "name: llminferenceservices.serving.kserve.io" /tmp/odh-xks-output.yaml
# Output: 1

# KServe controller deployment exists
grep -c "name: kserve-controller-manager" /tmp/odh-xks-output.yaml
# Output: 11

# LLM controller enabled
grep -c "ENABLE_LLMISVC_CONTROLLER" /tmp/odh-xks-output.yaml
# Output: 1

# InferencePool permissions granted
grep -c "inferencepools" /tmp/odh-xks-output.yaml
# Output: 6
```

## Timeline of Investigation

1. **Initial Problem**: Segfault when running `kustomize build` on odh-xks overlay
2. **Hypothesis 1**: Missing `vars` section causing kustomize to fail
3. **Discovery**: Even the reference "fixed" overlay (`odh-xks-fixed`) was segfaulting
4. **Key Finding**: All overlays (odh, odh-xks, odh-xks-fixed) segfaulted with v5.5.0
5. **Isolation**: Created minimal test overlay - found `$patch: delete` triggered the segfault
6. **Source Analysis**: Cloned kustomize repo, analyzed source code
7. **Bug Found**: Located nil pointer dereference bug in `RNode.Content()` method
8. **Fix Identified**: Bug fixed in commit 87617912b, released in v5.8.0
9. **Solution**: Upgraded to v5.8.0 + added missing vars section
10. **Verification**: All tests passing, overlay builds successfully

## Files Modified

### /home/jhull/devel/kserve/config/overlays/odh-xks/kustomization.yaml
- **Lines 62-112**: Added complete `vars:` section with 7 variable definitions
- **Line 42**: Changed `opendatahub/kserve-webhook-server` → `"$(NAMESPACE)/kserve-webhook-server"`
- **Line 51**: Changed `opendatahub/kserve-webhook-server` → `"$(NAMESPACE)/kserve-webhook-server"`

### System Installation
- **Installed**: kustomize v5.8.0 to `~/.local/bin/kustomize`
- **Updated**: `~/.bashrc` to include `~/.local/bin` in PATH

## Related Issues

- **Upstream Bug**: https://github.com/kubernetes-sigs/kustomize/pull/5985
- **KServe Repository**: https://github.com/opendatahub-io/kserve
- **Affected Versions**: kustomize v5.0.0 - v5.7.1
- **Fixed Version**: kustomize v5.8.0+

## Recommendations

1. **Always use kustomize v5.8.0 or later** for building KServe overlays
2. **kubectl users**: Note that kubectl v1.33.3 bundles kustomize v5.6.0 (affected by bug)
   - Use standalone kustomize v5.8.0 instead of `kubectl kustomize`
3. **CI/CD pipelines**: Pin kustomize version to v5.8.0+ to avoid segfaults
4. **Upstream contribution**: Consider submitting this fix as a PR to opendatahub-io/kserve

## Next Steps for Deployment

With the odh-xks overlay now working, you can proceed with Pattern 1 deployment:

```bash
# Build the overlay
kustomize build /home/jhull/devel/kserve/config/overlays/odh-xks > kserve-gke-llm.yaml

# Deploy to GKE cluster
kubectl apply -f kserve-gke-llm.yaml

# Verify deployment
kubectl get deployment kserve-controller-manager -n opendatahub
kubectl logs -n opendatahub deployment/kserve-controller-manager | grep "LLMInferenceService controller"
```

See `llm-d-pattern1-gpu-setup.md` for complete deployment instructions.
