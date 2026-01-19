"""Report generation utilities for benchmark results

This module provides functions to generate JSON and HTML reports from benchmark metrics.
"""

import json
from typing import Dict, Any
from datetime import datetime
from pathlib import Path


def generate_json_report(metrics: Dict[str, Any], output_path: str,
                        metadata: Dict[str, Any] = None) -> None:
    """Generate JSON report from metrics

    Args:
        metrics: Aggregated metrics dictionary
        output_path: Path to save JSON file
        metadata: Optional metadata to include (target, scenario, timestamp, etc.)
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
        "metrics": metrics
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"JSON report saved to: {output_path}")


def generate_html_report(metrics: Dict[str, Any], output_path: str,
                         metadata: Dict[str, Any] = None) -> None:
    """Generate HTML report from metrics

    Args:
        metrics: Aggregated metrics dictionary
        output_path: Path to save HTML file
        metadata: Optional metadata to include
    """
    # Build metadata section
    metadata_html = ""
    if metadata:
        metadata_html = "<div class='metadata'><h2>Test Configuration</h2><ul>"
        for key, value in metadata.items():
            metadata_html += f"<li><strong>{key}:</strong> {value}</li>"
        metadata_html += "</ul></div>"

    # Determine pass/fail status
    mlperf_status = "✓ PASS" if metrics.get('mlperf_compliant', False) else "✗ FAIL"
    mlperf_class = "pass" if metrics.get('mlperf_compliant', False) else "fail"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>vLLM Benchmark Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
        }}
        .metadata {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .metadata ul {{
            list-style: none;
            padding: 0;
        }}
        .metadata li {{
            margin: 5px 0;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            border-left: 4px solid #007bff;
        }}
        .metric-card h3 {{
            margin-top: 0;
            color: #007bff;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
        }}
        .stats-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .stats-table th, .stats-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        .stats-table th {{
            background-color: #007bff;
            color: white;
        }}
        .stats-table tr:hover {{
            background-color: #f5f5f5;
        }}
        .pass {{
            color: #28a745;
            font-weight: bold;
        }}
        .fail {{
            color: #dc3545;
            font-weight: bold;
        }}
        .mlperf-section {{
            background-color: #e7f3ff;
            padding: 20px;
            border-radius: 5px;
            border-left: 4px solid #007bff;
            margin: 20px 0;
        }}
        .timestamp {{
            color: #666;
            font-style: italic;
            margin-top: 30px;
            text-align: right;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>vLLM Benchmark Report</h1>

        {metadata_html}

        <h2>Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Success Rate</h3>
                <div class="metric-value">{metrics.get('success_rate', 0) * 100:.1f}%</div>
                <div class="metric-label">{metrics.get('num_successful', 0)}/{metrics.get('num_requests', 0)} requests</div>
            </div>
            <div class="metric-card">
                <h3>TTFT (p50)</h3>
                <div class="metric-value">{metrics.get('ttft_p50', 0) * 1000:.0f}ms</div>
                <div class="metric-label">Time to First Token</div>
            </div>
            <div class="metric-card">
                <h3>TPOT (p50)</h3>
                <div class="metric-value">{metrics.get('tpot_p50', 0) * 1000:.0f}ms</div>
                <div class="metric-label">Time Per Output Token</div>
            </div>
            <div class="metric-card">
                <h3>Throughput</h3>
                <div class="metric-value">{metrics.get('throughput_tokens_per_sec', 0):.0f}</div>
                <div class="metric-label">tokens/second</div>
            </div>
        </div>

        <div class="mlperf-section">
            <h2>MLPerf Compliance</h2>
            <p><strong>Standard Workload:</strong> <span class="{mlperf_class}">{mlperf_status}</span></p>
            <ul>
                <li>TTFT p95: {metrics.get('ttft_p95', 0):.3f}s (threshold: 2.0s) - <strong>{'✓' if metrics.get('ttft_p95', 999) <= 2.0 else '✗'}</strong></li>
                <li>TPOT p95: {metrics.get('tpot_p95', 0) * 1000:.1f}ms (threshold: 100ms) - <strong>{'✓' if metrics.get('tpot_p95', 999) <= 0.1 else '✗'}</strong></li>
            </ul>
        </div>

        <h2>Latency Details</h2>
        <table class="stats-table">
            <tr>
                <th>Metric</th>
                <th>Mean</th>
                <th>p50</th>
                <th>p90</th>
                <th>p95</th>
                <th>p99</th>
            </tr>
            <tr>
                <td><strong>TTFT</strong></td>
                <td>{metrics.get('ttft_mean', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('ttft_p50', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('ttft_p90', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('ttft_p95', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('ttft_p99', 0) * 1000:.1f}ms</td>
            </tr>
            <tr>
                <td><strong>TPOT</strong></td>
                <td>{metrics.get('tpot_mean', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('tpot_p50', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('tpot_p90', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('tpot_p95', 0) * 1000:.1f}ms</td>
                <td>{metrics.get('tpot_p99', 0) * 1000:.1f}ms</td>
            </tr>
            <tr>
                <td><strong>End-to-End</strong></td>
                <td>{metrics.get('latency_mean', 0):.3f}s</td>
                <td>{metrics.get('latency_p50', 0):.3f}s</td>
                <td>{metrics.get('latency_p90', 0):.3f}s</td>
                <td>{metrics.get('latency_p95', 0):.3f}s</td>
                <td>{metrics.get('latency_p99', 0):.3f}s</td>
            </tr>
        </table>

        <h2>Token Statistics</h2>
        <table class="stats-table">
            <tr>
                <th>Type</th>
                <th>Total</th>
                <th>Average per Request</th>
            </tr>
            <tr>
                <td>Prompt Tokens</td>
                <td>{metrics.get('total_prompt_tokens', 0):,}</td>
                <td>{metrics.get('avg_prompt_tokens', 0):.1f}</td>
            </tr>
            <tr>
                <td>Completion Tokens</td>
                <td>{metrics.get('total_completion_tokens', 0):,}</td>
                <td>{metrics.get('avg_completion_tokens', 0):.1f}</td>
            </tr>
            <tr>
                <td><strong>Total</strong></td>
                <td><strong>{metrics.get('total_tokens', 0):,}</strong></td>
                <td><strong>{metrics.get('avg_total_tokens', 0):.1f}</strong></td>
            </tr>
        </table>

        <h2>Throughput</h2>
        <ul>
            <li><strong>Tokens/second:</strong> {metrics.get('throughput_tokens_per_sec', 0):.2f}</li>
            <li><strong>Requests/second:</strong> {metrics.get('throughput_requests_per_sec', 0):.2f}</li>
        </ul>

        <div class="timestamp">
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"HTML report saved to: {output_path}")


def generate_comparison_report(gpu_results: Dict[str, Any],
                               tpu_results: Dict[str, Any],
                               output_path: str) -> None:
    """Generate comparison report for GPU vs TPU results

    Args:
        gpu_results: GPU benchmark metrics
        tpu_results: TPU benchmark metrics
        output_path: Path to save comparison report (JSON or HTML)
    """
    comparison = {
        "timestamp": datetime.now().isoformat(),
        "gpu": gpu_results,
        "tpu": tpu_results,
        "comparison": {
            "ttft_ratio": tpu_results.get('ttft_p50', 1) / gpu_results.get('ttft_p50', 1),
            "tpot_ratio": tpu_results.get('tpot_p50', 1) / gpu_results.get('tpot_p50', 1),
            "throughput_ratio": tpu_results.get('throughput_tokens_per_sec', 1) / gpu_results.get('throughput_tokens_per_sec', 1),
            "latency_ratio": tpu_results.get('latency_p50', 1) / gpu_results.get('latency_p50', 1),
        }
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_path.endswith('.json'):
        with open(output_file, 'w') as f:
            json.dump(comparison, f, indent=2)
        print(f"Comparison report saved to: {output_path}")
    else:
        # Generate HTML comparison (simplified version)
        print("HTML comparison reports not yet implemented. Use JSON format.")


__all__ = [
    'generate_json_report',
    'generate_html_report',
    'generate_comparison_report',
]
