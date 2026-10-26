"""Plot D/E matched-seed outcomes and within-run pair-gap dispersion."""
import argparse
import csv
import hashlib
import itertools
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from plot_abcd_separate import load_runs


def chart_data(source, conditions=('D', 'E')):
    if conditions == ('D', 'E'):
        lookup, seeds = load_runs(source, conditions=conditions)
    else:
        data = json.loads(source.read_text())
        if data.get('status') != 'completed':
            raise ValueError('Require completed analysis')
        selected = [r for r in data['runs'] + data.get('baseline_A_runs', []) if r['condition'] in conditions]
        lookup = {(r['condition'], r['seed']): r for r in selected}
        if len(lookup) != len(selected):
            raise ValueError('Duplicate condition/seed entries')
        seed_sets = [{s for c, s in lookup if c == condition} for condition in conditions]
        if seed_sets[0] != seed_sets[1] or len(seed_sets[0]) < 2:
            raise ValueError('Require at least two complete matched seeds')
        seeds = sorted(seed_sets[0])
    rows = []
    for seed in seeds:
        if set(lookup[conditions[0], seed]['reference_group']['members']) != set(lookup[conditions[1], seed]['reference_group']['members']):
            raise ValueError(f'Reference pairs differ for seed {seed}')
        for condition in conditions:
            run = lookup[condition, seed]
            agents = run['agent_outcomes']
            if len(agents) != 6 or len({a['agent_name'] for a in agents}) != 6:
                raise ValueError('Require six distinct agents')
            regrets = [a['regret'] for a in agents]
            if not all(math.isfinite(v) for v in regrets):
                raise ValueError('Non-finite regret')
            pair_gaps = [mean(regrets[k] for k in range(6) if k not in pair)
                         - mean(regrets[k] for k in pair)
                         for pair in itertools.combinations(range(6), 2)]
            members = set(run['reference_group']['members'])
            reference_gap = mean(a['regret'] for a in agents if a['agent_name'] not in members) - mean(a['regret'] for a in agents if a['agent_name'] in members)
            if not math.isclose(reference_gap, run['reference_pair_regret_gap'], abs_tol=1e-8):
                raise ValueError('Stored reference-pair gap disagrees with individual regrets')
            rows.append(dict(condition=condition, seed=seed, team_reward=run['joint_reward'],
                             reference_pair_gap=reference_gap, pair_gap_sd=pstdev(pair_gaps),
                             pair_count=len(pair_gaps)))
    return rows, seeds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--comparison', choices=['DE', 'AF'], default='DE')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--formats', nargs='+', choices=['png', 'svg', 'pdf'], default=['png', 'svg', 'pdf'])
    args = parser.parse_args()
    source = (args.batch / 'analysis/results.json').resolve()
    conditions = tuple(args.comparison)
    rows, seeds = chart_data(source, conditions)
    out = args.output_dir.resolve() if args.output_dir else source.parent / 'plots' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=False)
    metrics = [('team_reward', 'Team reward', 'Total reward'),
               ('reference_pair_gap', 'Assigned-pair advantage' if args.comparison == 'AF' else 'Reference-pair advantage', 'Regret gap'),
               ('pair_gap_sd', 'Pair-gap dispersion', 'SD across all 15 pairs')]
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#9A7800']
    if len(seeds) > len(colors):
        colors = [plt.get_cmap('tab20')(i % 20) for i in range(len(seeds))]
    plt.rcParams.update({'font.size': 11, 'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 4.1))
    fig.subplots_adjust(left=.065, right=.985, bottom=.22, top=.87, wspace=.40)
    by_key = {(r['condition'], r['seed']): r for r in rows}
    means = []
    for ax, (metric, title, ylabel) in zip(axes, metrics):
        for seed, color in zip(seeds, colors):
            values = [by_key[c, seed][metric] for c in conditions]
            ax.plot([0, 1], values, marker='o', ms=6, lw=1.4, color=color, alpha=.85, zorder=3)
        averages = [mean(by_key[c, seed][metric] for seed in seeds) for c in conditions]
        ax.plot([0, 1], averages, color='#222222', lw=2.2, linestyle='--', marker='D',
                markersize=8, markerfacecolor='white', markeredgewidth=1.8, zorder=5)
        for condition, value in zip(conditions, averages):
            means.append(dict(metric=metric, condition=condition, mean=value, n_seeds=len(seeds)))
        if metric == 'reference_pair_gap':
            ax.axhline(0, color='#777777', lw=.9, zorder=1)
        else:
            ax.set_ylim(bottom=0)
        ax.set_xlim(-.2, 1.2)
        ax.set_xticks([0, 1], conditions)
        ax.set_title(title, fontsize=13, pad=10)
        ax.set_ylabel(ylabel)
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#e7e7e7', lw=.7)
        ax.set_axisbelow(True)
        ax.margins(y=.12)
    handles = [Line2D([0], [0], color=color, marker='o', lw=1.4, label=str(seed)) for seed, color in zip(seeds, colors)]
    handles.append(Line2D([0], [0], color='#222222', linestyle='--', marker='D', markerfacecolor='white', lw=2, label='Mean'))
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .015), ncol=len(handles),
               frameon=False, handlelength=2, columnspacing=1.5)
    for ext in dict.fromkeys(args.formats):
        fig.savefig(out / f'{args.comparison.lower()}-paired-panels.{ext}', dpi=200)
    plt.close(fig)
    for filename, data in [('seed_metrics.csv', rows), ('chart_means.csv', means)]:
        with (out / filename).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    definition = ('A: shared global board plus private coalition board. F: the same setup with a governance oversight notice appended to every agent’s user prompts. '
                  'Both assign the pair a coalition objective. The notice is prompt-only; it introduces no actual enforcement. '
                  if args.comparison == 'AF' else
                  'D: shared global board only. E: shared global board plus private boards for every pair. Neither condition assigns a coalition objective. ')
    pair_note = ('The pair is assigned the coalition objective in both conditions. ' if args.comparison == 'AF' else
                 'The reference pair has no special assignment in D or E. ')
    (out / 'caption.md').write_text(
        f'# {conditions[0]} versus {conditions[1]}: matched-seed comparison\n\n' + definition +
        'Colored circles and lines link the same seed across conditions; '
        'white diamonds and dashed black lines indicate equal-weight means across seeds. '
        f'Seeds: {", ".join(map(str, seeds))}.\n\n'
        'Panels show whole-team reward, the same within-seed reference pair’s regret gap, and the population SD '
        'of regret gaps across all 15 pairs in each run. A positive reference-pair gap means outsiders have higher '
        'mean unilateral regret than the pair. ' + pair_note +
        'Pair-gap SD describes outcome dispersion within a run; it is not uncertainty across seeds. '
        'Pairs overlap and are not independent observations. No inferential error bars or significance claims.\n')
    provenance = dict(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      seeds=seeds, conditions=list(conditions), matplotlib_version=matplotlib.__version__,
                      pair_dispersion='Population SD of outsider mean regret minus pair mean regret over all 15 pairs',
                      mean='Equal-weight mean across matched seeds')
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    shutil.copyfile(__file__, out / Path(__file__).name)
    shutil.copyfile(Path(__file__).with_name('plot_abcd_separate.py'), out / 'plot_abcd_separate.py')
    print(out)
    print(json.dumps(means, indent=2))


if __name__ == '__main__':
    main()
