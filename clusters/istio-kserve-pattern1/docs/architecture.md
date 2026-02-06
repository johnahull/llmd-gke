# Architecture - istio-kserve-pattern1

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Internet (Clients)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTPS (443) / HTTP (80)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Istio Ingress Gateway (LoadBalancer: 34.7.208.8)             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Listeners:                                                │ │
│  │  • HTTPS:443 (TLS Termination)                           │ │
│  │  • HTTP:80 (Backwards compat)                            │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         │ HTTP (internal, plaintext)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  HTTPRoute (auto-created by KServe)                            │
│  Path: /llm-d-inference-scheduling/qwen2-3b-pattern1/*         │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  InferencePool (llm-d Gateway API extension)                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ EPP Scheduler (Endpoint Picker)                          │ │
│  │  • Evaluates queue depth, KV cache, prefix cache        │ │
│  │  • Selects optimal vLLM endpoint                        │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  vLLM Pod (TPU v6e)                                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Container: registry.redhat.io/rhaiis/vllm-tpu-rhel9      │ │
│  │ Model: Qwen/Qwen2.5-3B-Instruct                          │ │
│  │ Accelerator: TPU v6e (4 chips, 2x2 topology)             │ │
│  │ API: OpenAI-compatible (port 8000)                       │ │
│  │ Backend: JAX/XLA                                         │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

## Component Inventory

### Infrastructure Layer

| Component | Type | Purpose | Namespace |
|-----------|------|---------|-----------|
| cert-manager | Operator | Certificate management | cert-manager |
| sail-operator | Operator | Istio lifecycle management | sail-operator |
| KServe | Controller | LLM serving orchestration | opendatahub |
| Calico | CNI plugin | NetworkPolicy enforcement | kube-system |

### Gateway Layer

| Component | Type | Purpose | Namespace |
|-----------|------|---------|-----------|
| inference-gateway | Gateway API | Traffic entry point | opendatahub |
| inference-gateway-istio | LoadBalancer Service | External IP | opendatahub |
| inference-gateway-tls | Certificate | TLS for HTTPS listener | opendatahub |

### Application Layer

| Component | Type | Purpose | Namespace |
|-----------|------|---------|-----------|
| qwen2-3b-pattern1 | LLMInferenceService | Declarative model deployment | llm-d-inference-scheduling |
| qwen2-3b-pattern1-kserve | Deployment | vLLM pod(s) | llm-d-inference-scheduling |
| qwen2-3b-pattern1-kserve-router-scheduler | Deployment | EPP scheduler | llm-d-inference-scheduling |
| qwen2-3b-pattern1-inference-pool | InferencePool | Endpoint discovery | llm-d-inference-scheduling |
| qwen2-3b-pattern1-kserve-route | HTTPRoute | Path-based routing | llm-d-inference-scheduling |

### Security Layer

| Component | Type | Purpose | Namespace |
|-----------|------|---------|-----------|
| default-deny-all | NetworkPolicy | Deny all traffic by default | llm-d-inference-scheduling |
| allow-gateway-to-vllm | NetworkPolicy | Allow Gateway → vLLM | llm-d-inference-scheduling |
| allow-vllm-egress | NetworkPolicy | Allow vLLM DNS/HTTPS egress | llm-d-inference-scheduling |

## Traffic Flow Details

### External Request Flow

1. **Client Request:**
   ```bash
   POST https://34.7.208.8/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions
   ```

2. **Gateway (TLS Termination):**
   - Terminates TLS (HTTPS → HTTP)
   - Matches HTTPRoute based on path prefix
   - Forwards to InferencePool backend

3. **HTTPRoute Matching:**
   ```yaml
   path: /llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions
   rewrite: /v1/chat/completions
   backend: InferencePool (qwen2-3b-pattern1-inference-pool)
   ```

4. **EPP Scheduler:**
   - Receives request from HTTPRoute
   - Queries all vLLM endpoints for metrics:
     - Queue depth (pending requests)
     - KV cache utilization
     - Prefix cache hit rate
   - Scores endpoints and selects optimal one
   - Forwards request to selected vLLM pod

5. **vLLM Pod:**
   - Receives inference request on port 8000
   - Processes with TPU v6e accelerator
   - Returns OpenAI-compatible response

### Internal Communication

```
Gateway Pod (opendatahub namespace)
    ↓ HTTP (allowed by NetworkPolicy)
vLLM Pod (llm-d-inference-scheduling namespace)
    ↓ HTTPS:443 (allowed by NetworkPolicy)
Internet (HuggingFace CDN for model downloads)

vLLM Pod
    ↓ UDP/TCP:53 (allowed by NetworkPolicy)
CoreDNS (kube-system namespace)
```

## Data Flow

### Model Loading

1. **Init Container (storage-initializer):**
   - Downloads model from HuggingFace Hub
   - Stores in `/mnt/models` (emptyDir volume)
   - Egress: HTTPS to `huggingface.co` (allowed by NetworkPolicy)

2. **vLLM Container:**
   - Loads model from `/mnt/models`
   - Compiles with JAX/XLA for TPU
   - First inference triggers compilation (slow)
   - Subsequent requests use compiled kernels

### Inference Request

1. **Input:** Client sends JSON request
2. **Tokenization:** vLLM tokenizes prompt
3. **Inference:** TPU executes model forward passes
4. **Decoding:** vLLM generates tokens autoregressively
5. **Output:** Returns JSON response with generated text

## Accelerator Configuration

### TPU v6e Details

- **Topology:** 2x2 (4 chips)
- **Memory:** 32 GB HBM per chip
- **Interconnect:** TPU network fabric
- **Software Stack:** JAX + XLA compiler

### vLLM Configuration

```yaml
env:
- name: TPU_CHIPS_PER_HOST_BOUNDS
  value: "2,2,1"  # 2x2x1 topology
- name: TPU_HOST_BOUNDS
  value: "1,1,1"  # Single host
- name: PJRT_DEVICE
  value: "TPU"

args:
- --model=/mnt/models
- --dtype=half
- --max-model-len=2048
- --tensor-parallel-size=4  # Use all 4 TPU chips
- --disable-log-requests
```

## Networking

### Pod Networking

- **Pod CIDR:** 10.28.0.0/14
- **Service CIDR:** 34.118.224.0/20
- **CNI:** GKE native (uses VPC routing)
- **NetworkPolicy Provider:** Calico

### Service Discovery

```
Service Name: qwen2-3b-pattern1-kserve-workload-svc
ClusterIP: 34.118.227.230
Port: 8000

DNS Names:
- qwen2-3b-pattern1-kserve-workload-svc.llm-d-inference-scheduling.svc.cluster.local
- qwen2-3b-pattern1-kserve-workload-svc.llm-d-inference-scheduling.svc
- qwen2-3b-pattern1-kserve-workload-svc
```

### External Access

```
LoadBalancer IP: 34.7.208.8
Ports:
  - 80/TCP  (HTTP)
  - 443/TCP (HTTPS)
  - 15021/TCP (Istio health/metrics)
```

## Observability

### Metrics Endpoints

| Component | Port | Endpoint | Metrics |
|-----------|------|----------|---------|
| vLLM | 8000 | /metrics | Inference metrics (Prometheus) |
| EPP Scheduler | 9090 | /metrics | Scheduler metrics |
| Gateway | 15090 | /stats/prometheus | Envoy metrics |

### Health Endpoints

| Component | Endpoint | Purpose |
|-----------|----------|---------|
| vLLM | /health | Liveness probe |
| vLLM | /v1/models | Readiness probe |
| Gateway | :15021/healthz/ready | Gateway readiness |

### Logs

```bash
# vLLM logs (inference and errors)
kubectl logs -n llm-d-inference-scheduling deployment/qwen2-3b-pattern1-kserve -f

# EPP scheduler logs
kubectl logs -n llm-d-inference-scheduling deployment/qwen2-3b-pattern1-kserve-router-scheduler -f

# Gateway logs
kubectl logs -n opendatahub deployment/inference-gateway-istio -f
```

## Resource Allocation

### vLLM Pod Resources

```yaml
resources:
  limits:
    google.com/tpu: "4"  # Request all 4 TPU chips
  requests:
    google.com/tpu: "4"
```

**Note:** TPU resources are not fractional - must request full chip counts.

### EPP Scheduler Resources

```yaml
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

## Scaling Considerations

### Current Configuration

- **Replicas:** 1 (single replica baseline)
- **Autoscaling:** Disabled
- **Node Pool:** Fixed size (1 TPU node)

### Scale-Out (Pattern 3)

To scale to multiple replicas:
1. Update `spec.replicas` in LLMInferenceService
2. EPP scheduler distributes requests across replicas
3. Prefix cache-aware routing improves cache hit rates

See: [Pattern 3 Architecture](../../../pattern3/README.md)

## Design Decisions

### Why No Istio Sidecars?

**Decision:** Use Istio Gateway only, no sidecars on application pods.

**Rationale:**
- Resource efficiency (sidecars add ~0.5 CPU + 200Mi per pod)
- TPU workloads are resource-intensive
- NetworkPolicies provide sufficient isolation
- Cluster is not multi-tenant

**Trade-off:** No mTLS for internal traffic.

### Why Path-Based Routing?

**Decision:** Use path prefix `/llm-d-inference-scheduling/qwen2-3b-pattern1/` for routing.

**Rationale:**
- KServe auto-generates HTTPRoutes with this pattern
- Supports multiple models on same Gateway
- Enables multi-tenancy (separate namespaces)

**Alternative:** Host-based routing (requires DNS setup).

### Why Self-Signed Certificates?

**Decision:** Use cert-manager with self-signed CA for testing.

**Rationale:**
- Automated renewal without external dependencies
- Fast setup for development/testing
- No DNS configuration required

**Production:** Switch to Let's Encrypt or organization CA.

## Related Documentation

- [Security Model](./security-model.md) - Detailed security architecture
- [Deployment Guide](./deployment-guide.md) - Step-by-step deployment
- [Pattern 1 Reference](../../../pattern1/README.md) - Pattern 1 overview
- [Pattern 1 Architecture Deep Dive](../../../pattern1/istio-kserve-llmd-architecture.md) - Complete reference
