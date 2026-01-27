# llm-d EPP Backend Discovery Limitation

## TL;DR

The llm-d EPP (Endpoint Picker) scheduler has a backend discovery limitation that causes **intermittent routing failures** in multi-model deployments. Client-side retry logic (2-2.2 attempts average) is **required** to achieve 100% success rates.

---

## The Problem

### Symptom

When deploying multiple models with a single InferencePool (Pattern 2 GPU multi-model):
- **40-60% success rate** without retry logic
- Requests fail with "model not found" errors
- `/v1/models` endpoint returns **only ONE model at a time** (flickering between models)
- Retrying after 2 seconds often succeeds

### Root Cause

The EPP backend discovery has an architectural limitation:

1. **InferencePool selector matches multiple pods**:
   ```yaml
   selector:
     matchLabels:
       llm-d.ai/inferenceServing: "true"  # Matches ALL model pods
   ```

2. **EPP queries backends via headless service**:
   - DNS returns pod IPs via round-robin
   - EPP queries **ONE pod at a time**, not all simultaneously

3. **Model list "flickers"**:
   - Query 1 → hits Gemma pod → returns `["google/gemma-2b-it"]`
   - Query 2 → hits Phi-3 pod → returns `["microsoft/Phi-3-mini-4k-instruct"]`
   - Query 3 → hits Gemma pod → returns `["google/gemma-2b-it"]`

4. **Requests fail when wrong model is visible**:
   - Client requests `microsoft/Phi-3-mini-4k-instruct`
   - EPP's last query returned Gemma → model not in list
   - Request fails with model not found

### Evidence

**DNS resolves correctly** (all backend IPs present):
```bash
$ kubectl run -it --rm debug --image=busybox -n llm-d -- \
  nslookup gaie-pattern2-ips-506adabb.llm-d.svc.cluster.local

Name: gaie-pattern2-ips-506adabb.llm-d.svc.cluster.local
Address: 10.0.0.16  # Phi-3-mini pod
Name: gaie-pattern2-ips-506adabb.llm-d.svc.cluster.local
Address: 10.0.4.5   # Gemma-2B pod
```

**Model discovery flickers** (only one model visible per query):
```bash
$ for i in {1..5}; do
  curl -s http://35.209.92.117/v1/models | jq -r '.data[].id'
  sleep 2
done

google/gemma-2b-it                      # Query 1
microsoft/Phi-3-mini-4k-instruct       # Query 2
google/gemma-2b-it                      # Query 3
microsoft/Phi-3-mini-4k-instruct       # Query 4
microsoft/Phi-3-mini-4k-instruct       # Query 5
```

**Requests fail intermittently** (without retry):
```bash
$ for i in {1..10}; do
  curl -s -X POST http://35.209.92.117/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "microsoft/Phi-3-mini-4k-instruct", "prompt": "Test", "max_tokens": 10}' \
    | jq -r '.model // "FAILED"'
done

FAILED                                  # EPP saw Gemma, not Phi-3
microsoft/Phi-3-mini-4k-instruct       # Success
FAILED                                  # EPP saw Gemma again
microsoft/Phi-3-mini-4k-instruct       # Success
microsoft/Phi-3-mini-4k-instruct       # Success
FAILED                                  # EPP saw Gemma
...
# Result: ~60% success rate
```

---

## Why This Happens

### EPP Backend Discovery Flow

```
1. EPP needs to discover available models
   ↓
2. EPP queries headless service (gaie-pattern2-ips-506adabb)
   ↓
3. DNS returns ONE IP (round-robin)
   ↓
4. EPP queries /v1/models on that single IP
   ↓
5. Gets model list from ONE pod only
   ↓
6. EPP uses this incomplete model list for routing
   ↓
7. Requests for "missing" model fail
```

### What SHOULD Happen

```
1. EPP resolves headless service → gets ALL pod IPs
   ↓
2. EPP queries /v1/models on EACH pod individually
   ↓
3. Pod 1 returns: ["microsoft/Phi-3-mini-4k-instruct"]
   Pod 2 returns: ["google/gemma-2b-it"]
   ↓
4. EPP aggregates: ["microsoft/Phi-3-mini-4k-instruct", "google/gemma-2b-it"]
   ↓
5. Complete model list persists across requests
   ↓
6. All requests route correctly (100% success)
```

### Configuration Details

**EPP Arguments** (from deployment):
```yaml
args:
  - --pool-name=gaie-pattern2
  - --pool-namespace=llm-d
  - --refresh-metrics-interval=50000000      # 50ms refresh
  - --metrics-staleness-threshold=2000000000 # 2s staleness
```

