#!/usr/bin/env python3
"""
analysis_latency.py
Analyze latency benchmark data and generate publication-quality tables and graphs.

Usage:
  python analysis_latency.py \
    --input experiments/latency_benchmark.csv \
    --output results/latency_analysis

Requirements:
  pip install pandas numpy matplotlib seaborn scipy
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
ACTIONS = ['search_web', 'read_file', 'transfer_money', 'execute_command', 'delete_database']
MODE_LABELS = {
    'A': 'Baseline (No Policy)',
    'B': 'Centralized (JSON)',
    'C': 'Blockchain (Smart Contract)'
}

# ── Data Loading ────────────────────────────────────────────────────────────────

def load_data(csv_path: str) -> pd.DataFrame:
    """Load latency benchmark CSV."""
    if not Path(csv_path).exists():
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    
    df = pd.read_csv(csv_path)
    
    # Validate required columns
    required = ['mode', 'action', 'total_latency_ms', 'policy_latency_ms']
    for col in required:
        if col not in df.columns:
            print(f"ERROR: Missing required column: {col}", file=sys.stderr)
            sys.exit(1)
    
    print(f"[INFO] Loaded {len(df)} records from {csv_path}")
    return df

# ── Statistical Analysis ────────────────────────────────────────────────────────

def compute_summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute latency statistics for each (mode, action) pair.
    
    FORMULA:
      mean = Σ(latency_i) / N
      median = sorted(latencies)[N/2]
      p95 = sorted(latencies)[ceil(0.95 * N)]
      p99 = sorted(latencies)[ceil(0.99 * N)]
      stdev = sqrt(Σ(latency_i - mean)^2 / (N-1))
      ci_95 = mean ± 1.96 * stdev / sqrt(N)
    
    Returns DataFrame with one row per (mode, action) pair.
    """
    results = []
    
    for mode in MODES:
        for action in ACTIONS:
            subset = df[(df['mode'] == mode) & (df['action'] == action)]['total_latency_ms']
            
            if len(subset) == 0:
                continue
            
            mean = np.mean(subset)
            stdev = np.std(subset, ddof=1)
            sem = stdev / np.sqrt(len(subset))  # Standard Error of the Mean
            
            results.append({
                'mode': mode,
                'mode_label': MODE_LABELS[mode],
                'action': action,
                'count': len(subset),
                'mean_ms': mean,
                'median_ms': np.median(subset),
                'p95_ms': np.percentile(subset, 95),
                'p99_ms': np.percentile(subset, 99),
                'stdev_ms': stdev,
                'sem_ms': sem,
                'min_ms': np.min(subset),
                'max_ms': np.max(subset),
                'ci_lower_95': mean - 1.96 * sem,
                'ci_upper_95': mean + 1.96 * sem,
            })
    
    return pd.DataFrame(results)

def compute_mode_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aggregate latency statistics across all actions for each mode.
    """
    results = []
    
    for mode in MODES:
        subset = df[df['mode'] == mode]['total_latency_ms']
        
        if len(subset) == 0:
            continue
        
        mean = np.mean(subset)
        stdev = np.std(subset, ddof=1)
        sem = stdev / np.sqrt(len(subset))
        
        results.append({
            'mode': mode,
            'mode_label': MODE_LABELS[mode],
            'count': len(subset),
            'mean_ms': mean,
            'median_ms': np.median(subset),
            'p95_ms': np.percentile(subset, 95),
            'p99_ms': np.percentile(subset, 99),
            'stdev_ms': stdev,
            'sem_ms': sem,
            'ci_lower_95': mean - 1.96 * sem,
            'ci_upper_95': mean + 1.96 * sem,
        })
    
    return pd.DataFrame(results)

def compute_policy_latency_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze policy decision latency specifically (excluding intent & execute).
    """
    results = []
    
    for mode in MODES:
        subset = df[df['mode'] == mode]['policy_latency_ms']
        
        if len(subset) == 0:
            continue
        
        mean = np.mean(subset)
        stdev = np.std(subset, ddof=1)
        sem = stdev / np.sqrt(len(subset))
        
        results.append({
            'mode': mode,
            'mode_label': MODE_LABELS[mode],
            'count': len(subset),
            'mean_ms': mean,
            'median_ms': np.median(subset),
            'p95_ms': np.percentile(subset, 95),
            'stdev_ms': stdev,
            'sem_ms': sem,
        })
    
    return pd.DataFrame(results)

