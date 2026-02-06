# GKE Cluster: istio-kserve-pattern1

Production GKE cluster running Pattern 1 LLM inference with Istio + KServe + llm-d integration.

## Cluster Information

- **Name:** istio-kserve-pattern1
- **Project:** ecoeng-llmd
- **Zone:** europe-west4-a
- **Kubernetes Version:** 1.34.3-gke.1051003
- **Created:** 2026-02-06

## Infrastructure

### Node Pools

| Pool | Machine Type | Accelerator | Nodes | Purpose |
|------|-------------|------------|-------|---------|
| default-pool | n1-standard-4 | None | 2 | Control plane workloads, Istio Gateway |
| tpu-v6e-pool | ct6e-standard-4t | TPU v6e (4 chips) | 1 | LLM inference (vLLM) |

### Networking

- **Network:** default
- **Subnetwork:** default (europe-west4)
- **Pod CIDR:** 10.28.0.0/14
- **Service CIDR:** 34.118.224.0/20
- **NetworkPolicy:** Enabled (Calico provider)

### Gateway

- **Type:** Istio Ingress Gateway (LoadBalancer)
- **External IP:** 34.7.208.8
- **Ports:** 80 (HTTP), 443 (HTTPS)
- **TLS:** Enabled (cert-manager with self-signed CA)

## Deployed Components

### Operators

- **cert-manager:** v1.16.2 (certificate management)
- **sail-operator:** 3.1.x (Istio/OSSM)
- **KServe:** v0.15 (LLM serving)

### Security

- **TLS Termination:** Gateway (port 443)
- **Internal Traffic:** Plain HTTP (no mTLS)
- **NetworkPolicies:** Enabled (default-deny + allow rules)
- **Certificates:** Auto-renewed by cert-manager

See [docs/security-model.md](docs/security-model.md) for details.

### Applications

- **Pattern 1 Deployment:** Single replica baseline
  - Model: Qwen/Qwen2.5-3B-Instruct (3B parameters)
  - Accelerator: TPU v6e (4 chips, 2x2 topology)
  - Container: registry.redhat.io/rhaiis/vllm-tpu-rhel9:3.2.5
  - Scheduler: EPP (Endpoint Picker) for intelligent routing

## Directory Structure

```
istio-kserve-pattern1/
├── README.md                   # This file
├── cluster-info.yaml           # Cluster metadata (YAML)
├── security/
│   ├── certificates/           # TLS certificates
│   └── networkpolicies/        # Network isolation policies
├── deployments/
│   └── pattern1/               # Pattern 1 LLM deployment manifests
└── docs/
    ├── architecture.md         # Architecture overview
    ├── security-model.md       # Security design and hardening
    └── deployment-guide.md     # Deployment procedures
```

## Quick Links

- **Architecture:** [docs/architecture.md](docs/architecture.md)
- **Security Model:** [docs/security-model.md](docs/security-model.md)
- **Deployment Guide:** [docs/deployment-guide.md](docs/deployment-guide.md)
- **Pattern 1 Reference:** [../../pattern1/README.md](../../pattern1/README.md)

## Access

### API Endpoints

```bash
# Gateway External IP
export GATEWAY_IP=34.7.208.8

# HTTPS endpoint (recommended)
curl -k -X POST "https://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'

# HTTP endpoint (backwards compatibility)
curl -X POST "http://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

### Cluster Access

```bash
# Configure kubectl
gcloud container clusters get-credentials istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd

# Verify access
kubectl cluster-info
```

## Cost Management

### Current Monthly Cost (est.)

- **TPU v6e-1:** ~$3,760/month
- **n1-standard-4 nodes (2):** ~$150/month
- **LoadBalancer:** ~$20/month
- **Total:** ~$3,930/month

### Cost Optimization

```bash
# Scale down when not in use
kubectl scale deployment qwen2-3b-pattern1-kserve --replicas=0 -n llm-d-inference-scheduling
gcloud container node-pools update tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=1

# Delete TPU node pool (most cost-effective)
gcloud container node-pools delete tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --quiet
```

## Monitoring

```bash
# Check deployment status
kubectl get llminferenceservice -n llm-d-inference-scheduling
kubectl get pods -n llm-d-inference-scheduling
kubectl get gateway -n opendatahub

# View logs
kubectl logs -n llm-d-inference-scheduling deployment/qwen2-3b-pattern1-kserve -f

# Check NetworkPolicy enforcement
kubectl get networkpolicy -n llm-d-inference-scheduling
```

## Troubleshooting

See [docs/deployment-guide.md#troubleshooting](docs/deployment-guide.md#troubleshooting) for common issues and solutions.

## Related Documentation

- [Pattern 1 Overview](../../pattern1/README.md)
- [Pattern 1 Architecture Deep Dive](../../pattern1/istio-kserve-llmd-architecture.md)
- [llm-d Infrastructure](../../llm-d-infra-xks/README.md)
