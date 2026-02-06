# Pattern 1 Deployment Session - 2026-02-06

## Cluster Configuration

### New Cluster Details
- **Name:** `istio-kserve-pattern1`
- **Zone:** `europe-west4-a`
- **Project:** `ecoeng-llmd`
- **Creation Time:** 2026-02-06 ~15:15 UTC

### Node Pools

**Standard Pool (Control Plane)**
- **Machine Type:** `n1-standard-4`
- **Initial Nodes:** 2
- **Autoscaling:** 1-3 nodes
- **Purpose:** Kubernetes control plane, operators, KServe controller, Gateway

**TPU v6e Pool**
- **Machine Type:** `ct6e-standard-4t`
- **TPU Type:** TPU v6e (4 chips, 2x2 topology)
- **Initial Nodes:** 0
- **Autoscaling:** 0-2 nodes
- **Purpose:** vLLM inference workloads

## Deployment Plan

### Phase 1: Infrastructure Operators
**Repository:** https://github.com/aneeshkp/llm-d-infra-xks

**Components:**
1. **cert-manager-operator** - Certificate management
2. **sail-operator** - Istio/OSSM 3.1.x (InferencePool v1alpha2 compatible)

**Configuration:**
```yaml
useSystemPodmanAuth: true
pullSecretFile: "/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml"

certManager:
  enabled: true

sailOperator:
  enabled: true
  istioVersion: "v1.26.6"  # OSSM 3.1.x

lwsOperator:
  enabled: false  # Pattern 1 doesn't need LWS
```

### Phase 2: KServe Controller
**Repository:** `/home/jhull/devel/kserve` (release-v0.15)

**Overlay:** `config/overlays/odh-xks`
- Fixed with vars section (KUSTOMIZE-FIX.md)
- Requires kustomize v5.8.0+

**Namespace:** `opendatahub`

**Key Features:**
- LLMInferenceService controller enabled
- Standard InferenceService controller disabled
- Gateway API routing (not Istio VirtualService)
- cert-manager TLS (not OpenShift service-ca)

### Phase 3: Gateway Setup
**Script:** `~/llm-d-infra-xks/scripts/setup-gateway.sh`

**Creates:**
- Gateway resource in opendatahub namespace
- Istio Ingress Gateway deployment
- CA bundle mount for mTLS

### Phase 4: Application Namespace
**Namespace:** `llm-d-inference-scheduling`

**Secrets:**
1. **redhat-pull-secret** - From `/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`
2. **hf-token** - HuggingFace token: `YOUR_HUGGINGFACE_TOKEN`

### Phase 5: LLMInferenceService Deployment
**Model:** Qwen/Qwen2.5-3B-Instruct
**Image:** registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5
**Replicas:** 1 (Pattern 1 baseline)

**TPU Configuration:**
```yaml
resources:
  limits:
    google.com/tpu: "4"
  requests:
    google.com/tpu: "4"

env:
- name: TPU_CHIPS_PER_HOST_BOUNDS
  value: "2,2,1"  # 2x2 topology
- name: TPU_HOST_BOUNDS
  value: "1,1,1"
- name: PJRT_DEVICE
  value: "TPU"
```

**Router Configuration:**
```yaml
router:
  route: {}      # Auto-create HTTPRoute
  gateway: {}    # Bind to Gateway
  scheduler: {}  # Enable EPP scheduler
```

## Credentials

### Red Hat Registry
- **File:** `/home/jhull/devel/11009103-jhull-svc-pull-secret.yaml`
- **Account:** `11009103|jhull-svc`

### HuggingFace
- **Token:** `YOUR_HUGGINGFACE_TOKEN`
- **Source:** `/home/jhull/devel/tokens.txt`

## Key Differences from Previous Attempts

### Fixed Issues
1. ✅ Kustomize v5.8.0 installed (fixes segfault bug)
2. ✅ odh-xks overlay has vars section restored
3. ✅ Using correct credentials from /home/jhull/devel

### New Approach
- Fresh cluster (not reusing tpu-test-cluster)
- Following istio-kserve-llmd-architecture.md exactly
- Using KServe LLMInferenceService (not Helm charts)

## Expected Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Cluster creation | 5-10 min | ⏳ In Progress |
| TPU node pool | 2-3 min | Pending |
| Operator deployment | 3-5 min | Pending |
| KServe controller | 2-3 min | Pending |
| Gateway setup | 1-2 min | Pending |
| Namespace + secrets | 1 min | Pending |
| LLMInferenceService | 5-7 min | Pending |
| **Total** | **~20-30 min** | |

## Verification Steps

1. Check operators running
2. Verify KServe controller logs show LLM controller enabled
3. Confirm Gateway has external IP
4. Test inference with curl
5. Verify InferencePool and HTTPRoute auto-created
6. Check EPP scheduler routing metrics

## Related Documentation

- [istio-kserve-llmd-architecture.md](./istio-kserve-llmd-architecture.md) - Full architecture
- [KUSTOMIZE-FIX.md](./KUSTOMIZE-FIX.md) - odh-xks overlay fix details
- [ISSUES-istio.md](./ISSUES-istio.md) - Historical troubleshooting