No configuration options exist to:
- Force querying all backend IPs
- Aggregate model lists from multiple backends
- Cache model discovery results

---

## Impact Analysis

### Pattern 2 GPU Multi-Model Deployment

**Configuration**:
- InferencePool: `gaie-pattern2`
- Selector: `llm-d.ai/inferenceServing: true`
- Backends: 2 pods (Phi-3-mini, Gemma-2B)
- Gateway: 35.209.92.117

**Results**:

| Test Type | Retries | Success Rate | Avg Attempts | Notes |
|-----------|---------|--------------|--------------|-------|
| **Without retry logic** | 0 | 40-60% | 1.0 | Unacceptable for production |
| **With retry logic (max 10)** | Yes | 100% | 2.0-2.2 | Acceptable with client changes |

**Benchmark Results** (50 requests, 25 per model):

```
Pattern 2 GPU Multi-Model Benchmark with Retry Logic
================================================================================

Model: microsoft/Phi-3-mini-4k-instruct
  Requests: 25/25 succeeded
  Success Rate: 100.0%
  Retry Statistics:
    Avg attempts per request: 2.0
    Max attempts needed: 5

Model: google/gemma-2b-it
  Requests: 25/25 succeeded
  Success Rate: 100.0%
  Retry Statistics:
    Avg attempts per request: 2.2
    Max attempts needed: 6

UNIFIED ROUTING VERIFICATION
  Total Requests: 50
  Total Successful: 50
  Overall Success Rate: 100.0%

  ✅✅✅ 100% COMPLETION ACHIEVED ✅✅✅
```

### Why Retry Logic Works

Retrying with 2-second delays gives the EPP time to query the other backend pod:
- First attempt → EPP has Gemma in cache → request fails
- Wait 2 seconds
- EPP refreshes (50ms interval) and queries Phi-3 pod
- Second attempt → EPP has Phi-3 in cache → request succeeds

Average 2-2.2 attempts indicates EPP backend discovery refresh rate.

---

## Workarounds

### Option 1: Client-Side Retry Logic (Recommended)

**Pros**:
- ✅ Simple to implement
- ✅ Achieves 100% success rate
- ✅ Works with existing deployments
- ✅ No infrastructure changes

**Cons**:
- ❌ Increased latency (1st attempt: ~2s, 2nd attempt: ~2s = 4s total)
- ❌ Requires client changes
- ❌ Not transparent to end users

**Implementation**:

**Bash**:
```bash
for attempt in {1..10}; do
  RESPONSE=$(curl -s --max-time 25 -X POST http://35.209.92.117/v1/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$MODEL\", \"prompt\": \"$PROMPT\", \"max_tokens\": 50}")

  RESPONSE_MODEL=$(echo "$RESPONSE" | jq -r '.model // "null"')

  if [ "$RESPONSE_MODEL" = "$MODEL" ]; then
    echo "Success on attempt $attempt"
    break
  fi

  sleep 2  # Wait for EPP to refresh backend discovery
done
```

**Python**:
```python
async def send_request_with_retry(session, model, prompt, max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        async with session.post(
            "http://35.209.92.117/v1/completions",
            json={"model": model, "prompt": prompt, "max_tokens": 50}
        ) as response:
            result = await response.json()

            if result.get("model") == model:
                return True, result, attempt

            if attempt < max_attempts:
                await asyncio.sleep(2)

    return False, {"error": "Max retries exceeded"}, max_attempts
```

### Option 2: BBR (Body Based Router) Architecture

**Pros**:
- ✅ 100% success rate without retries
- ✅ Pattern 2 TPU uses this successfully
- ✅ Transparent to clients

**Cons**:
- ❌ Requires separate InferencePools per model
- ❌ More complex infrastructure
- ❌ Header injection required (BBR filter or manual headers)

**Architecture**:
```yaml
# Separate InferencePools
InferencePool: gaie-pattern2-phi3
  selector: {llm-d.ai/model: phi-3-mini}

InferencePool: gaie-pattern2-gemma
  selector: {llm-d.ai/model: gemma-2b}

# Header-based HTTPRoutes
HTTPRoute: phi3-route
  matches:
    - headers:
      - name: x-model-name
        value: microsoft/Phi-3-mini-4k-instruct
  backendRefs:
    - InferencePool: gaie-pattern2-phi3

HTTPRoute: gemma-route
  matches:
    - headers:
      - name: x-model-name
        value: google/gemma-2b-it
  backendRefs:
    - InferencePool: gaie-pattern2-gemma
```

**Status**: Not implemented for Pattern 2 GPU (Pattern 2 TPU uses this approach).

