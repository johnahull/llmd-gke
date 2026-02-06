# Deployment Guide - istio-kserve-pattern1

This guide documents the actual deployment steps used to create and configure the istio-kserve-pattern1 cluster.

## Prerequisites

- Google Cloud SDK (`gcloud`) configured
- `kubectl` installed
- `helmfile` installed
- Red Hat registry credentials (11009103-jhull-svc-pull-secret.yaml)
- Hugging Face token for model downloads

## Deployment Timeline

**Cluster created:** 2026-02-06
**Security hardening completed:** 2026-02-06
**Status:** Production-ready

---

## Part 1: GKE Cluster Creation

### Step 1: Create GKE Cluster

```bash
# Create cluster with default node pool
gcloud container clusters create istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --machine-type=n1-standard-4 \
  --num-nodes=2 \
  --disk-size=100 \
  --kubernetes-version=1.34.3-gke.1051003 \
  --enable-ip-alias \
  --network=default \
  --subnetwork=default \
  --enable-cloud-logging \
  --enable-cloud-monitoring \
  --addons=HorizontalPodAutoscaling,HttpLoadBalancing

# Expected output: Cluster created (5-10 minutes)
```

### Step 2: Add TPU Node Pool

```bash
# Add TPU v6e node pool
gcloud container node-pools create tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --machine-type=ct6e-standard-4t \
  --num-nodes=1 \
  --disk-size=100 \
  --node-labels=cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice,cloud.google.com/gke-tpu-topology=2x2 \
  --node-taints=google.com/tpu=present:NoSchedule

# Expected output: Node pool created (3-5 minutes)
```

### Step 3: Configure kubectl

```bash
# Get cluster credentials
gcloud container clusters get-credentials istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd

# Verify cluster access
kubectl cluster-info
kubectl get nodes
```

**Expected output:**
```
NAME                                                  STATUS   ROLES    AGE   VERSION
gke-istio-kserve-pattern-default-pool-xxxxx-xxxx     Ready    <none>   10m   v1.34.3-gke.1051003
gke-istio-kserve-pattern-default-pool-xxxxx-yyyy     Ready    <none>   10m   v1.34.3-gke.1051003
gke-tpu-xxxxxxxx-zzzz                                 Ready    <none>   5m    v1.34.3-gke.1051003
```

---

## Part 2: Infrastructure Deployment

### Step 4: Deploy llm-d-infra-xks

**Navigate to infrastructure directory:**
```bash
cd /path/to/llm-d-infra-xks
```

**Deploy cert-manager + sail-operator:**
```bash
make deploy

# This deploys:
# - cert-manager operator
# - sail-operator (Istio)
# - Creates opendatahub namespace
# - Creates opendatahub-ca-issuer (ClusterIssuer)
```

**Verify deployment:**
```bash
kubectl get pods -n cert-manager
kubectl get pods -n sail-operator
kubectl get clusterissuer
```

**Expected output:**
```
# cert-manager
cert-manager-xxx-yyy                    1/1     Running
cert-manager-cainjector-xxx-yyy         1/1     Running
cert-manager-webhook-xxx-yyy            1/1     Running

# sail-operator
sail-operator-xxx-yyy                   1/1     Running

# ClusterIssuer
opendatahub-ca-issuer         True    5m
opendatahub-selfsigned-issuer True    5m
```

### Step 5: Create Gateway

**Run gateway setup script:**
```bash
cd /path/to/llm-d-infra-xks
./scripts/setup-gateway.sh
```

**This creates:**
- Gateway resource (inference-gateway) in opendatahub namespace
- CA bundle ConfigMap (odh-ca-bundle)
- Gateway config ConfigMap

**Verify:**
```bash
kubectl get gateway -n opendatahub
kubectl get svc -n opendatahub | grep inference-gateway
```

**Expected output:**
```
NAME                CLASS   ADDRESS      PROGRAMMED   AGE
inference-gateway   istio   34.7.208.8   True         2m

NAME                              TYPE           EXTERNAL-IP    PORT(S)
inference-gateway-istio           LoadBalancer   34.7.208.8     80:xxxxx/TCP
```

---

## Part 3: Security Hardening

### Step 6: Create Gateway TLS Certificate

**Create certificate manifest:**
```bash
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: inference-gateway-tls
  namespace: opendatahub
spec:
  secretName: inference-gateway-tls-cert
  duration: 2160h  # 90 days
  renewBefore: 360h  # 15 days
  issuerRef:
    name: opendatahub-ca-issuer
    kind: ClusterIssuer
  commonName: inference-gateway.opendatahub.svc.cluster.local
  dnsNames:
  - inference-gateway.opendatahub.svc.cluster.local
  - "*.llm-d-inference-scheduling.svc.cluster.local"
  ipAddresses:
  - 34.7.208.8  # Gateway external IP
  usages:
  - digital signature
  - key encipherment
  - server auth
EOF
```

