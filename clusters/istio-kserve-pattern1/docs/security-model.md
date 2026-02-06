# Security Model - istio-kserve-pattern1

This document describes the security architecture and hardening implemented for the Pattern 1 deployment on GKE.

## Implementation Date

**Security hardening completed:** 2026-02-06

## Overview

Pattern 1 implements **TLS at the edge** with **network isolation** for defense in depth, prioritizing resource efficiency for single-model TPU deployments.

## Security Architecture

### Encryption Model

```
Internet (HTTPS) → Gateway (TLS Termination) → Internal (HTTP) → vLLM Pods
```

**External Traffic:**
- Protocol: HTTPS
- Port: 443
- TLS Version: TLS 1.2+
- Certificate: Self-signed (cert-manager)
- Cipher Suites: Modern (configured by Istio)

**Internal Traffic:**
- Protocol: HTTP (plaintext)
- Port: 8000 (vLLM API)
- No mTLS between services
- No Istio sidecars injected

### Design Rationale: No mTLS

**Why Pattern 1 doesn't use mTLS:**

1. **Resource Efficiency**
   - Istio sidecars add ~0.5 CPU + ~200Mi memory per pod
   - TPU v6e workloads are resource-intensive
   - Minimizing overhead maximizes model serving capacity

2. **Simplified Operations**
   - Fewer components to manage and troubleshoot
   - Reduced certificate rotation complexity
   - Faster pod startup times

3. **Network Isolation Provides Defense**
   - NetworkPolicies prevent lateral movement
   - Internal traffic is already isolated within GKE VPC
   - Cluster is not multi-tenant

**Trade-off:** Internal traffic is not encrypted. This is acceptable because:
- GKE nodes are in a private VPC
- NetworkPolicies enforce strict pod-to-pod isolation
- No untrusted workloads share the cluster

---

## Certificate Management

### Implementation

**Provider:** cert-manager v1.16.2

**Components:**
```yaml
ClusterIssuer: opendatahub-ca-issuer (self-signed CA)
├── Certificate: inference-gateway-tls
│   ├── Namespace: opendatahub
│   ├── Secret: inference-gateway-tls-cert
│   ├── Duration: 90 days (2160h)
│   ├── Renewal: 15 days before expiry (360h)
│   └── SANs:
│       ├── inference-gateway.opendatahub.svc.cluster.local
│       ├── *.llm-d-inference-scheduling.svc.cluster.local
│       └── 34.7.208.8 (Gateway external IP)
```

**Auto-Renewal:** Certificates automatically renew 15 days before expiration.

### Verification

```bash
# Check certificate status
kubectl get certificate inference-gateway-tls -n opendatahub

# View certificate details
kubectl describe certificate inference-gateway-tls -n opendatahub

# Inspect TLS secret
kubectl get secret inference-gateway-tls-cert -n opendatahub -o yaml
```

### Production Considerations

**Current setup (self-signed):**
- ✅ Automated renewal
- ✅ Works for testing/development
- ❌ Browsers show security warnings
- ❌ Clients must use `-k` or disable TLS verification

**Production recommendations:**
1. Use **Let's Encrypt** for public endpoints (free, trusted by browsers)
2. Use **organization CA** for private/internal endpoints
3. Configure **ACME DNS-01 challenge** for wildcard certificates
4. Enable **Certificate Transparency** monitoring

---

## Network Isolation

### NetworkPolicy Configuration

**Enforcement:** Enabled via Calico (GKE NetworkPolicy addon)

**Policies Applied:**

#### 1. Default Deny All (`default-deny-all`)

```yaml
# Blocks ALL ingress and egress by default
spec:
  podSelector: {}  # Applies to all pods in namespace
  policyTypes:
  - Ingress
  - Egress
```

**Effect:** Nothing can communicate unless explicitly allowed.

#### 2. Allow Gateway to vLLM (`allow-gateway-to-vllm`)

```yaml
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: qwen2-3b-pattern1
      kserve.io/component: workload

  ingress:
  # Allow from Istio Gateway pods
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: opendatahub
      podSelector:
        matchLabels:
          gateway.networking.k8s.io/gateway-name: inference-gateway
    ports:
    - protocol: TCP
      port: 8000

  # Allow kubelet health probes (from nodes)
  - from:
    - namespaceSelector: {}
      podSelector: {}
    ports:
    - protocol: TCP
      port: 8000
```

**Allowed Traffic:**
- ✅ Gateway → vLLM (inference requests)
- ✅ Kubelet → vLLM (health/readiness probes)
- ❌ Other pods → vLLM (blocked)

