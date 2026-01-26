# Pattern 3 Manifests

Kubernetes manifests for Pattern 3 (N/S-Caching Scale-Out deployment).

## Files

### `httproute-pattern3.yaml`
HTTPRoute that routes traffic to the Pattern 3 InferencePool for 3-replica caching deployment.

- Routes all requests to `gaie-pattern3` InferencePool
- 3 replicas with prefix-cache-aware routing
- Intelligent load balancing via EPP

## Deployment

After deploying infrastructure and model services with helmfile:

```bash
kubectl apply -f pattern3/manifests/httproute-pattern3.yaml -n llm-d-inference-scheduling
```

Verify the HTTPRoute:

```bash
kubectl get httproute -n llm-d-inference-scheduling
kubectl describe httproute pattern3-route -n llm-d-inference-scheduling
```

## See Also

- [Pattern 3 GPU Setup Guide](../llm-d-pattern3-gpu-setup.md)
- [Pattern 3 TPU Setup Guide](../llm-d-pattern3-tpu-setup.md)