**Verify certificate:**
```bash
kubectl get certificate inference-gateway-tls -n opendatahub
# Should show READY: True after ~30 seconds

kubectl get secret inference-gateway-tls-cert -n opendatahub
# Should exist with type kubernetes.io/tls
```

### Step 7: Add HTTPS Listener to Gateway

**Patch Gateway to add HTTPS listener:**
```bash
kubectl patch gateway inference-gateway -n opendatahub --type=json -p='[
  {
    "op": "add",
    "path": "/spec/listeners/-",
    "value": {
      "name": "https",
      "port": 443,
      "protocol": "HTTPS",
      "allowedRoutes": {
        "namespaces": {
          "from": "All"
        }
      },
      "tls": {
        "mode": "Terminate",
        "certificateRefs": [
          {
            "kind": "Secret",
            "name": "inference-gateway-tls-cert"
          }
        ]
      }
    }
  }
]'
```

**Verify both listeners exist:**
```bash
kubectl get gateway inference-gateway -n opendatahub -o jsonpath='{.spec.listeners[*].name}'
# Should output: http https
```

### Step 8: Enable NetworkPolicy Enforcement

**⚠️ Warning:** This will recreate node pools (~5-10 min disruption).

**Step 8a: Enable NetworkPolicy addon on master:**
```bash
gcloud container clusters update istio-kserve-pattern1 \
  --update-addons=NetworkPolicy=ENABLED \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --quiet
```

**Step 8b: Enable NetworkPolicy enforcement on nodes:**
```bash
gcloud container clusters update istio-kserve-pattern1 \
  --enable-network-policy \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --quiet
```

**Verify Calico is running:**
```bash
kubectl get pods -n kube-system | grep calico
# Should see calico-typha and calico-node-vertical-autoscaler pods
```

### Step 9: Deploy NetworkPolicies

**Create application namespace:**
```bash
kubectl create namespace llm-d-inference-scheduling
```

**Apply NetworkPolicies:**
```bash
# Apply from cluster directory
cd clusters/istio-kserve-pattern1

kubectl apply -f security/networkpolicies/networkpolicy-default-deny.yaml
kubectl apply -f security/networkpolicies/networkpolicy-allow-gateway.yaml
kubectl apply -f security/networkpolicies/networkpolicy-allow-vllm-egress.yaml
```

**Verify policies:**
```bash
kubectl get networkpolicy -n llm-d-inference-scheduling
```

**Expected output:**
```
NAME                    POD-SELECTOR
allow-gateway-to-vllm   app.kubernetes.io/name=qwen2-3b-pattern1,kserve.io/component=workload
allow-vllm-egress       app.kubernetes.io/name=qwen2-3b-pattern1,kserve.io/component=workload
default-deny-all        <none>
```

---

## Part 4: Application Deployment

### Step 10: Create Secrets

**Red Hat registry pull secret:**
```bash
kubectl create secret generic 11009103-jhull-svc-pull-secret \
  --from-file=.dockerconfigjson=/path/to/11009103-jhull-svc-pull-secret.yaml \
  --type=kubernetes.io/dockerconfigjson \
  -n llm-d-inference-scheduling
```

**Hugging Face token:**
```bash
kubectl create secret generic hf-token \
  --from-literal=HF_TOKEN=<your-huggingface-token> \
  -n llm-d-inference-scheduling
```

### Step 11: Deploy Pattern 1 LLMInferenceService

**Apply deployment manifest:**
```bash
cd clusters/istio-kserve-pattern1
kubectl apply -f deployments/pattern1/llmisvc-pattern1-tpu.yaml
```

**Monitor deployment:**
```bash
# Watch LLMInferenceService status
kubectl get llminferenceservice -n llm-d-inference-scheduling -w

# Watch pod creation
kubectl get pods -n llm-d-inference-scheduling -w
```

**Deployment stages:**
1. Init container downloads model (~2-3 min)
2. vLLM container starts and compiles model for TPU (~5-7 min)
3. Pod becomes Ready
4. HTTPRoute auto-created by KServe
5. InferencePool becomes Programmed

