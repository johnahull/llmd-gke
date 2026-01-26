# Custom Helm Configurations for llm-d Patterns

This directory contains custom Helm configurations for deploying Patterns 1, 2, and 3 with llm-d.

## Setup

### 1. Clone llm-d Repository

From the root of this repository:

```bash
git clone https://github.com/llm-d/llm-d.git
```

### 2. Copy Custom Configurations

```bash
# Copy pattern overrides
cp helm-configs/pattern-overrides/*.yaml \
   llm-d/guides/inference-scheduling/ms-inference-scheduling/

# Copy modified helmfile
cp helm-configs/helmfile.yaml.gotmpl \
   llm-d/guides/inference-scheduling/
```

### 3. Deploy Pattern

```bash
cd llm-d/guides/inference-scheduling

# For GPU Pattern 1
helmfile apply -e gke -n llm-d --selector release=pattern1

# For GPU Pattern 3
helmfile apply -e gke -n llm-d --selector release=pattern3

# For TPU Pattern 1
helmfile apply -e gke_tpu -n llm-d --selector release=pattern1

# For TPU Pattern 2
helmfile apply -e gke_tpu -n llm-d --selector release=pattern2
```

## Files

- `helmfile.yaml.gotmpl` - Modified helmfile with pattern conditionals
- `pattern-overrides/pattern1-overrides.yaml` - Pattern 1 GPU configuration
- `pattern-overrides/pattern1-tpu-overrides.yaml` - Pattern 1 TPU configuration
- `pattern-overrides/pattern2-gpu-overrides.yaml` - Pattern 2 GPU multi-model configuration
- `pattern-overrides/pattern2-tpu-overrides.yaml` - Pattern 2 TPU configuration
- `pattern-overrides/pattern3-gpu-overrides.yaml` - Pattern 3 GPU configuration
- `pattern-overrides/pattern3-tpu-overrides.yaml` - Pattern 3 TPU caching scale-out configuration

## Modifications

### helmfile.yaml.gotmpl

1. **GKE Monitoring** (line 79): Disabled temporarily
2. **TPU Patterns** (lines 110-116): Added pattern1/pattern2 conditionals
3. **GPU Patterns** (lines 125-129): Added pattern1/pattern3 conditionals
