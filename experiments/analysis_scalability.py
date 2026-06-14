#!/usr/bin/env python3
"""
analysis_scalability.py
Analyze scalability test data: throughput, latency under load, failure rates.

Usage:
  python analysis_scalability.py \
    --input experiments/scalability_test.csv \
    --output results/scalability_analysis

Requirements:
  pip install pandas numpy matplotlib seaborn
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
from pathlib import Path
import json
import sys

# ── Configuration ──────────────────────────────────────────────────────────────

MODES = ['A', 'B', 'C']
MODE_LABELS = {
    'A': 'Baseline',
    'B': 'Centralized',
    'C': 'Blockchain'
}
CONCURRENCY_LEVELS = [1, 5, 10, 25, 50]

# ── Data Loading ────────────────────────────────────────────────────────────────

def load_data(csv_path: str) -> pd.DataFrame:
    """Load scalability test CSV."""
    if not Path(csv_path).exists():
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    
    df = pd.read_csv(csv_path)
    print(f"[INFO] Loaded {len(df)} records from {csv_path}")
    return df

# ── Statistical Analysis ────────────────────────────────────────────────────────

def compute_throughput_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute throughput (RPS) and latency for each (mode, concurrency) pair.
    
    FORMULA:
      throughput_rps = completed_requests / elapsed_seconds
      p95_latency_ms = percentile(latencies, 95)
      p99_latency_ms = percentile(latencies, 99)
    """
    results = []
    
    for mode in MODES:
        for concurrency in CONCURRENCY_LEVELS:
            subset = df[(df['mode'] == mode) & 
                       (df['concurrency_level'] == concurrency)]
            
            if len(subset) == 0:
                continue
            
            # Filter successful requests only
            successful = subset[subset['success'] == 1]
            failed = subset[subset['success'] == 0]
            
            if len(successful) == 0:
                continue
            
            latencies = successful['latency_ms'].values
            
            # Compute elapsed time from first to last request
            min_time = successful['submitted_time_ms'].min()
            max_time = successful['completed_time_ms'].max()
            elapsed_sec = (max_time - min_time) / 1000.0
            elapsed_sec = max(elapsed_sec, 0.001)  # Avoid division by zero
            
            throughput_rps = len(successful) / elapsed_sec
            
            results.append({
                'mode': mode,
                'mode_label': MODE_LABELS[mode],
                'concurrency_level': int(concurrency),
                'n_submitted': len(subset),
                'n_completed': len(successful),
                'n_failed': len(failed),
                'failure_rate_pct': (len(failed) / len(subset) * 100) if len(subset) > 0 else 0,
                'throughput_rps': throughput_rps,
                'mean_latency_ms': np.mean(latencies),
                'median_latency_ms': np.median(latencies),
                'p95_latency_ms': np.percentile(latencies, 95),
                'p99_latency_ms': np.percentile(latencies, 99),
                'stdev_latency_ms': np.std(latencies, ddof=1),
                'min_latency_ms': np.min(latencies),
                'max_latency_ms': np.max(latencies),
            })
    
    return pd.DataFrame(results)