**Expected final state:**
```bash
kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling
# STATUS: Ready

kubectl get pods -n llm-d-inference-scheduling
# qwen2-3b-pattern1-kserve-xxx: 1/1 Running
# qwen2-3b-pattern1-kserve-router-scheduler-xxx: 1/1 Running

kubectl get httproute -n llm-d-inference-scheduling
# qwen2-3b-pattern1-kserve-route: 2 routes

kubectl get inferencepool -n llm-d-inference-scheduling
# qwen2-3b-pattern1-inference-pool: age 10m
```

---

## Part 5: Verification

### Step 12: Test HTTP Endpoint

```bash
export GATEWAY_IP=34.7.208.8

curl -X POST "http://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "prompt": "What is 2+2?",
    "max_tokens": 20
  }'
```

**Expected response:**
```json
{
  "id": "cmpl-xxx",
  "object": "text_completion",
  "created": 1738864823,
  "model": "Qwen/Qwen2.5-3B-Instruct",
  "choices": [{
    "index": 0,
    "text": " 4",
    "logprobs": null,
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 6,
    "completion_tokens": 2,
    "total_tokens": 8
  }
}
```

### Step 13: Test HTTPS Endpoint

```bash
curl -k -X POST "https://${GATEWAY_IP}/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 50
  }'
```

**Note:** Use `-k` flag to accept self-signed certificate.

### Step 14: Verify NetworkPolicy Enforcement

**Test lateral movement is blocked:**
```bash
# Get vLLM pod IP
VLLM_POD_IP=$(kubectl get pod -n llm-d-inference-scheduling \
  -l kserve.io/component=workload \
  -o jsonpath='{.items[0].status.podIP}')

# Try to access from test pod (should timeout)
kubectl run test-isolation --image=curlimages/curl:latest \
  -n llm-d-inference-scheduling --rm --restart=Never -- \
  timeout 10 curl http://${VLLM_POD_IP}:8000/health
```

**Expected:** Connection timeout (blocked by NetworkPolicy).

### Step 15: Verify Health Probes

```bash
kubectl get pod -n llm-d-inference-scheduling \
  -l kserve.io/component=workload
```

**Expected:** Pod shows `1/1 Running` with READY status.

---

## Troubleshooting

### Pod Stuck in ContainerCreating

**Symptoms:**
```
qwen2-3b-pattern1-kserve-xxx   0/1     ContainerCreating
```

**Check:**
```bash
kubectl describe pod -n llm-d-inference-scheduling qwen2-3b-pattern1-kserve-xxx
```

**Common causes:**
1. **Image pull error** - Check registry secret exists
2. **TPU not available** - Verify TPU node pool exists
3. **Volume mount error** - Check storage class

**Fix:**
```bash
# Recreate pull secret if needed
kubectl get secret 11009103-jhull-svc-pull-secret -n llm-d-inference-scheduling

# Verify TPU nodes exist
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v6e-slice
```

### Pod CrashLoopBackOff

**Symptoms:**
```
qwen2-3b-pattern1-kserve-xxx   0/1     CrashLoopBackOff
```

**Check logs:**
```bash
kubectl logs -n llm-d-inference-scheduling qwen2-3b-pattern1-kserve-xxx
```

**Common causes:**
1. **Model download failed** - Check HF token
2. **Out of memory** - Reduce `--max-model-len`
3. **TPU init failed** - Check TPU environment variables

**Fix:**
```bash
# Verify HF token secret
kubectl get secret hf-token -n llm-d-inference-scheduling

# Check TPU configuration
kubectl get pod qwen2-3b-pattern1-kserve-xxx -n llm-d-inference-scheduling \
  -o jsonpath='{.spec.containers[0].env}' | jq .
```

### Gateway Returns 404

**Symptoms:**
```
HTTP/1.1 404 Not Found
```

**Check HTTPRoute:**
```bash
kubectl get httproute -n llm-d-inference-scheduling
kubectl describe httproute qwen2-3b-pattern1-kserve-route -n llm-d-inference-scheduling
```

**Verify path:**
```bash
# HTTPRoute path should be:
/llm-d-inference-scheduling/qwen2-3b-pattern1/v1/chat/completions

# Not:
/v1/chat/completions  # This will 404
```

### NetworkPolicy Blocks Health Probes

**Symptoms:**
```
Pod qwen2-3b-pattern1-kserve-xxx: Readiness probe failed
```

**Check NetworkPolicy:**
```bash
kubectl get networkpolicy -n llm-d-inference-scheduling
kubectl describe networkpolicy allow-gateway-to-vllm -n llm-d-inference-scheduling
```

**Verify kubelet rule exists:**
```yaml
# Should have this rule in allow-gateway-to-vllm:
- from:
  - namespaceSelector: {}
    podSelector: {}
  ports:
  - protocol: TCP
    port: 8000
```

