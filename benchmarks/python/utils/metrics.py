"""Metric calculation utilities for vLLM benchmarks

This module provides functions for calculating TTFT, TPOT, throughput, percentiles,
and checking MLPerf compliance.
"""

import time
from typing import List, Dict, Any, Optional
import numpy as np


def calculate_ttft(request_start_time: float, first_token_time: float) -> float:
    """Calculate Time to First Token (TTFT)

    TTFT includes request queueing time, prompt processing (prefill) time,
    and network latency.

    Args:
        request_start_time: Timestamp when request was sent
        first_token_time: Timestamp when first token was received

    Returns:
        TTFT in seconds
    """
    return first_token_time - request_start_time


def calculate_tpot(generation_start_time: float, generation_end_time: float,
                   num_tokens: int) -> float:
    """Calculate Time Per Output Token (TPOT)

    TPOT measures the average time to generate each output token, excluding TTFT.

    Args:
        generation_start_time: Timestamp when first token was received
        generation_end_time: Timestamp when generation completed
        num_tokens: Number of tokens generated (excluding first token)

    Returns:
        TPOT in seconds per token
    """
    if num_tokens <= 1:
        return 0.0

    generation_time = generation_end_time - generation_start_time
    # Exclude first token from TPOT calculation
    return generation_time / max(num_tokens - 1, 1)


def calculate_percentiles(data: List[float],
                          percentiles: List[int] = [50, 90, 95, 99]) -> Dict[str, float]:
    """Calculate percentile values

    Args:
        data: List of numerical values
        percentiles: List of percentile values to calculate (0-100)

    Returns:
        Dictionary mapping percentile names to values
    """
    if not data:
        return {f"p{p}": 0.0 for p in percentiles}

    result = {}
    for p in percentiles:
        result[f"p{p}"] = float(np.percentile(data, p))

    return result


def calculate_throughput(total_tokens: int, total_time: float) -> float:
    """Calculate throughput in tokens per second

    Args:
        total_tokens: Total number of tokens generated
        total_time: Total time elapsed in seconds

    Returns:
        Tokens per second
    """
    if total_time <= 0:
        return 0.0

    return total_tokens / total_time


def check_mlperf_compliance(ttft: float, tpot: float,
                            interactive: bool = False) -> bool:
    """Check if metrics meet MLPerf 2025-2026 standards

    MLPerf Standard Workloads:
    - TTFT ≤ 2.0 seconds (p95)
    - TPOT ≤ 100 milliseconds (p95)

    MLPerf Interactive Workloads (aggressive):
    - TTFT ≤ 0.5 seconds (p95)
    - TPOT ≤ 30 milliseconds (p95)

    Args:
        ttft: Time to First Token in seconds (p95)
        tpot: Time Per Output Token in seconds (p95)
        interactive: Whether to use interactive (aggressive) thresholds

    Returns:
        True if both metrics meet MLPerf standards
    """
    if interactive:
        ttft_threshold = 0.5  # seconds
        tpot_threshold = 0.030  # seconds (30ms)
    else:
        ttft_threshold = 2.0  # seconds
        tpot_threshold = 0.100  # seconds (100ms)

    return ttft <= ttft_threshold and tpot <= tpot_threshold