def compute_degradation_factor(throughput_metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Compute latency degradation factor vs. baseline (concurrency=1).
    
    FORMULA:
      degradation_factor = latency_at_N / latency_at_1
      degradation_pct = (degradation_factor - 1) * 100
    """
    results = []
    
    for mode in MODES:
        mode_data = throughput_metrics[throughput_metrics['mode'] == mode]
        baseline = mode_data[mode_data['concurrency_level'] == 1]
        
        if len(baseline) == 0:
            continue
        
        baseline_p95 = baseline['p95_latency_ms'].values[0]
        baseline_mean = baseline['mean_latency_ms'].values[0]
        
        for _, row in mode_data.iterrows():
            if row['concurrency_level'] == 1:
                degradation_factor = 1.0
                degradation_pct = 0.0
            else:
                degradation_factor = row['p95_latency_ms'] / baseline_p95
                degradation_pct = (degradation_factor - 1) * 100
            
            throughput_ratio = row['throughput_rps'] / baseline['throughput_rps'].values[0]
            
            results.append({
                'mode': row['mode'],
                'mode_label': row['mode_label'],
                'concurrency_level': int(row['concurrency_level']),
                'throughput_rps': row['throughput_rps'],
                'p95_latency_ms': row['p95_latency_ms'],
                'degradation_factor': degradation_factor,
                'degradation_pct': degradation_pct,
                'throughput_ratio': throughput_ratio,
            })
    
    return pd.DataFrame(results)

# ── Visualization ──────────────────────────────────────────────────────────────

def plot_throughput_vs_concurrency(throughput_metrics: pd.DataFrame, output_dir: Path):
    """
    Line plot: throughput (RPS) vs. concurrency level for each mode.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for mode in MODES:
        mode_data = throughput_metrics[
            (throughput_metrics['mode'] == mode) &
            (throughput_metrics['failure_rate_pct'] < 10)  # Filter major failures
        ].sort_values('concurrency_level')
        
        if len(mode_data) == 0:
            continue
        
        ax.plot(mode_data['concurrency_level'], mode_data['throughput_rps'],
                marker='o', label=MODE_LABELS[mode], linewidth=2.5, markersize=8)
    
    ax.set_xlabel('Concurrency Level (# parallel threads)', fontsize=12, labelpad=10)
    ax.set_ylabel('Throughput (requests/second)', fontsize=12, labelpad=10)
    ax.set_title('Throughput Scaling Under Concurrent Load', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(CONCURRENCY_LEVELS)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'throughput_vs_concurrency.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: throughput_vs_concurrency.png")

def plot_latency_vs_concurrency(throughput_metrics: pd.DataFrame, output_dir: Path):
    """
    Line plot: p95 latency vs. concurrency for each mode.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for mode in MODES:
        mode_data = throughput_metrics[
            (throughput_metrics['mode'] == mode) &
            (throughput_metrics['failure_rate_pct'] < 10)
        ].sort_values('concurrency_level')
        
        if len(mode_data) == 0:
            continue
        
        ax.plot(mode_data['concurrency_level'], mode_data['p95_latency_ms'],
                marker='s', label=MODE_LABELS[mode], linewidth=2.5, markersize=8)
    
    ax.set_xlabel('Concurrency Level (# parallel threads)', fontsize=12, labelpad=10)
    ax.set_ylabel('p95 Latency (ms)', fontsize=12, labelpad=10)
    ax.set_title('Latency Degradation Under Concurrent Load (p95)', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(CONCURRENCY_LEVELS)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_vs_concurrency.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_vs_concurrency.png")

def plot_degradation_factor(degradation: pd.DataFrame, output_dir: Path):
    """
    Bar chart: degradation factor vs. baseline for each concurrency level.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Filter out concurrency=1 (baseline is always 1.0)
    degradation_plot = degradation[degradation['concurrency_level'] > 1]
    
    concurrency_levels = sorted(degradation_plot['concurrency_level'].unique())
    x = np.arange(len(concurrency_levels))
    width = 0.25
    
    for i, mode in enumerate(MODES):
        mode_data = degradation_plot[degradation_plot['mode'] == mode].sort_values('concurrency_level')
        factors = mode_data['degradation_factor'].values
        ax.bar(x + i*width - width, factors, width, label=MODE_LABELS[mode], 
               edgecolor='black', linewidth=1.5)
    
    ax.set_xlabel('Concurrency Level', fontsize=12, labelpad=10)
    ax.set_ylabel('Latency Degradation Factor (vs. baseline concurrency=1)', fontsize=12, labelpad=10)
    ax.set_title('Latency Degradation Factor (p95)', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x + width)
    ax.set_xticklabels([f'{int(c)}' for c in concurrency_levels])
    ax.axhline(y=2.0, color='r', linestyle='--', alpha=0.5, linewidth=2, label='2x degradation')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'degradation_factor.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: degradation_factor.png")

def plot_mean_vs_p95_latency(throughput_metrics: pd.DataFrame, output_dir: Path):
    """
    Grouped bar plot: mean vs. p95 latency for each mode at each concurrency level.
    """
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Prepare data by concurrency level
    for concurrency in CONCURRENCY_LEVELS:
        subset = throughput_metrics[throughput_metrics['concurrency_level'] == concurrency]
        
        if len(subset) == 0:
            continue
        
        x = np.arange(len(MODES))
        width = 0.35
        
        means = [subset[subset['mode'] == m]['mean_latency_ms'].values[0] 
                if len(subset[subset['mode'] == m]) > 0 else 0 for m in MODES]
        p95s = [subset[subset['mode'] == m]['p95_latency_ms'].values[0]
               if len(subset[subset['mode'] == m]) > 0 else 0 for m in MODES]
    
    # Create subplots for each concurrency level
    fig, axes = plt.subplots(1, len(CONCURRENCY_LEVELS), figsize=(16, 5))
    
    for idx, concurrency in enumerate(CONCURRENCY_LEVELS):
        ax = axes[idx] if len(CONCURRENCY_LEVELS) > 1 else axes
        subset = throughput_metrics[throughput_metrics['concurrency_level'] == concurrency]
        
        if len(subset) == 0:
            continue
        
        x = np.arange(len(MODES))
        width = 0.35
        
        means = [subset[subset['mode'] == m]['mean_latency_ms'].values[0]
                if len(subset[subset['mode'] == m]) > 0 else 0 for m in MODES]
        p95s = [subset[subset['mode'] == m]['p95_latency_ms'].values[0]
               if len(subset[subset['mode'] == m]) > 0 else 0 for m in MODES]
        
        ax.bar(x - width/2, means, width, label='Mean', color='#a6d854', edgecolor='black', linewidth=1)
        ax.bar(x + width/2, p95s, width, label='p95', color='#fc8d59', edgecolor='black', linewidth=1)
        
        ax.set_ylabel('Latency (ms)', fontsize=10)
        ax.set_title(f'Concurrency: {concurrency}', fontsize=11, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m][:7] for m in MODES], fontsize=9)
        ax.grid(axis='y', alpha=0.3)
        
        if idx == 0:
            ax.legend(fontsize=10)
    
    fig.suptitle('Latency (Mean vs. p95) Across Modes and Concurrency Levels', 
                fontsize=14, fontweight='bold', y=1.00)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_mean_vs_p95.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_mean_vs_p95.png")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Analyze scalability test data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analysis_scalability.py --input scalability_test.csv --output results/
  python analysis_scalability.py --input /tmp/scalability.csv --output ./analysis/
        """
    )
    parser.add_argument('--input', required=True, help='Path to scalability_test.csv')
    parser.add_argument('--output', required=True, help='Output directory for results')
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Output directory: {output_dir}")
    
    # Load & analyze
    print("[INFO] Loading data...")
    df = load_data(args.input)
    
    print("[INFO] Computing metrics...")
    throughput_metrics = compute_throughput_metrics(df)
    degradation = compute_degradation_factor(throughput_metrics)
    
    # Export tables
    print("[INFO] Exporting tables...")
    throughput_metrics.to_csv(output_dir / 'throughput_metrics.csv', index=False)
    degradation.to_csv(output_dir / 'degradation_factor.csv', index=False)
    
    # Generate plots
    print("[INFO] Generating visualizations...")
    plot_throughput_vs_concurrency(throughput_metrics, output_dir)
    plot_latency_vs_concurrency(throughput_metrics, output_dir)
    plot_degradation_factor(degradation, output_dir)
    plot_mean_vs_p95_latency(throughput_metrics, output_dir)
    
    # Print summary to console
    print("\n" + "="*80)
    print("SCALABILITY ANALYSIS SUMMARY")
    print("="*80)
    print("\nThroughput Metrics:")
    print(throughput_metrics.to_string(index=False))
    
    print("\n\nDegradation Analysis:")
    print(degradation.to_string(index=False))
    
    print("\n\nDetailed Results exported to:", output_dir)
    print("Files:")
    print("  - throughput_metrics.csv")
    print("  - degradation_factor.csv")
    print("  - throughput_vs_concurrency.png")
    print("  - latency_vs_concurrency.png")
    print("  - degradation_factor.png")
    print("  - latency_mean_vs_p95.png")
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