### Certificate Not Ready

**Symptoms:**
```
NAME                    READY   SECRET
inference-gateway-tls   False   inference-gateway-tls-cert
```

**Check cert-manager:**
```bash
kubectl describe certificate inference-gateway-tls -n opendatahub
kubectl get certificaterequest -n opendatahub
```

**Common causes:**
1. **Issuer not found** - Verify ClusterIssuer exists
2. **Validation failed** - Check certificate SANs

**Fix:**
```bash
# Verify issuer
kubectl get clusterissuer opendatahub-ca-issuer

# Force certificate reissue
kubectl delete certificaterequest -n opendatahub --all
```

---

## Cost Monitoring

### Daily Costs (Approximate)

```
TPU v6e-1:              $127/day ($3,760/month)
n1-standard-4 (2):      $5/day ($150/month)
LoadBalancer:           $0.70/day ($20/month)
─────────────────────────────────────────────
Total:                  $133/day ($3,930/month)
```

### Cost Optimization

**When not in use:**

```bash
# Scale down vLLM deployment
kubectl scale deployment qwen2-3b-pattern1-kserve --replicas=0 \
  -n llm-d-inference-scheduling

# Delete TPU node pool (saves $127/day)
gcloud container node-pools delete tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --quiet
```

**To restart:**

```bash
# Recreate TPU node pool
gcloud container node-pools create tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a \
  --project=ecoeng-llmd \
  --machine-type=ct6e-standard-4t \
  --num-nodes=1

# Scale up vLLM deployment
kubectl scale deployment qwen2-3b-pattern1-kserve --replicas=1 \
  -n llm-d-inference-scheduling
```

---

## Backup and Disaster Recovery

### Backup Procedure

**Export manifests:**
```bash
# Export cluster resources
kubectl get llminferenceservice qwen2-3b-pattern1 -n llm-d-inference-scheduling -o yaml \
  > backup/llmisvc-pattern1-backup.yaml

kubectl get networkpolicy -n llm-d-inference-scheduling -o yaml \
  > backup/networkpolicies-backup.yaml

kubectl get gateway inference-gateway -n opendatahub -o yaml \
  > backup/gateway-backup.yaml
```

**Backup secrets (encrypted):**
```bash
# Export secrets (DO NOT commit to git)
kubectl get secret -n llm-d-inference-scheduling -o yaml \
  > backup/secrets-backup.yaml

# Encrypt backup
gpg --encrypt --recipient admin@example.com backup/secrets-backup.yaml
```

### Disaster Recovery

**Restore from backup:**
```bash
# Recreate namespace
kubectl create namespace llm-d-inference-scheduling

# Restore secrets
gpg --decrypt backup/secrets-backup.yaml.gpg | kubectl apply -f -

# Restore NetworkPolicies
kubectl apply -f backup/networkpolicies-backup.yaml

# Restore LLMInferenceService
kubectl apply -f backup/llmisvc-pattern1-backup.yaml
```

---

## Maintenance

### Update Kubernetes Version

```bash
# Update cluster master
gcloud container clusters upgrade istio-kserve-pattern1 \
  --master \
  --cluster-version=1.34.4-gke.1234567 \
  --zone=europe-west4-a

# Update node pools
gcloud container node-pools upgrade default-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a

gcloud container node-pools upgrade tpu-v6e-pool \
  --cluster=istio-kserve-pattern1 \
  --zone=europe-west4-a
```

### Update cert-manager

```bash
cd /path/to/llm-d-infra-xks
git pull
make deploy-cert-manager
```

### Rotate Certificates

**Manual rotation:**
```bash
kubectl delete secret inference-gateway-tls-cert -n opendatahub
# cert-manager will automatically reissue
```

**Force renewal:**
```bash
kubectl annotate certificate inference-gateway-tls -n opendatahub \
  cert-manager.io/issue-temporary-certificate="true"
```

---

## Next Steps

- [Configure monitoring and alerting](https://cloud.google.com/stackdriver)
- [Set up CI/CD pipeline](https://cloud.google.com/build)
- [Implement autoscaling (Pattern 3)](../../../pattern3/README.md)
- [Add multiple models (Pattern 2)](../../../pattern2/README.md)
- [Replace self-signed certs with Let's Encrypt](./security-model.md#production-hardening-recommendations)

---

## References

- [Architecture Documentation](./architecture.md)
- [Security Model](./security-model.md)
- [Pattern 1 Overview](../../../pattern1/README.md)
- [llm-d Documentation](https://llm-d.ai/docs)
- [GKE Documentation](https://cloud.google.com/kubernetes-engine/docs)
