# LLM Inference Deployment Guides

Production-grade LLM inference deployment documentation for Kubernetes with intelligent routing and operator-based infrastructure.

## 📚 Available Guides

### 1. GKE Inference Gateway + Istio Deployment
**File:** [`gke-inference-gateway-istio-deployment.md`](./gke-inference-gateway-istio-deployment.md)

**What it deploys:**
- GKE cluster with NVIDIA GPU support (T4)
- GKE Inference Gateway (Gateway API + Inference Extensions)
- Istio service mesh via sail-operator
- llm-d Pattern 1 (single-replica vLLM deployment)
- Intelligent routing with Endpoint Picker (EPP)

**Best for:**
- Google Cloud Platform (GKE) deployments
- Production LLM inference with intelligent routing
- GKE-native Gateway API integration
- Users wanting GKE's regional external Application Load Balancer

**Deployment Options:**
- **Option A:** Upstream operators (Jetstack, Istio, Kubernetes-SIGs)
- **Option B:** Red Hat operators via llm-d-infra-xks meta helmfile

**Time to deploy:** ~45 minutes

**Prerequisites:**
- GCP project with billing enabled
- `gcloud`, `kubectl`, `helm`, `helmfile`, `git`
- HuggingFace token
- (Optional) Red Hat pull secret for enterprise operators

---

### 2. Cloud-Agnostic LLM Deployment
**File:** [`cloud-agnostic-llm-deployment.md`](./cloud-agnostic-llm-deployment.md)

**What it deploys:**
- Kubernetes cluster with GPU support (works on GKE, EKS, AKS, OpenShift, vanilla K8s)
- Upstream cert-manager + Istio service mesh
- llm-d with intelligent routing
- Portable across all major cloud providers and on-premises

**Best for:**
- Multi-cloud deployments
- Cloud portability requirements
- Non-GKE Kubernetes distributions (EKS, AKS, OpenShift, etc.)
- Maximum flexibility and vendor independence

**Deployment Options:**
- **Option A:** Upstream operators (default)
- **Option B:** Red Hat operators via llm-d-infra-xks

**Time to deploy:** ~50 minutes

**Prerequisites:**
- Any Kubernetes cluster (1.28.0+)
- `kubectl`, `helm`, `helmfile`, `git`
- HuggingFace token
- (Optional) Red Hat pull secret

---

## 🤔 Which Guide Should I Use?

### Use **GKE Inference Gateway + Istio** if:
- ✅ You're deploying on Google Cloud Platform (GKE)
- ✅ You want GKE's native Gateway API integration
- ✅ You need GKE regional external Application Load Balancer
- ✅ You want the fastest path to production on GKE
- ✅ You're comfortable with GKE-specific features

### Use **Cloud-Agnostic Deployment** if:
- ✅ You're deploying on AWS (EKS), Azure (AKS), or other clouds
- ✅ You need multi-cloud portability
- ✅ You're running on OpenShift or vanilla Kubernetes
- ✅ You want to avoid cloud provider lock-in
- ✅ You need maximum flexibility across environments

### Both guides support:
- ✅ Upstream operators (community-supported, open-source)
- ✅ Red Hat operators (enterprise support, Red Hat subscription)
- ✅ llm-d intelligent routing with Endpoint Picker
- ✅ Production-grade LLM inference
- ✅ Multiple deployment patterns (Pattern 1, 2, 3)

---

## 🏗️ Deployment Approaches Comparison

Both guides offer two operator deployment approaches:

| Aspect | Upstream Operators | Red Hat Operators |
|--------|-------------------|-------------------|
| **Source** | Jetstack, Istio, Kubernetes-SIGs | registry.redhat.io |
| **Deployment** | Individual Helm charts | Single helmfile command |
| **Support** | Community | Red Hat Enterprise |
| **Cost** | Free | Red Hat subscription |
| **Portability** | Maximum | Maximum |
| **Best for** | Dev/test, flexibility | Production, enterprises |
| **Speed** | ~20 min (3 operators) | ~5 min (single command) |

