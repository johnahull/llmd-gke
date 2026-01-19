#!/usr/bin/env python3
"""
Async vLLM Benchmark

Main benchmarking tool for measuring TTFT, TPOT, throughput, and latency
of vLLM deployments using async HTTP requests.
"""

import argparse
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List
import yaml

import aiohttp

# Import utility modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils.metrics import (
    calculate_ttft, calculate_tpot, aggregate_metrics, format_metrics_for_display
)
from utils.prompts import get_prompts_for_benchmark
from utils.report_generator import generate_json_report, generate_html_report


class AsyncBenchmarker:
    """Async benchmarker for vLLM inference"""

    def __init__(self, base_url: str, model: str, config: Dict[str, Any]):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.config = config
        self.timeout = aiohttp.ClientTimeout(
            total=config.get('timeout', 300),
            connect=config.get('connect_timeout', 30)
        )

    async def send_completion_request(self, session: aiohttp.ClientSession,
                                      prompt: str, max_tokens: int) -> Dict[str, Any]:
        """Send a completion request and measure TTFT/TPOT

        Args:
            session: aiohttp ClientSession
            prompt: Prompt text
            max_tokens: Maximum tokens to generate

        Returns:
            Dict with timing metrics and response data
        """
        request_start = time.time()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": self.config.get('temperature', 0.7),
            "top_p": self.config.get('top_p', 0.9),
            "stream": False
        }

        try:
            async with session.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=self.timeout
            ) as response:
                first_byte_time = time.time()
                ttft = first_byte_time - request_start

                result = await response.json()
                end_time = time.time()

                # Check for errors
                if response.status != 200 or "error" in result:
                    error_msg = result.get("error", {}).get("message", f"HTTP {response.status}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "total_latency": end_time - request_start
                    }

                # Extract metrics
                total_latency = end_time - request_start
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                # Calculate TPOT
                generation_time = total_latency - ttft
                tpot = generation_time / max(completion_tokens - 1, 1) if completion_tokens > 1 else 0.0

                return {
                    "success": True,
                    "ttft": ttft,
                    "tpot": tpot,
                    "total_latency": total_latency,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "response_text": result.get("choices", [{}])[0].get("text", "")
                }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timeout",
                "total_latency": time.time() - request_start
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "total_latency": time.time() - request_start
            }

    async def run_benchmark(self, num_requests: int, concurrency: int,
                           prompts: List[str], max_tokens: int,
                           warmup_requests: int = 0) -> Dict[str, Any]:
        """Run benchmark with specified concurrency

        Args:
            num_requests: Total number of requests
            concurrency: Maximum concurrent requests
            prompts: List of prompts to use
            max_tokens: Maximum tokens per request
            warmup_requests: Number of warmup requests (not counted in metrics)

        Returns:
            Aggregated metrics dictionary
        """
        print(f"\nRunning benchmark:")
        print(f"  Requests: {num_requests}")
        print(f"  Concurrency: {concurrency}")
        print(f"  Max tokens: {max_tokens}")
        print(f"  Warmup: {warmup_requests}")
        print()

        async with aiohttp.ClientSession() as session:
            # Warmup phase
            if warmup_requests > 0:
                print(f"Warming up with {warmup_requests} requests...")
                warmup_prompts = prompts[:warmup_requests]
                warmup_tasks = [
                    self.send_completion_request(session, prompt, max_tokens)
                    for prompt in warmup_prompts
                ]
                await asyncio.gather(*warmup_tasks)
                print("Warmup complete.\n")

            # Main benchmark
            print("Running main benchmark...")
            semaphore = asyncio.Semaphore(concurrency)

            async def limited_request(prompt):
                async with semaphore:
                    return await self.send_completion_request(session, prompt, max_tokens)

            # Cycle through prompts if needed
            benchmark_prompts = []
            for i in range(num_requests):
                benchmark_prompts.append(prompts[i % len(prompts)])

            # Track progress
            benchmark_start = time.time()
            tasks = [limited_request(prompt) for prompt in benchmark_prompts]

            # Execute with progress tracking
            results = []
            completed = 0
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                completed += 1
                if completed % max(1, num_requests // 10) == 0 or completed == num_requests:
                    elapsed = time.time() - benchmark_start
                    rate = completed / elapsed if elapsed > 0 else 0
                    print(f"  Progress: {completed}/{num_requests} ({completed/num_requests*100:.1f}%) - {rate:.2f} req/s")

            benchmark_end = time.time()
            total_elapsed = benchmark_end - benchmark_start

            print(f"\nBenchmark complete in {total_elapsed:.2f}s")

        # Aggregate metrics
        metrics = aggregate_metrics(results, total_elapsed)
        return metrics


def load_config(config_dir: Path) -> tuple:
    """Load targets and scenarios configuration

    Args:
        config_dir: Path to config directory

    Returns:
        Tuple of (targets, scenarios, defaults)
    """
    with open(config_dir / "targets.yaml") as f:
        targets_config = yaml.safe_load(f)

    with open(config_dir / "test_scenarios.yaml") as f:
        scenarios_config = yaml.safe_load(f)

    return (
        targets_config["targets"],
        scenarios_config["scenarios"],
        targets_config.get("defaults", {})
    )


def main():
    parser = argparse.ArgumentParser(
        description="Async benchmark for vLLM inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run latency benchmark on GKE T4
  python benchmark_async.py --target gke-t4 --scenario latency_benchmark

  # Custom benchmark with specific URL
  python benchmark_async.py --base-url http://localhost:8000 --num-requests 100 --concurrency 10

  # Output to specific file
  python benchmark_async.py --target gke-t4 --output results/my_test.json
        """
    )

    parser.add_argument('--target', choices=['gke-t4', 'tpu-v6e'],
                       help='Target deployment from config')
    parser.add_argument('--scenario',
                       choices=['quick_validation', 'latency_benchmark', 'throughput_benchmark', 'load_test'],
                       help='Test scenario from config')
    parser.add_argument('--base-url', help='Base URL (overrides target config)')
    parser.add_argument('--model', help='Model name (overrides target config)')
    parser.add_argument('--num-requests', type=int, help='Number of requests')
    parser.add_argument('--concurrency', type=int, help='Concurrent requests')
    parser.add_argument('--max-tokens', type=int, help='Max tokens per request')
    parser.add_argument('--output', help='Output file path (.json or .html)')
    parser.add_argument('--html', action='store_true', help='Also generate HTML report')

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    config_dir = script_dir.parent / "config"

    # Load configuration
    targets, scenarios, defaults = load_config(config_dir)

    # Determine base URL and model
    if args.target:
        target_config = targets[args.target]
        base_url = args.base_url or target_config["base_url"]
        model = args.model or target_config["model"]
    else:
        if not args.base_url or not args.model:
            parser.error("Either --target or both --base-url and --model must be specified")
        base_url = args.base_url
        model = args.model

    # Determine test parameters
    if args.scenario:
        scenario_config = scenarios[args.scenario]
        num_requests = args.num_requests or scenario_config["num_requests"]
        concurrency = args.concurrency or scenario_config["concurrency"]

        # Handle max_tokens (can be int or list)
        scenario_max_tokens = scenario_config["max_tokens"]
        if isinstance(scenario_max_tokens, list):
            max_tokens = args.max_tokens or scenario_max_tokens[0]
        else:
            max_tokens = args.max_tokens or scenario_max_tokens

        warmup_requests = scenario_config.get("warmup_requests", 0)

        # Get prompts (use first prompt_tokens value)
        if isinstance(scenario_config.get("prompt_tokens"), list):
            prompt_length = scenario_config["prompt_tokens"][0]
        else:
            prompt_length = scenario_config.get("prompt_tokens", 100)
    else:
        num_requests = args.num_requests or 10
        concurrency = args.concurrency or 1
        max_tokens = args.max_tokens or 100
        warmup_requests = 0
        prompt_length = 100

    # Merge defaults with config
    config = defaults.copy()
    config.update({
        'timeout': defaults.get('timeout', 300),
        'temperature': defaults.get('temperature', 0.7),
        'top_p': defaults.get('top_p', 0.9),
    })

    # Generate prompts
    prompts = get_prompts_for_benchmark(max(num_requests, 20), distribution="mixed")

    # Create benchmarker and run
    print("="*60)
    print("  vLLM Async Benchmark")
    print("="*60)
    print(f"\nTarget: {base_url}")
    print(f"Model: {model}")

    benchmarker = AsyncBenchmarker(base_url, model, config)

    # Run benchmark
    try:
        metrics = asyncio.run(
            benchmarker.run_benchmark(
                num_requests,
                concurrency,
                prompts,
                max_tokens,
                warmup_requests
            )
        )
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        return 1

    # Display results
    print(format_metrics_for_display(metrics))

    # Save results
    if args.output:
        metadata = {
            "target": args.target or "custom",
            "scenario": args.scenario or "custom",
            "base_url": base_url,
            "model": model,
            "num_requests": num_requests,
            "concurrency": concurrency,
            "max_tokens": max_tokens,
        }

        output_path = Path(args.output)

        if args.output.endswith('.json') or not args.html:
            generate_json_report(metrics, args.output, metadata)

        if args.output.endswith('.html') or args.html:
            html_path = str(output_path.with_suffix('.html'))
            generate_html_report(metrics, html_path, metadata)

    return 0 if metrics['mlperf_compliant'] else 1


if __name__ == '__main__':
    sys.exit(main())
