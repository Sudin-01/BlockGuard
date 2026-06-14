#!/usr/bin/env python3
"""
BlockGuard Visualization Generator
Generates 4 publication-quality figures from experiment results
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Configure style for publication quality
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Create results directory
results_dir = Path('results/figures')
results_dir.mkdir(parents=True, exist_ok=True)

# Load data
df = pd.read_csv('experiments/experiment_results.csv')

print("=" * 70)
print("BLOCKGUARD FIGURE GENERATION")
print("=" * 70)

# ============================================================================
# FIGURE 1: Latency Heatmap (Mode × Action)
# ============================================================================
print("\n[1/4] Generating Latency Heatmap (Mode × Action)...")

pivot_data = df.pivot_table(
    values='latency_ms',
    index='action',
    columns='system',
    aggfunc='mean'
)

fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(
    pivot_data,
    annot=True,
    fmt='.1f',
    cmap='RdYlGn_r',
    cbar_kws={'label': 'Latency (ms)'},
    linewidths=0.5,
    ax=ax,
    vmin=300,
    vmax=420
)
ax.set_title('End-to-End Latency by Policy Mode and Action', fontsize=14, fontweight='bold')
ax.set_xlabel('Policy Mode', fontsize=12, fontweight='bold')
ax.set_ylabel('Action Type', fontsize=12, fontweight='bold')
ax.set_xticklabels(['Baseline (No Policy)', 'Centralized (JSON)', 'Blockchain (Smart Contract)'])
plt.tight_layout()
plt.savefig(results_dir / 'latency_heatmap.png', dpi=300, bbox_inches='tight')
print(f"   ✓ Saved: {results_dir / 'latency_heatmap.png'}")
plt.close()

# ============================================================================
# FIGURE 2: Accuracy Bar Chart (A vs. B vs. C)
# ============================================================================
print("\n[2/4] Generating Accuracy Bar Chart...")

accuracy_data = []
for mode in ['A', 'B', 'C']:
    subset = df[df['system'] == mode]
    accuracy = (subset['is_correct'].sum() / len(subset)) * 100
    accuracy_data.append(accuracy)

fig, ax = plt.subplots(figsize=(10, 6))
modes_label = ['Baseline\n(No Policy)', 'Centralized\n(JSON Dict)', 'Blockchain\n(Smart Contract)']
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
bars = ax.bar(modes_label, accuracy_data, color=colors, edgecolor='black', linewidth=1.5, alpha=0.8)

# Add value labels on bars
for i, (bar, val) in enumerate(zip(bars, accuracy_data)):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
            f'{val:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')

ax.set_ylabel('Authorization Accuracy (%)', fontsize=12, fontweight='bold')
ax.set_title('Authorization Accuracy by Policy Mode', fontsize=14, fontweight='bold')
ax.set_ylim(0, 110)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(results_dir / 'accuracy_by_mode.png', dpi=300, bbox_inches='tight')
print(f"   ✓ Saved: {results_dir / 'accuracy_by_mode.png'}")
plt.close()

# ============================================================================
# FIGURE 3: False Positive Rate Comparison
# ============================================================================
print("\n[3/4] Generating False Positive Rate Comparison...")

fp_data = []
mode_names = []
for mode in ['A', 'B', 'C']:
    subset = df[df['system'] == mode]
    fp_rate = (subset['is_fp'].sum() / len(subset)) * 100
    fp_data.append(fp_rate)
    mode_names.append(['Mode A\n(Baseline)', 'Mode B\n(Centralized)', 'Mode C\n(Blockchain)'][['A', 'B', 'C'].index(mode)])

fig, ax = plt.subplots(figsize=(10, 6))
colors = ['#FF6B6B', '#FFE66D', '#95E1D3']
bars = ax.bar(mode_names, fp_data, color=colors, edgecolor='black', linewidth=1.5, alpha=0.8)

# Add value labels
for bar, val in zip(bars, fp_data):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
            f'{val:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')

ax.set_ylabel('False Positive Rate (%)', fontsize=12, fontweight='bold')
ax.set_title('False Positive Rate Comparison (Unauthorized Actions Allowed)', fontsize=14, fontweight='bold')
ax.set_ylim(0, 70)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(results_dir / 'false_positive_rate.png', dpi=300, bbox_inches='tight')
print(f"   ✓ Saved: {results_dir / 'false_positive_rate.png'}")
plt.close()

# ============================================================================
# FIGURE 4: Blockchain Overhead Visualization
# ============================================================================
print("\n[4/4] Generating Blockchain Overhead Visualization...")

overhead_modes = ['Mode A\n(Baseline)', 'Mode B\n(Centralized)', 'Mode C\n(Blockchain)']
mode_latencies = []
for mode in ['A', 'B', 'C']:
    subset = df[df['system'] == mode]['latency_ms']
    mode_latencies.append(subset.mean())

# Create figure with subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Left: Latency comparison
colors = ['#94E1D3', '#F38181', '#AA96DA']
bars1 = ax1.bar(overhead_modes, mode_latencies, color=colors, edgecolor='black', linewidth=1.5, alpha=0.8)
for bar, val in zip(bars1, mode_latencies):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5, 
            f'{val:.1f} ms', ha='center', va='bottom', fontsize=11, fontweight='bold')

ax1.set_ylabel('Mean Latency (ms)', fontsize=11, fontweight='bold')
ax1.set_title('Mean Latency by Mode', fontsize=12, fontweight='bold')
ax1.grid(axis='y', alpha=0.3)

# Right: Overhead percentage
overhead_b = ((mode_latencies[1] - mode_latencies[0]) / mode_latencies[0]) * 100
overhead_c = ((mode_latencies[2] - mode_latencies[1]) / mode_latencies[1]) * 100
overhead_total = ((mode_latencies[2] - mode_latencies[0]) / mode_latencies[0]) * 100

overhead_labels = [
    f'A → B\n+{overhead_b:.1f}%',
    f'B → C\n+{overhead_c:.1f}%',
    f'A → C\n+{overhead_total:.1f}%'
]
overhead_values = [overhead_b, overhead_c, overhead_total]
colors2 = ['#F9A825', '#FF6B35', '#C1121F']

bars2 = ax2.bar(overhead_labels, overhead_values, color=colors2, edgecolor='black', linewidth=1.5, alpha=0.8)
for bar, val in zip(bars2, overhead_values):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, 
            f'{val:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

ax2.set_ylabel('Latency Overhead (%)', fontsize=11, fontweight='bold')
ax2.set_title('Blockchain Overhead Analysis', fontsize=12, fontweight='bold')
ax2.grid(axis='y', alpha=0.3)

plt.suptitle('Blockchain Overhead Visualization', fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(results_dir / 'blockchain_overhead.png', dpi=300, bbox_inches='tight')
print(f"   ✓ Saved: {results_dir / 'blockchain_overhead.png'}")
plt.close()

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("FIGURE GENERATION COMPLETE")
print("=" * 70)
print(f"\nAll figures saved to: {results_dir}")
print("\nGenerated Figures:")
print("  1. latency_heatmap.png - Mode × Action latency heatmap")
print("  2. accuracy_by_mode.png - Authorization accuracy comparison")
print("  3. false_positive_rate.png - FP rate comparison")
print("  4. blockchain_overhead.png - Overhead analysis (2 subplots)")
print("\nAll figures: 300 DPI, publication-ready PNG format")
print("\n" + "=" * 70)