def compute_blockchain_overhead(summary_stats: pd.DataFrame) -> dict:
    """
    Calculate blockchain overhead vs. centralized.
    
    FORMULA:
      overhead_pct = (mean_C - mean_B) / mean_B * 100
      overhead_ms = mean_C - mean_B
    """
    mode_means = {}
    for mode in MODES:
        mode_data = summary_stats[summary_stats['mode'] == mode]['mean_ms']
        if len(mode_data) > 0:
            mode_means[mode] = mode_data.mean()
    
    if not all(m in mode_means for m in ['A', 'B', 'C']):
        print("[WARNING] Could not compute all mode means", file=sys.stderr)
        return {}
    
    return {
        'baseline_mean_ms': mode_means['A'],
        'centralized_mean_ms': mode_means['B'],
        'blockchain_mean_ms': mode_means['C'],
        'blockchain_vs_centralized_pct': (mode_means['C'] - mode_means['B']) / mode_means['B'] * 100,
        'blockchain_vs_baseline_pct': (mode_means['C'] - mode_means['A']) / mode_means['A'] * 100,
        'blockchain_overhead_ms': mode_means['C'] - mode_means['B'],
    }

# ── Visualization ──────────────────────────────────────────────────────────────

def plot_latency_by_mode_action(df: pd.DataFrame, output_dir: Path):
    """
    Create heatmap: modes (rows) × actions (columns) = mean latency.
    """
    # Pivot: mode × action
    pivot = df.pivot_table(
        values='total_latency_ms',
        index='mode',
        columns='action',
        aggfunc='mean'
    )
    
    # Reorder for readability
    pivot = pivot.reindex(['A', 'B', 'C'])
    pivot.index = [MODE_LABELS[m] for m in pivot.index]
    
    fig, ax = plt.subplots(figsize=(13, 5))
    sns.heatmap(
        pivot, annot=True, fmt='.1f', cmap='YlOrRd', ax=ax,
        cbar_kws={'label': 'Latency (ms)'}, linewidths=0.5, cbar=True
    )
    ax.set_title('Mean End-to-End Latency by Mode and Action Type', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Action Type', fontsize=12, labelpad=10)
    ax.set_ylabel('Policy Enforcement Mode', fontsize=12, labelpad=10)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_heatmap.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_heatmap.png")

def plot_latency_distribution(df: pd.DataFrame, output_dir: Path):
    """
    Violin plot: distribution of total_latency_ms for each mode.
    """
    fig, ax = plt.subplots(figsize=(11, 6))
    
    df_plot = df.copy()
    df_plot['Mode Label'] = df_plot['mode'].map(MODE_LABELS)
    
    sns.violinplot(
        data=df_plot, x='Mode Label', y='total_latency_ms', 
        palette=['#ff9999', '#ffcc99', '#99ccff'], ax=ax
    )
    ax.set_xlabel('Policy Enforcement Mode', fontsize=12, labelpad=10)
    ax.set_ylabel('Total Latency (ms)', fontsize=12, labelpad=10)
    ax.set_title('Latency Distribution Across Policy Modes', 
                 fontsize=14, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_distribution.png")

def plot_latency_percentiles(summary_stats: pd.DataFrame, output_dir: Path):
    """
    Bar plot: mean, p95, and p99 latencies for each mode.
    """
    mode_summary = summary_stats.groupby('mode')[['mean_ms', 'p95_ms', 'p99_ms']].mean()
    mode_summary.index = [MODE_LABELS[m] for m in mode_summary.index]
    
    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(mode_summary))
    width = 0.25
    
    ax.bar(x - width, mode_summary['mean_ms'], width, label='Mean', color='#a6d854')
    ax.bar(x, mode_summary['p95_ms'], width, label='p95', color='#fc8d59')
    ax.bar(x + width, mode_summary['p99_ms'], width, label='p99', color='#d73027')
    
    ax.set_xlabel('Policy Mode', fontsize=12, labelpad=10)
    ax.set_ylabel('Latency (ms)', fontsize=12, labelpad=10)
    ax.set_title('Latency Percentiles (Mean, p95, p99) by Mode', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(mode_summary.index)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_percentiles.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_percentiles.png")

def plot_latency_by_action(summary_stats: pd.DataFrame, output_dir: Path):
    """
    Grouped bar plot: mean latency for each action across modes.
    """
    fig, ax = plt.subplots(figsize=(13, 6))
    
    actions = ACTIONS
    x = np.arange(len(actions))
    width = 0.25
    
    for i, mode in enumerate(MODES):
        mode_data = summary_stats[summary_stats['mode'] == mode]
        means = [mode_data[mode_data['action'] == a]['mean_ms'].values[0] 
                 if len(mode_data[mode_data['action'] == a]) > 0 else 0 
                 for a in actions]
        ax.bar(x + i*width - width, means, width, label=MODE_LABELS[mode])
    
    ax.set_xlabel('Action Type', fontsize=12, labelpad=10)
    ax.set_ylabel('Mean Latency (ms)', fontsize=12, labelpad=10)
    ax.set_title('Mean Latency by Action Type Across Modes', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(actions, rotation=15, ha='right')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_by_action.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: latency_by_action.png")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Analyze latency benchmark data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analysis_latency.py --input latency_benchmark.csv --output results/
  python analysis_latency.py --input /tmp/latency.csv --output ./analysis/
        """
    )
    parser.add_argument('--input', required=True, help='Path to latency_benchmark.csv')
    parser.add_argument('--output', required=True, help='Output directory for results')
    args = parser.parse_args()
    
    # Setup
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Output directory: {output_dir}")
    
    # Load & analyze
    print("[INFO] Loading data...")
    df = load_data(args.input)
    
    print("[INFO] Computing statistics...")
    summary_stats = compute_summary_stats(df)
    mode_summary = compute_mode_summary(df)
    policy_latency_stats = compute_policy_latency_stats(df)
    blockchain_overhead = compute_blockchain_overhead(summary_stats)
    
    # Export tables
    print("[INFO] Exporting tables...")
    summary_stats.to_csv(output_dir / 'latency_summary_by_action.csv', index=False)
    mode_summary.to_csv(output_dir / 'latency_summary_by_mode.csv', index=False)
    policy_latency_stats.to_csv(output_dir / 'policy_latency_summary.csv', index=False)
    
    # Export overhead metrics
    with open(output_dir / 'blockchain_overhead.json', 'w') as f:
        json.dump(blockchain_overhead, f, indent=2)
    
    # Generate plots
    print("[INFO] Generating visualizations...")
    plot_latency_by_mode_action(df, output_dir)
    plot_latency_distribution(df, output_dir)
    plot_latency_percentiles(summary_stats, output_dir)
    plot_latency_by_action(summary_stats, output_dir)
    
    # Print summary to console
    print("\n" + "="*80)
    print("LATENCY ANALYSIS SUMMARY")
    print("="*80)
    print("\nMode Summary (Across All Actions):")
    print(mode_summary.to_string(index=False))
    print("\n\nBlockchain Overhead Analysis:")
    for key, val in blockchain_overhead.items():
        if isinstance(val, float):
            print(f"  {key}: {val:.2f}")
        else:
            print(f"  {key}: {val}")
    
    print("\n\nDetailed Results exported to:", output_dir)
    print("Files:")
    print("  - latency_summary_by_action.csv")
    print("  - latency_summary_by_mode.csv")
    print("  - policy_latency_summary.csv")
    print("  - blockchain_overhead.json")
    print("  - latency_heatmap.png")
    print("  - latency_distribution.png")
    print("  - latency_percentiles.png")
    print("  - latency_by_action.png")
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
