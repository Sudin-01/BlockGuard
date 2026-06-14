#!/usr/bin/env python3
"""
analysis_safety.py
Analyze safety evaluation data: accuracy, FP/FN rates, unauthorized actions.

Usage:
  python analysis_safety.py \
    --input experiments/safety_evaluation.csv \
    --output results/safety_analysis

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
RESTRICTED_ACTIONS = ['transfer_money', 'execute_command', 'delete_database']

# ── Data Loading ────────────────────────────────────────────────────────────────

def load_data(csv_path: str) -> pd.DataFrame:
    """Load safety evaluation CSV and convert boolean columns."""
    if not Path(csv_path).exists():
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    
    df = pd.read_csv(csv_path)
    
    # Convert string bools to actual booleans
    for col in ['ground_truth', 'decision', 'is_correct', 'is_fp', 'is_fn']:
        if col in df.columns:
            df[col] = df[col].astype(bool)
    
    print(f"[INFO] Loaded {len(df)} records from {csv_path}")
    return df

# ── Statistical Analysis ────────────────────────────────────────────────────────

def compute_accuracy_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute accuracy, FP/FN rates for each mode.
    
    FORMULAS:
      accuracy = n_correct / n_total * 100
      false_positive_rate = n_fp / n_total * 100
      false_negative_rate = n_fn / n_total * 100
      unauthorized_actions = count(is_fp AND action in restricted_actions)
    """
    results = []
    
    for mode in MODES:
        subset = df[df['mode'] == mode]
        if len(subset) == 0:
            continue
        
        n_correct = (subset['is_correct']).sum()
        n_fp = (subset['is_fp']).sum()
        n_fn = (subset['is_fn']).sum()
        n_total = len(subset)
        
        # Count restricted actions that were incorrectly allowed
        restricted_subset = subset[subset['action'].isin(RESTRICTED_ACTIONS)]
        n_unauthorized = (restricted_subset['is_fp']).sum()
        n_correctly_denied = ((~restricted_subset['is_fp']) & 
                              (restricted_subset['ground_truth'] == False)).sum()
        
        results.append({
            'mode': mode,
            'mode_label': MODE_LABELS[mode],
            'n_requests': n_total,
            'n_correct': int(n_correct),
            'n_false_positive': int(n_fp),
            'n_false_negative': int(n_fn),
            'n_unauthorized_actions': int(n_unauthorized),
            'n_correctly_denied': int(n_correctly_denied),
            'accuracy_pct': (n_correct / n_total) * 100,
            'false_positive_rate_pct': (n_fp / n_total) * 100,
            'false_negative_rate_pct': (n_fn / n_total) * 100,
            'unauthorized_action_pct': (n_unauthorized / len(restricted_subset) * 100) if len(restricted_subset) > 0 else 0,
        })
    
    return pd.DataFrame(results)