def aggregate_metrics(request_results: List[Dict[str, Any]],
                      total_elapsed_time: Optional[float] = None) -> Dict[str, Any]:
    """Aggregate individual request results into summary statistics

    Args:
        request_results: List of individual request result dictionaries
        total_elapsed_time: Total time for all requests (for throughput calculation)

    Returns:
        Dictionary containing aggregated metrics
    """
    if not request_results:
        return {
            "num_requests": 0,
            "num_successful": 0,
            "num_failed": 0,
            "error_rate": 1.0,
            "success_rate": 0.0,
            "ttft_p50": 0.0,
            "ttft_p95": 0.0,
            "tpot_p50": 0.0,
            "tpot_p95": 0.0,
            "throughput_tokens_per_sec": 0.0,
            "mlperf_compliant": False
        }

    # Separate successful and failed requests
    successful = [r for r in request_results if r.get("success", False)]
    failed = len(request_results) - len(successful)

    if not successful:
        return {
            "num_requests": len(request_results),
            "num_successful": 0,
            "num_failed": failed,
            "error_rate": 1.0,
            "success_rate": 0.0,
            "ttft_p50": 0.0,
            "ttft_p95": 0.0,
            "tpot_p50": 0.0,
            "tpot_p95": 0.0,
            "throughput_tokens_per_sec": 0.0,
            "mlperf_compliant": False
        }

    # Extract metrics from successful requests
    ttfts = [r["ttft"] for r in successful if "ttft" in r]
    tpots = [r["tpot"] for r in successful if "tpot" in r]
    latencies = [r["total_latency"] for r in successful if "total_latency" in r]
    prompt_tokens = sum(r.get("prompt_tokens", 0) for r in successful)
    completion_tokens = sum(r.get("completion_tokens", 0) for r in successful)
    total_tokens = prompt_tokens + completion_tokens

    # Calculate percentiles
    ttft_percentiles = calculate_percentiles(ttfts)
    tpot_percentiles = calculate_percentiles(tpots)
    latency_percentiles = calculate_percentiles(latencies)

    # Calculate throughput
    if total_elapsed_time and total_elapsed_time > 0:
        throughput_tokens_per_sec = total_tokens / total_elapsed_time
        throughput_requests_per_sec = len(successful) / total_elapsed_time
    else:
        # Use average latency if total time not provided
        avg_latency = np.mean(latencies) if latencies else 1.0
        throughput_tokens_per_sec = (completion_tokens / len(successful)) / avg_latency
        throughput_requests_per_sec = 1.0 / avg_latency

    # Check MLPerf compliance
    mlperf_compliant = check_mlperf_compliance(
        ttft_percentiles["p95"],
        tpot_percentiles["p95"],
        interactive=False
    )

    mlperf_interactive = check_mlperf_compliance(
        ttft_percentiles["p95"],
        tpot_percentiles["p95"],
        interactive=True
    )

    # Build result dictionary
    result = {
        # Request counts
        "num_requests": len(request_results),
        "num_successful": len(successful),
        "num_failed": failed,
        "error_rate": failed / len(request_results),
        "success_rate": len(successful) / len(request_results),

        # TTFT metrics
        "ttft_mean": float(np.mean(ttfts)) if ttfts else 0.0,
        "ttft_median": float(np.median(ttfts)) if ttfts else 0.0,
        "ttft_min": float(np.min(ttfts)) if ttfts else 0.0,
        "ttft_max": float(np.max(ttfts)) if ttfts else 0.0,
        "ttft_p50": ttft_percentiles["p50"],
        "ttft_p90": ttft_percentiles["p90"],
        "ttft_p95": ttft_percentiles["p95"],
        "ttft_p99": ttft_percentiles["p99"],

        # TPOT metrics
        "tpot_mean": float(np.mean(tpots)) if tpots else 0.0,
        "tpot_median": float(np.median(tpots)) if tpots else 0.0,
        "tpot_min": float(np.min(tpots)) if tpots else 0.0,
        "tpot_max": float(np.max(tpots)) if tpots else 0.0,
        "tpot_p50": tpot_percentiles["p50"],
        "tpot_p90": tpot_percentiles["p90"],
        "tpot_p95": tpot_percentiles["p95"],
        "tpot_p99": tpot_percentiles["p99"],

        # Latency metrics
        "latency_mean": float(np.mean(latencies)) if latencies else 0.0,
        "latency_median": float(np.median(latencies)) if latencies else 0.0,
        "latency_min": float(np.min(latencies)) if latencies else 0.0,
        "latency_max": float(np.max(latencies)) if latencies else 0.0,
        "latency_p50": latency_percentiles["p50"],
        "latency_p90": latency_percentiles["p90"],
        "latency_p95": latency_percentiles["p95"],
        "latency_p99": latency_percentiles["p99"],

        # Token metrics
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "avg_prompt_tokens": prompt_tokens / len(successful),
        "avg_completion_tokens": completion_tokens / len(successful),
        "avg_total_tokens": total_tokens / len(successful),

        # Throughput metrics
        "throughput_tokens_per_sec": throughput_tokens_per_sec,
        "throughput_requests_per_sec": throughput_requests_per_sec,

        # MLPerf compliance
        "mlperf_compliant": mlperf_compliant,
        "mlperf_interactive": mlperf_interactive,
        "mlperf_ttft_threshold": 2.0,
        "mlperf_tpot_threshold": 0.100,
        "mlperf_ttft_threshold_interactive": 0.5,
        "mlperf_tpot_threshold_interactive": 0.030,
    }

    return result