**Architecturally identical:** Both result in the same functionality - the choice is about operational preference.

---

## 🚀 Quick Start Paths

### Path 1: GKE with Upstream Operators (Recommended for GKE users)
```bash
# Follow: gke-inference-gateway-istio-deployment.md
# Steps: 1 (GKE cluster) → 2-4 (operators) → 6 (Gateway) → 7 (llm-d)
# Time: ~45 minutes
```

### Path 2: GKE with Red Hat Operators (Fast deployment)
```bash
# Follow: gke-inference-gateway-istio-deployment.md
# Steps: 1 (GKE cluster) → 0 (Red Hat secret) → Quick deploy all operators → 6 (Gateway) → 7 (llm-d)
# Time: ~30 minutes
```

### Path 3: Cloud-Agnostic with Upstream Operators
```bash
# Follow: cloud-agnostic-llm-deployment.md
# Steps: Part 1 (cluster) → Part 2 (operators) → Part 3 (llm-d)
# Time: ~50 minutes
```

### Path 4: Cloud-Agnostic with Red Hat Operators
```bash
# Follow: cloud-agnostic-llm-deployment.md
# Steps: Part 1 (cluster) → Step 0 (Red Hat secret) → Quick deploy → Part 3 (llm-d)
# Time: ~35 minutes
```

---

## 📋 Common Prerequisites

Both guides require:

**Local Tools:**
- `kubectl` v1.28.0+
- `helm` v3.12.0+
- `helmfile` v1.1.0+
- `git` v2.30.0+

**Credentials:**
- HuggingFace token (https://huggingface.co/settings/tokens)
- (Optional) Red Hat pull secret (https://console.redhat.com/openshift/install/pull-secret)

**Cloud Access:**
- GKE: `gcloud` CLI + GCP project with `roles/container.admin`
- Other clouds: Appropriate CLI and permissions

---

## 🎯 Deployment Patterns Supported

Both guides support multiple llm-d patterns:

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **Pattern 1** | Single-replica baseline | Development, testing, single model |
| **Pattern 2** | Multi-model routing | Multiple models, intelligent routing |
| **Pattern 3** | N/S-caching scale-out | High throughput, 3+ replicas |
| **Pattern 4** | MoE multi-node | Mixture of Experts models |
| **Pattern 5** | P/D disaggregation | Prefill/Decode separation |

---

## 🔧 Post-Deployment

After deployment, both guides provide:
- ✅ Working inference API at `http://<GATEWAY-IP>/v1/completions`
- ✅ Intelligent routing with Endpoint Picker (EPP)
- ✅ OpenAI-compatible API endpoints
- ✅ Production-grade service mesh with Istio
- ✅ TLS certificate management with cert-manager

---

## 📖 Additional Resources

**llm-d Documentation:**
- Main site: https://llm-d.ai/
- GKE Provider Guide: https://llm-d.ai/docs/guide/InfraProviders/gke
- Gateway API Inference Extension: https://gateway-api-inference-extension.sigs.k8s.io/

**Red Hat Operators:**
- llm-d-infra-xks: https://github.com/aneeshkp/llm-d-infra-xks
- Individual operator charts available in aneeshkp GitHub org

**Google Cloud AI:**
- GKE AI Labs: https://gke-ai-labs.dev
- AI on GKE: https://github.com/ai-on-gke

---

## 🆘 Getting Help

**Troubleshooting:**
- Both guides include comprehensive troubleshooting sections
- Common issues: GPU detection, image pull, Gateway connectivity
- Verification steps provided at each checkpoint

**Community:**
- llm-d: GitHub issues and discussions
- GKE: Google Cloud support and community forums
- Red Hat: Red Hat support portal (with subscription)

---

## 📝 License

Documentation and configurations in this repository follow the repository's main license.

Red Hat operator images require appropriate Red Hat subscriptions for production use.