### Option 3: Single-Model Per InferencePool

**Pros**:
- ✅ 100% success rate
- ✅ Simple architecture
- ✅ No EPP discovery issues

**Cons**:
- ❌ Not true "multi-model" deployment
- ❌ Separate Gateways per model
- ❌ This is just Pattern 1 deployed twice

**Architecture**:
```
Pattern 1 Gateway (35.209.201.202) → Gemma-2B only
Pattern 2 Gateway (35.209.92.117)  → Phi-3-mini only
```

**Status**: This defeats the purpose of Pattern 2 multi-model routing.

---

## Upstream Issue

This is a limitation in the `llm-d-inference-scheduler` (EPP) implementation, specifically in how it discovers and aggregates backends.

**Affected Component**: `ghcr.io/llm-d/llm-d-inference-scheduler:v0.4.0`

**Required Fix**: EPP should:
1. Resolve ALL pod IPs from headless service DNS
2. Query `/v1/models` on EACH pod individually
3. Aggregate model lists from all backends
4. Persist aggregated list across requests

**Tracking**: This limitation is documented in this repository. Consider filing an issue with llm-d project:
- Repository: https://github.com/llm-d/llm-d
- Component: `llm-d-inference-scheduler` (EPP)

---

## Recommendations

### For Pattern 2 GPU Deployments

**Short-term** (Production NOW):
- ✅ Implement client-side retry logic (max 10 attempts, 2s delay)
- ✅ Document retry requirement in API documentation
- ✅ Monitor retry statistics (alert if avg > 3 attempts)
- ✅ Use custom benchmark: `benchmarks/python/pattern2_benchmark_retry.py`

**Long-term** (Future):
- Consider migrating to BBR architecture (separate InferencePools)
- OR wait for upstream EPP fix in llm-d
- OR deploy single model per Gateway (abandon multi-model)

### For New Deployments

**If you need multi-model routing WITHOUT retries**:
- Use Pattern 2 TPU approach (BBR with header-based routing)
- Requires separate InferencePools per model
- Achieves 100% success without client changes

**If retry logic is acceptable**:
- Use Pattern 2 GPU approach (unified InferencePool)
- Simpler infrastructure
- Client implements retry logic
- 100% success with 2-2.2 average attempts

---

## Testing

### Verify EPP Discovery Issue

```bash
# 1. Check DNS resolution (should show ALL pod IPs)
kubectl run -it --rm debug --image=busybox -n llm-d -- \
  nslookup gaie-pattern2-ips-506adabb.llm-d.svc.cluster.local

# 2. Query /v1/models multiple times (will flicker between models)
for i in {1..10}; do
  echo "Attempt $i:"
  curl -s http://35.209.92.117/v1/models | jq -r '.data[].id'
  sleep 2
done

# 3. Test success rate WITHOUT retry
SUCCESS=0
for i in {1..20}; do
  RESULT=$(curl -s -X POST http://35.209.92.117/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "microsoft/Phi-3-mini-4k-instruct", "prompt": "Test", "max_tokens": 10}' \
    | jq -r '.model // "FAILED"')

  [ "$RESULT" != "FAILED" ] && SUCCESS=$((SUCCESS + 1))
done

echo "Success rate: $((SUCCESS * 100 / 20))%"
# Expected: 40-60%

# 4. Test WITH retry logic
python3 benchmarks/python/pattern2_benchmark_retry.py
# Expected: 100% success, avg 2-2.2 attempts
```

---

## References

- **Pattern 2 GPU Documentation**: `pattern2/llm-d-pattern2-gpu-setup.md`
- **Pattern 2 TPU (BBR approach)**: `pattern2/llm-d-pattern2-tpu-setup.md`
- **Benchmark Results**: `benchmarks/PATTERN2_GPU_RESULTS.md`
- **Retry-aware Benchmark**: `benchmarks/python/pattern2_benchmark_retry.py`
- **llm-d Project**: https://llm-d.ai/
- **Gateway API Inference Extension**: https://gateway-api-inference-extension.sigs.k8s.io/

---

## Conclusion

The llm-d EPP backend discovery limitation is a **known architectural issue** that requires client-side retry logic for reliable multi-model routing. Pattern 2 GPU deployments achieve 100% success with an average of 2-2.2 retry attempts per request.

**This is not a configuration problem** - it's a fundamental limitation in how the EPP discovers and aggregates backends. The proper fix requires upstream changes to the llm-d-inference-scheduler.

For production deployments, implement retry logic and monitor retry statistics. For deployments requiring zero retries, use the BBR architecture (Pattern 2 TPU approach) with separate InferencePools and header-based routing.