#### 3. Allow vLLM Egress (`allow-vllm-egress`)

```yaml
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: qwen2-3b-pattern1
      kserve.io/component: workload

  egress:
  # Allow DNS queries to CoreDNS
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53

  # Allow HTTPS for model downloads
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443

  # Allow Kubernetes API access
  - to:
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          component: apiserver
    ports:
    - protocol: TCP
      port: 443
```

**Allowed Traffic:**
- ✅ vLLM → DNS (service discovery)
- ✅ vLLM → HuggingFace (model downloads via HTTPS)
- ✅ vLLM → Kubernetes API (metadata, health reporting)
- ❌ vLLM → other pods (blocked - no lateral movement)

### Traffic Flow Matrix

| Source | Destination | Port | Protocol | Allowed | Policy |
|--------|-------------|------|----------|---------|--------|
| Internet | Gateway | 443 | HTTPS | ✅ | GKE LoadBalancer |
| Internet | Gateway | 80 | HTTP | ✅ | GKE LoadBalancer |
| Gateway | vLLM | 8000 | HTTP | ✅ | allow-gateway-to-vllm |
| Kubelet | vLLM | 8000 | HTTP | ✅ | allow-gateway-to-vllm |
| vLLM | DNS | 53 | UDP/TCP | ✅ | allow-vllm-egress |
| vLLM | Internet | 443 | HTTPS | ✅ | allow-vllm-egress |
| Pod (same ns) | vLLM | 8000 | HTTP | ❌ | default-deny-all |
| vLLM | vLLM | 8000 | HTTP | ❌ | default-deny-all |

### Verification

```bash
# List NetworkPolicies
kubectl get networkpolicy -n llm-d-inference-scheduling

# Test lateral movement is blocked
kubectl run test-isolation --image=curlimages/curl:latest \
  -n llm-d-inference-scheduling --rm --restart=Never -- \
  timeout 10 curl http://<vllm-pod-ip>:8000/health
# Should timeout (connection blocked)

# Verify inference through Gateway works
curl -k -X POST "https://34.7.208.8/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-3B-Instruct", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 20}'
```

### GKE NetworkPolicy Enablement

**Steps taken to enable enforcement:**

```bash
# Step 1: Enable NetworkPolicy addon on cluster master
gcloud container clusters update istio-kserve-pattern1 \
  --update-addons=NetworkPolicy=ENABLED \
  --zone=europe-west4-a \
  --project=ecoeng-llmd

# Step 2: Enable NetworkPolicy enforcement on nodes (triggers node pool recreation)
gcloud container clusters update istio-kserve-pattern1 \
  --enable-network-policy \
  --zone=europe-west4-a \
  --project=ecoeng-llmd
```

**Provider:** Calico (GKE-managed)

**Verification:**
```bash
# Check NetworkPolicy is enabled
gcloud container clusters describe istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --format="get(networkPolicy)"
# Output: enabled=True;provider=CALICO

# Check Calico pods are running
kubectl get pods -n kube-system -l k8s-app=calico-node
kubectl get pods -n kube-system | grep calico
```

**⚠️ Important:** GKE NetworkPolicy enablement requires node pool recreation, which causes ~5-10 minutes of disruption.

---

## Gateway Security

### TLS Configuration

**Gateway Resource:**
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: inference-gateway
  namespace: opendatahub
spec:
  gatewayClassName: istio
  listeners:
  - name: http
    port: 80
    protocol: HTTP
    # Kept for backwards compatibility and debugging

  - name: https
    port: 443
    protocol: HTTPS
    tls:
      mode: Terminate
      certificateRefs:
      - kind: Secret
        name: inference-gateway-tls-cert
```

**External IP:** 34.7.208.8 (GCP L4 LoadBalancer)

**Ports:**
- **80 (HTTP):** Backwards compatibility, debugging, health checks
- **443 (HTTPS):** Primary endpoint for inference requests

### Testing TLS Termination

```bash
# Test HTTPS endpoint (self-signed cert, use -k)
curl -k -X POST "https://34.7.208.8/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-3B-Instruct", "messages": [{"role": "user", "content": "Test"}], "max_tokens": 20}'

# Verify TLS handshake (requires openssl)
echo | openssl s_client -connect 34.7.208.8:443 -servername \
  qwen2-3b-pattern1.llm-d-inference-scheduling.svc.cluster.local 2>/dev/null | \
  grep -E "subject=|issuer=|Verify return code"