def compute_per_action_accuracy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute accuracy broken down by action type.
    """
    results = []
    
    for mode in MODES:
        for action in sorted(df['action'].unique()):
            subset = df[(df['mode'] == mode) & (df['action'] == action)]
            if len(subset) == 0:
                continue
            
            n_correct = (subset['is_correct']).sum()
            n_total = len(subset)
            n_fp = (subset['is_fp']).sum()
            n_fn = (subset['is_fn']).sum()
            
            results.append({
                'mode': mode,
                'mode_label': MODE_LABELS[mode],
                'action': action,
                'n_requests': int(n_total),
                'n_correct': int(n_correct),
                'n_false_positive': int(n_fp),
                'n_false_negative': int(n_fn),
                'accuracy_pct': (n_correct / n_total) * 100,
            })
    
    return pd.DataFrame(results)

def compute_confusion_matrix(df: pd.DataFrame) -> dict:
    """
    Compute confusion matrix metrics for each mode.
    
    FORMULAS:
      TP = decision=1 AND ground_truth=1
      TN = decision=0 AND ground_truth=0
      FP = decision=1 AND ground_truth=0
      FN = decision=0 AND ground_truth=1
      
      Precision = TP / (TP + FP)
      Recall = TP / (TP + FN)
      F1 = 2 * (Precision * Recall) / (Precision + Recall)
    """
    results = {}
    
    for mode in MODES:
        subset = df[df['mode'] == mode]
        
        # Convert to numeric for calculations
        decisions = subset['decision'].astype(int)
        ground_truths = subset['ground_truth'].astype(int)
        
        TP = ((decisions == 1) & (ground_truths == 1)).sum()
        TN = ((decisions == 0) & (ground_truths == 0)).sum()
        FP = ((decisions == 1) & (ground_truths == 0)).sum()
        FN = ((decisions == 0) & (ground_truths == 1)).sum()
        
        precision = TP / (TP + FP) if (TP + FP) > 0 else 0
        recall = TP / (TP + FN) if (TP + FN) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        results[mode] = {
            'TP': int(TP),
            'TN': int(TN),
            'FP': int(FP),
            'FN': int(FN),
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'specificity': TN / (TN + FP) if (TN + FP) > 0 else 0,
        }
    
    return results

# ── Visualization ──────────────────────────────────────────────────────────────

def plot_accuracy_by_mode(accuracy_metrics: pd.DataFrame, output_dir: Path):
    """
    Bar plot: accuracy % for each mode.
    """
    fig, ax = plt.subplots(figsize=(11, 6))
    
    modes = accuracy_metrics['mode'].values
    labels = [MODE_LABELS[m] for m in modes]
    values = accuracy_metrics['accuracy_pct'].values
    colors = ['#ff9999', '#ffcc99', '#99ccff']
    
    bars = ax.bar(labels, values, color=colors, edgecolor='black', linewidth=1.5)
    ax.set_ylabel('Decision Accuracy (%)', fontsize=12, labelpad=10)
    ax.set_title('Decision Accuracy by Policy Mode', fontsize=14, fontweight='bold', pad=20)
    ax.set_ylim([0, 105])
    ax.axhline(y=97, color='r', linestyle='--', alpha=0.7, linewidth=2, label='Target: 97%')
    
    # Add value labels on bars
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{val:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')
    
    ax.legend(fontsize=11, loc='lower right')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'accuracy_by_mode.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: accuracy_by_mode.png")

def plot_error_rates(accuracy_metrics: pd.DataFrame, output_dir: Path):
    """
    Grouped bar plot: FP and FN rates for each mode.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(accuracy_metrics))
    width = 0.35
    
    fp_rates = accuracy_metrics['false_positive_rate_pct'].values
    fn_rates = accuracy_metrics['false_negative_rate_pct'].values
    labels = [MODE_LABELS[m] for m in accuracy_metrics['mode'].values]
    
    ax.bar(x - width/2, fp_rates, width, label='False Positive Rate (Security Risk)', 
           color='#ff6b6b', edgecolor='black', linewidth=1.5)
    ax.bar(x + width/2, fn_rates, width, label='False Negative Rate (Usability)', 
           color='#4ecdc4', edgecolor='black', linewidth=1.5)
    
    ax.set_ylabel('Error Rate (%)', fontsize=12, labelpad=10)
    ax.set_title('False Positive and False Negative Rates by Mode', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(fontsize=11, loc='upper right')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'error_rates.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: error_rates.png")

def plot_unauthorized_actions(accuracy_metrics: pd.DataFrame, output_dir: Path):
    """
    Bar plot: unauthorized actions allowed vs. correctly denied.
    """
    fig, ax = plt.subplots(figsize=(11, 6))
    
    x = np.arange(len(accuracy_metrics))
    width = 0.35
    
    unauthorized = accuracy_metrics['n_unauthorized_actions'].values
    denied = accuracy_metrics['n_correctly_denied'].values
    labels = [MODE_LABELS[m] for m in accuracy_metrics['mode'].values]
    
    ax.bar(x - width/2, unauthorized, width, label='Unauthorized Actions Allowed (CRITICAL)', 
           color='#ff6b6b', edgecolor='black', linewidth=1.5)
    ax.bar(x + width/2, denied, width, label='Correctly Denied', 
           color='#51cf66', edgecolor='black', linewidth=1.5)
    
    ax.set_ylabel('Count', fontsize=12, labelpad=10)
    ax.set_title('High-Risk Actions: Unauthorized vs. Correctly Denied', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'unauthorized_actions.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: unauthorized_actions.png")

def plot_per_action_accuracy(per_action_df: pd.DataFrame, output_dir: Path):
    """
    Heatmap: accuracy for each (mode × action) pair.
    """
    pivot = per_action_df.pivot_table(
        values='accuracy_pct',
        index='mode_label',
        columns='action',
        aggfunc='mean'
    )
    
    fig, ax = plt.subplots(figsize=(13, 5))
    sns.heatmap(
        pivot, annot=True, fmt='.1f', cmap='RdYlGn', ax=ax,
        cbar_kws={'label': 'Accuracy (%)'}, linewidths=0.5, vmin=0, vmax=100
    )
    ax.set_title('Accuracy by Mode and Action Type', fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Action Type', fontsize=12, labelpad=10)
    ax.set_ylabel('Policy Mode', fontsize=12, labelpad=10)
    plt.tight_layout()
    plt.savefig(output_dir / 'accuracy_by_action_heatmap.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Generated: accuracy_by_action_heatmap.png")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Analyze safety evaluation data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analysis_safety.py --input safety_evaluation.csv --output results/
  python analysis_safety.py --input /tmp/safety.csv --output ./analysis/
        """
    )
    parser.add_argument('--input', required=True, help='Path to safety_evaluation.csv')
    parser.add_argument('--output', required=True, help='Output directory for results')
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Output directory: {output_dir}")
    
    # Load & analyze
    print("[INFO] Loading data...")
    df = load_data(args.input)
    
    print("[INFO] Computing statistics...")
    accuracy_metrics = compute_accuracy_metrics(df)
    per_action_accuracy = compute_per_action_accuracy(df)
    confusion_matrices = compute_confusion_matrix(df)
    
    # Export tables
    print("[INFO] Exporting tables...")
    accuracy_metrics.to_csv(output_dir / 'accuracy_metrics.csv', index=False)
    per_action_accuracy.to_csv(output_dir / 'per_action_accuracy.csv', index=False)
    
    # Export confusion matrices
    with open(output_dir / 'confusion_matrices.json', 'w') as f:
        json.dump(confusion_matrices, f, indent=2)
    
    # Generate plots
    print("[INFO] Generating visualizations...")
    plot_accuracy_by_mode(accuracy_metrics, output_dir)
    plot_error_rates(accuracy_metrics, output_dir)
    plot_unauthorized_actions(accuracy_metrics, output_dir)
    plot_per_action_accuracy(per_action_accuracy, output_dir)
    
    # Print summary to console
    print("\n" + "="*80)
    print("SAFETY EVALUATION SUMMARY")
    print("="*80)
    print("\nAccuracy Metrics by Mode:")
    print(accuracy_metrics.to_string(index=False))
    
    print("\n\nPer-Action Accuracy:")
    print(per_action_accuracy.to_string(index=False))
    
    print("\n\nConfusion Matrices (Precision, Recall, F1):")
    for mode, metrics in confusion_matrices.items():
        print(f"\n  Mode {mode}:")
        print(f"    TP={metrics['TP']}, TN={metrics['TN']}, FP={metrics['FP']}, FN={metrics['FN']}")
        print(f"    Precision: {metrics['precision']:.4f}, Recall: {metrics['recall']:.4f}, F1: {metrics['f1_score']:.4f}")
    
    print("\n\nDetailed Results exported to:", output_dir)
    print("Files:")
    print("  - accuracy_metrics.csv")
    print("  - per_action_accuracy.csv")
    print("  - confusion_matrices.json")
    print("  - accuracy_by_mode.png")
    print("  - error_rates.png")
    print("  - unauthorized_actions.png")
    print("  - accuracy_by_action_heatmap.png")
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