def format_metrics_for_display(metrics: Dict[str, Any]) -> str:
    """Format metrics dictionary for console display

    Args:
        metrics: Aggregated metrics dictionary

    Returns:
        Formatted string for console output
    """
    lines = [
        "\n" + "="*60,
        "  Benchmark Results",
        "="*60,
        "",
        f"Requests: {metrics['num_successful']}/{metrics['num_requests']} succeeded",
        f"Success Rate: {metrics['success_rate']*100:.1f}%",
        "",
        "Time to First Token (TTFT):",
        f"  Mean: {metrics['ttft_mean']*1000:.1f}ms",
        f"  p50:  {metrics['ttft_p50']*1000:.1f}ms",
        f"  p95:  {metrics['ttft_p95']*1000:.1f}ms",
        f"  p99:  {metrics['ttft_p99']*1000:.1f}ms",
        "",
        "Time Per Output Token (TPOT):",
        f"  Mean: {metrics['tpot_mean']*1000:.1f}ms",
        f"  p50:  {metrics['tpot_p50']*1000:.1f}ms",
        f"  p95:  {metrics['tpot_p95']*1000:.1f}ms",
        f"  p99:  {metrics['tpot_p99']*1000:.1f}ms",
        "",
        "End-to-End Latency:",
        f"  Mean: {metrics['latency_mean']:.3f}s",
        f"  p50:  {metrics['latency_p50']:.3f}s",
        f"  p95:  {metrics['latency_p95']:.3f}s",
        f"  p99:  {metrics['latency_p99']:.3f}s",
        "",
        "Throughput:",
        f"  {metrics['throughput_tokens_per_sec']:.2f} tokens/sec",
        f"  {metrics['throughput_requests_per_sec']:.2f} requests/sec",
        "",
        "Token Counts:",
        f"  Total: {metrics['total_tokens']} ({metrics['avg_total_tokens']:.1f} avg/request)",
        f"  Prompt: {metrics['total_prompt_tokens']} ({metrics['avg_prompt_tokens']:.1f} avg)",
        f"  Completion: {metrics['total_completion_tokens']} ({metrics['avg_completion_tokens']:.1f} avg)",
        "",
        "MLPerf Compliance:",
        f"  Standard: {'✓ PASS' if metrics['mlperf_compliant'] else '✗ FAIL'}",
        f"    TTFT p95 {metrics['ttft_p95']:.3f}s (threshold: {metrics['mlperf_ttft_threshold']:.1f}s)",
        f"    TPOT p95 {metrics['tpot_p95']*1000:.1f}ms (threshold: {metrics['mlperf_tpot_threshold']*1000:.0f}ms)",
        f"  Interactive: {'✓ PASS' if metrics['mlperf_interactive'] else '✗ FAIL'}",
        f"    TTFT p95 {metrics['ttft_p95']:.3f}s (threshold: {metrics['mlperf_ttft_threshold_interactive']:.1f}s)",
        f"    TPOT p95 {metrics['tpot_p95']*1000:.1f}ms (threshold: {metrics['mlperf_tpot_threshold_interactive']*1000:.0f}ms)",
        "="*60,
        ""
    ]

    return "\n".join(lines)