```

---

## Security Trade-offs

| Aspect | Pattern 1 Approach | Alternative | Chosen Trade-off |
|--------|-------------------|-------------|------------------|
| **Service-to-service encryption** | None (HTTP only) | Istio mTLS with sidecars | Resource efficiency > encryption overhead |
| **Network isolation** | NetworkPolicies (L3/L4) | Service mesh authz (L7) | Simpler policies > fine-grained control |
| **Certificate management** | cert-manager self-signed | Let's Encrypt / org CA | Testing simplicity > browser trust |
| **Egress control** | Allow HTTPS:443 to any | IP/FQDN restrictions | Simplicity > tighter control |
| **Authentication** | None | API keys / OAuth | Testing ease > access control |

---

## Production Hardening Recommendations

For production deployments, implement these additional security measures:

### 1. Use Trusted CA

**Current:** Self-signed certificates (browser warnings)

**Recommended:**
```yaml
# Use Let's Encrypt with cert-manager
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - dns01:
        cloudDNS:
          project: ecoeng-llmd
```

### 2. Add Web Application Firewall

**Deploy Cloud Armor** for DDoS protection and rate limiting:

```bash
# Create Cloud Armor security policy
gcloud compute security-policies create llm-inference-policy \
  --description="Rate limiting and DDoS protection for LLM inference"

# Add rate limiting rule
gcloud compute security-policies rules create 1000 \
  --security-policy=llm-inference-policy \
  --expression="true" \
  --action=rate-based-ban \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60

# Attach to backend service
gcloud compute backend-services update <backend-service> \
  --security-policy=llm-inference-policy
```

### 3. Restrict Egress IPs

**Update NetworkPolicy** to allow only HuggingFace CDN:

```yaml
# Replace broad HTTPS:443 egress with specific CIDRs
egress:
- to:
  - ipBlock:
      cidr: 18.184.0.0/16  # HuggingFace CDN (example, verify actual IPs)
  ports:
  - protocol: TCP
    port: 443
```

### 4. Enable Audit Logging

**Configure GKE audit logs** to track API access:

```bash
gcloud container clusters update istio-kserve-pattern1 \
  --enable-cloud-logging \
  --logging=SYSTEM,WORKLOAD,API_SERVER \
  --zone=europe-west4-a
```

### 5. Add Authentication

**Implement API key validation** at Gateway (Istio EnvoyFilter):

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: api-key-auth
  namespace: opendatahub
spec:
  workloadSelector:
    labels:
      gateway.networking.k8s.io/gateway-name: inference-gateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.ext_authz
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz
          # Configure external authorization service
```

### 6. Monitor Network Traffic

**Use GKE network flow logs** for traffic visibility:

```bash
gcloud compute networks subnets update default \
  --region=europe-west4 \
  --enable-flow-logs \
  --logging-aggregation-interval=interval-5-sec \
  --logging-flow-sampling=0.5
```

---

## Security Incident Response

### Suspected Compromise

1. **Isolate affected pods:**
   ```bash
   kubectl scale deployment <compromised-deployment> --replicas=0
   ```

2. **Review audit logs:**
   ```bash
   gcloud logging read "resource.type=k8s_cluster" --limit=500
   ```

3. **Check NetworkPolicy violations:**
   ```bash
   kubectl get events -n llm-d-inference-scheduling | grep NetworkPolicy
   ```

4. **Rotate certificates:**
   ```bash
   kubectl delete secret inference-gateway-tls-cert -n opendatahub
   # cert-manager will automatically reissue
   ```

### Certificate Expiration

**Automated renewal** should prevent expiration, but if needed:

```bash
# Force certificate renewal
kubectl delete certificaterequest -n opendatahub --all
kubectl annotate certificate inference-gateway-tls -n opendatahub \
  cert-manager.io/issue-temporary-certificate="true"
```

---

## Compliance Considerations

### Data Protection

- **In-transit encryption:** HTTPS (external), HTTP (internal GKE VPC)
- **At-rest encryption:** GKE uses encrypted persistent disks by default
- **Model data:** Downloaded to ephemeral pod storage, deleted on termination

### Access Control

- **Cluster access:** GKE IAM + RBAC
- **API access:** No authentication (add for production)
- **Certificate management:** Automated by cert-manager

### Audit Trail

- **GKE audit logs:** Track API server requests
- **Envoy access logs:** Gateway traffic (if enabled)
- **NetworkPolicy:** Logs available via Calico (requires configuration)

---

## References

- [Pattern 1 Architecture](../../../pattern1/istio-kserve-llmd-architecture.md)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Calico NetworkPolicy](https://docs.tigera.io/calico/latest/network-policy/)
- [Istio Gateway API](https://istio.io/latest/docs/tasks/traffic-management/ingress/gateway-api/)
- [GKE Security Best Practices](https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster)
