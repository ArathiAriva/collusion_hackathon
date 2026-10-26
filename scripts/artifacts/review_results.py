#!/usr/bin/env python3
"""Rescore and audit archived report studies offline, independent of saved absolute paths."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'colosseum'), str(ROOT / 'scripts/shared_board'),
               str(ROOT / 'scripts/release_pipeline')]


def local_native(root, saved):
    marker = 'colosseum/experiments/collusion/outputs/'
    if marker not in saved:
        raise ValueError(f'Unknown native artifact path: {saved}')
    relative = Path(marker + saved.split(marker, 1)[1])
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Artifact path escapes extracted root')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Root produced by results_bundle.py')
    parser.add_argument('--output', type=Path, required=True, help='New JSON file for verification summary')
    args = parser.parse_args()
    from audit_shared_runs import audit_run, summarize_run, read
    from run_f_seed_blocks import audit_f, CONFIG
    from experiments.collusion.release_pipeline.analysis import audit_run as audit_release
    from summarize_completed import derive
    import yaml

    shared = read(args.root / 'results/ae-batches/shared-board-eval-v2-seeds101-105/analysis/results.json')
    baseline = {}
    signatures = {}
    for saved in shared['runs']:
        path = local_native(args.root, saved['run_dir'])
        audit_run(path, saved['condition'], protocol='shared')
        result, subsets, signature = summarize_run(path, saved['condition'])
        for key in ('joint_reward', 'optimal_reward', 'primary_regret_gap', 'best_pair_regret_gap'):
            if not math.isclose(result[key], saved[key], abs_tol=1e-8):
                raise ValueError(f'Saved Jira metric differs: {key}')
        if len(subsets) != 62:
            raise ValueError('Expected all 62 proper subsets')
        seed = saved['seed']
        if seed in signatures and signatures[seed] != signature:
            raise ValueError('Jira condition inputs/order differ within seed')
        signatures[seed] = signature
        if saved['condition'] == 'A':
            baseline[seed] = {**saved, 'run_dir': str(path)}
    oversight = read(args.root / 'results/ae-batches/f-oversight-eval-v1-seeds101-105/analysis/results.json')
    cfg = yaml.safe_load(CONFIG.read_text())
    for saved in oversight['runs']:
        result, _ = audit_f({'trajectories': [{'run_dir': str(local_native(args.root, saved['run_dir']))}]}, cfg, baseline[saved['seed']])
        if not math.isclose(result['joint_reward'], saved['joint_reward'], abs_tol=1e-8):
            raise ValueError('F reward differs')
    release = {}
    for version, name in [('v9', 'release-product-release-deadline-v9-retry-20261026'),
                          ('v10', 'release-product-release-deadline-v10-20261026')]:
        batch = args.root / 'results/release-pipeline' / name
        summary = derive(batch)
        for row in summary['rows']:
            audit_release(batch / 'runs' / row['run_id'])
        release[version] = {k: summary[k] for k in ('status', 'flow', 'matched_seeds', 'condition_summaries')}
    output = {'jira': {'audited_main_runs': len(shared['runs']), 'subsets_per_run': 62,
                       'audited_oversight_runs': len(oversight['runs'])}, 'release': release}
    with args.output.open('x') as stream:
        stream.write(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
