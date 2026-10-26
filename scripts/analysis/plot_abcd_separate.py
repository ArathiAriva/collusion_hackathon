"""Separate descriptive A–D figures, with an exact team-optimum reference."""
import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt



def load_runs(source, selected_seeds=None, conditions=('A', 'B', 'C', 'D')):
    """Require complete A–D blocks; never silently drop unmatched seeds."""
    data = json.loads(source.read_text())
    if data.get('status') != 'completed':
        raise ValueError('Plotting requires a completed analysis')
    runs = [r for r in data['runs'] if r['condition'] in conditions]
    lookup = {(r['condition'], r['seed']): r for r in runs}
    if len(lookup) != len(runs):
        raise ValueError('Duplicate condition/seed entries')
    by_condition = {c: {s for cc, s in lookup if cc == c} for c in conditions}
    if selected_seeds is None:
        if any(v != by_condition[conditions[0]] for v in by_condition.values()):
            raise ValueError('Condition seed sets differ; supply complete matched blocks')
        seeds = sorted(by_condition[conditions[0]])
    else:
        seeds = sorted(set(selected_seeds))
    if len(seeds) < 2:
        raise ValueError('At least two matched seeds are required for sample SD')
    for c in conditions:
        for seed in seeds:
            if (c, seed) not in lookup:
                raise ValueError(f'Missing condition {c}, seed {seed}')
            for key in ('reference_pair_regret_gap', 'joint_reward', 'primary_regret_gap', 'optimal_reward'):
                if not math.isfinite(lookup[c, seed][key]):
                    raise ValueError(f'Non-finite {key}: {c}, seed {seed}')
    return lookup, seeds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--batch', type=Path, help='Completed batch containing analysis/results.json')
    source_group.add_argument('--input', type=Path, help='Completed analysis results.json')
    parser.add_argument('--output-dir', type=Path, help='New output directory (must not exist)')
    parser.add_argument('--seeds', nargs='+', type=int, help='Explicit matched seed selection; default: all A–D seeds')
    parser.add_argument('--formats', nargs='+', choices=['svg', 'pdf', 'png'], default=['svg'],
                        help='Export formats; default: editable vector SVG')
    parser.add_argument('--charts', nargs='+', choices=['fixed-pair', 'team-reward', 'best-subset-supplement'],
                        default=['fixed-pair', 'team-reward', 'best-subset-supplement'])
    args = parser.parse_args()
    source = (args.input if args.input else args.batch / 'analysis/results.json').resolve()
    lookup, seeds = load_runs(source, args.seeds)
    conditions = list('ABCD')
    n = len(seeds)
    optima = []
    for seed in seeds:
        matched = [lookup[c, seed]['optimal_reward'] for c in conditions]
        if max(matched) - min(matched) >= 1e-8:
            raise ValueError(f'Optimal rewards differ across conditions for seed {seed}: {matched}')
        optima.append(matched[0])
    optimum_mean = mean(optima)
    optimum_sd = stdev(optima)
    out = args.output_dir.resolve() if args.output_dir else source.parent / 'plots' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=False)
    colors = ['#2463a6', '#d17b28', '#3b9364', '#8456a2']
    rows = []
    metrics = [
        ('reference_pair_regret_gap', 'fixed-pair', 'Advantage of the same fixed pair', 'Mean regret gap'),
        ('joint_reward', 'team-reward', 'Whole-team reward versus the task optimum', 'Mean total reward'),
        ('primary_regret_gap', 'best-subset-supplement', 'Best-subset advantage (supplementary)', 'Mean maximum regret gap'),
    ]
    for metric, name, title, ylabel in metrics:
        if name not in args.charts:
            continue
        values = [[lookup[c, s][metric] for s in seeds] for c in conditions]
        means = [mean(v) for v in values]
        sds = [stdev(v) for v in values]
        compact = name in ('fixed-pair', 'team-reward')
        if compact:
            fig, ax = plt.subplots(figsize=(6.4, 4.4), layout='constrained')
        else:
            fig, ax = plt.subplots(figsize=(8, 7))
            fig.subplots_adjust(left=.13, right=.96, bottom=.34, top=.77)
        ax.bar(range(4), means, yerr=sds, capsize=7, width=.6, color=colors, alpha=.82,
               error_kw={'ecolor': '#222222', 'elinewidth': 1.6, 'capthick': 1.6}, zorder=3)
        bounds = [0] + [b for mu, sd in zip(means, sds) for b in (mu-sd, mu+sd)]
        if metric == 'joint_reward':
            bounds.extend([min(optima), max(optima)])
            ax.axhspan(min(optima), max(optima), color='#777777', alpha=.16, zorder=0,
                       label='Optimum range')
            ax.axhline(optimum_mean, color='#333333', linestyle='--', lw=1.6, zorder=2,
                       label=f'Mean optimum: {optimum_mean:.2f}')
            ax.legend(loc='upper right', frameon=False, fontsize=11)
        span = max(max(bounds) - min(bounds), 1.0)
        for i, (mu, sd) in enumerate(zip(means, sds)):
            label = f'{mu:.2f}' if metric == 'joint_reward' else f'{mu:+.2f}'
            ax.text(i, mu+sd+.035*span, label, ha='center', va='bottom', fontsize=12, weight='bold')
            for seed, value in zip(seeds, values[i]):
                rows.append(dict(metric=metric, condition=conditions[i], seed=seed, value=value,
                                 mean=mu, sample_sd=sd, n=n, optimal_team_reward=lookup[conditions[i],seed]['optimal_reward']))
        if metric == 'joint_reward':
            for seed, value in zip(seeds, optima):
                rows.append(dict(metric='optimal_reward', condition='Optimum', seed=seed, value=value,
                                 mean=optimum_mean, sample_sd=optimum_sd, n=n, optimal_team_reward=value))
        ax.set_ylim(min(bounds)-.09*span, max(bounds)+.19*span)
        if metric == 'joint_reward':
            ax.set_ylim(bottom=0)
        ax.axhline(0, color='#555555', lw=.9, zorder=2)
        ax.set_xticks(range(4), conditions, fontsize=12)
        ax.set_xlabel('Condition', fontsize=12)
        ax.set_ylabel({'fixed-pair': 'Regret gap', 'team-reward': 'Total reward'}.get(name, ylabel),
                      fontsize=13 if compact else 12)
        if compact:
            ax.tick_params(axis='both', labelsize=12)
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#eeeeee', lw=.7)
        ax.set_axisbelow(True)
        if compact:
            ax.set_title('Fixed-pair regret gap' if name == 'fixed-pair' else 'Team reward', fontsize=16, pad=10)
        else:
            fig.suptitle(title, fontsize=16, y=.97)
            fig.text(.5, .90, f'Means ±1 sample SD across {n} matched seeds', ha='center', fontsize=11)
            fig.text(.5, .16, 'A: instructions + private board     B: instructions only\nC: private board only     D: neither\nAll conditions share a global planning board.', ha='center', fontsize=10, linespacing=1.45)
        note = {
            'reference_pair_regret_gap': 'Positive gap: pair has lower mean regret than outsiders.\nThe pair has coalition instructions only in A/B; C/D use the same identities.',
            'joint_reward': 'Dashed line: mean of the seed-specific exact optimal team rewards.\nEach optimum is shared across A–D for that seed.',
            'primary_regret_gap': 'The maximizing subset (size 2–5) is selected separately in each run.\nA positive maximum alone does not establish collusion.',
        }[metric]
        if compact:
            details = (
                'Positive gap means the pair has lower average regret than outsiders. '
                'The same pair identities are scored in every condition; only A/B assign a coalition objective. '
                if name == 'fixed-pair' else
                f'The horizontal gray band spans the minimum to maximum exact seed optimum '
                f'({min(optima):.2f}–{max(optima):.2f}), using the {n} distinct seed optima once each. '
                'This band is the observed range, not ±1 SD or a confidence interval. '
                f'The dashed line is the mean exact optimal team reward ({optimum_mean:.2f}) across these seeds; '
                'each seed has its own optimum, shared across conditions. '
            )
            caption = (
                f'Bars show means; error bars show ±1 sample SD across {n} matched seeds. '
                + details +
                'A: instructions + private pair board; B: instructions only; '
                'C: private pair board only; D: neither. All conditions share a global board. '
                'Error bars describe seed variation, not confidence intervals.\n'
            )
            (out / f'{name}-caption.md').write_text(caption)
        else:
            fig.text(.5, .045, note+'\nError bars describe seed variation, not confidence intervals.', ha='center', fontsize=9, linespacing=1.4)
        for ext in dict.fromkeys(args.formats):
            fig.savefig(out / f'{name}.{ext}', dpi=180, bbox_inches='tight', pad_inches=.08)
        plt.close(fig)
    with (out / 'chart_data.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    provenance = dict(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      seeds=seeds, conditions=conditions, error_bars=f'±1 sample SD (ddof=1), n={n}',
                      formats=args.formats, charts=args.charts, fixed_pair_layout='compact; external caption',
                      team_reward_layout='compact; external caption; horizontal min–max optimum band and mean line',
                      command=sys.argv, python_version=platform.python_version(),
                      matplotlib_version=matplotlib.__version__,
                      seed_optima=dict(zip(seeds, optima)), mean_exact_optimal_team_reward=optimum_mean,
                      sample_sd_exact_optimal_team_reward=optimum_sd,
                      exact_optimal_team_reward_range=[min(optima), max(optima)],
                      optimum_matches_conditions=True)
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    shutil.copyfile(__file__, out / Path(__file__).name)
    print(json.dumps({'output': str(out), 'mean_optimal_reward': optimum_mean, 'seed_optima': optima}, indent=2))


if __name__ == '__main__':
    main()
