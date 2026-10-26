"""Plot every subset regret gap in matched A–D runs using Matplotlib."""
import argparse
import csv
import hashlib
import itertools
import json
import math
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from plot_abcd_separate import load_runs

TITLES = {'A': 'Instructions + private board', 'B': 'Instructions only',
          'C': 'Private board only', 'D': 'Neither'}
MARKERS = {1: 'v', 2: 'o', 3: '^', 4: 's', 5: 'D'}


def load_points(source, subset_source, include_singletons=False, conditions=('A', 'B', 'C', 'D')):
    runs, seeds = load_runs(source, conditions=conditions)
    groups = {(c, s): [] for c in conditions for s in seeds}
    with subset_source.open() as f:
        for row in csv.DictReader(f):
            key = row['condition'], int(row['seed'])
            if key not in groups:
                continue
            members = tuple(sorted(json.loads(row['members'])))
            size, gap = int(row['size']), float(row['regret_gap'])
            if len(members) != size or not math.isfinite(gap):
                raise ValueError(f'Invalid subset score: {key}, {members}')
            groups[key].append(dict(condition=key[0], seed=key[1], members=members, size=size, regret_gap=gap))
    points = []
    for (c, seed), rows in groups.items():
        ref = runs[c, seed]['reference_group']
        agents = sorted(ref['members'] + ref['complement'])
        if len(agents) != 6 or len(set(agents)) != 6:
            raise ValueError('This plot supports the six-agent A–D protocol')
        expected = {t for k in range(1, 6) for t in itertools.combinations(agents, k)}
        actual = {r['members'] for r in rows}
        if len(rows) != len(actual) or actual != expected:
            raise ValueError(f'Incomplete or duplicate subset enumeration: {c}, {seed}')
        reference = tuple(sorted(ref['members']))
        highlighted = [r for r in rows if r['members'] == reference]
        if len(highlighted) != 1 or not math.isclose(highlighted[0]['regret_gap'], ref['regret_gap'], abs_tol=1e-8):
            raise ValueError(f'Reference-pair score mismatch: {c}, {seed}')
        if set(ref['members']) != set(runs[conditions[0], seed]['reference_group']['members']):
            raise ValueError(f'Reference pair identities differ: {c}, {seed}')
        for row in rows:
            if row['size'] == 1 and not include_singletons:
                continue
            row['is_reference_pair'] = row['members'] == reference
            # Stable horizontal jitter has no score meaning. Membership and seed
            # produce the same x coordinate across all matched conditions.
            token = json.dumps([seed, row['members']], separators=(',', ':')).encode()
            jitter = int.from_bytes(hashlib.sha256(token).digest()[:8], 'big') / (2**64 - 1) - .5
            seed_offset = (seeds.index(seed) - (len(seeds)-1)/2) * (.55 / len(seeds))
            row['x'] = row['size'] + seed_offset + jitter * (.45 / len(seeds))
            row['strip_y'] = conditions.index(c) + seed_offset + jitter * (.45 / len(seeds))
            points.append(row)
    return points, seeds


def draw_panel(ax, condition, points, seeds, colors, limits, sizes):
    rows = [r for r in points if r['condition'] == condition]
    for seed in seeds:
        for size in sizes:
            selected = [r for r in rows if r['seed'] == seed and r['size'] == size]
            ax.scatter([r['x'] for r in selected], [r['regret_gap'] for r in selected],
                       c=[colors[seed]], marker=MARKERS[size], s=29, alpha=.72,
                       edgecolors='none', zorder=3)
    for r in rows:
        if r['is_reference_pair']:
            ax.scatter(r['x'], r['regret_gap'], marker='o', s=120,
                       facecolors='none', edgecolors='black', linewidths=1.6, zorder=5)
            ax.scatter(r['x'], r['regret_gap'], marker='o', s=29,
                       c=[colors[r['seed']]], edgecolors='none', zorder=6)
    ax.axhline(0, color='#666666', lw=.9, zorder=2)
    ax.set(title=f'{condition}: {TITLES[condition]}', xlabel='Subset size (horizontal jitter for visibility)',
           ylabel='Regret gap: outsiders − subset', ylim=limits,
           xlim=(min(sizes)-.5, max(sizes)+.5))
    ax.set_xticks(sizes)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', color='#eeeeee', lw=.7)
    ax.set_axisbelow(True)


def make_figure(points, seeds, conditions, limits, sizes):
    palette = plt.get_cmap('tab10' if len(seeds) <= 10 else 'turbo')
    colors = {s: palette(i if len(seeds) <= 10 else i/max(len(seeds)-1, 1)) for i,s in enumerate(seeds)}
    if len(conditions) == 4:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharey=True)
        axes = axes.flat
        fig.subplots_adjust(left=.09, right=.97, bottom=.20, top=.85, hspace=.35, wspace=.20)
    else:
        fig, ax = plt.subplots(figsize=(8.5, 6.8))
        axes = [ax]
        fig.subplots_adjust(left=.13, right=.96, bottom=.29, top=.76)
    for ax, c in zip(axes, conditions):
        draw_panel(ax, c, points, seeds, colors, limits, sizes)
    fig.suptitle('Subset regret gaps across matched seeds', fontsize=16, y=.98)
    seed_handles = [Line2D([], [], marker='o', ls='', color=colors[s], label=str(s)) for s in seeds]
    shape_handles = [Line2D([], [], marker=MARKERS[k], ls='', color='#555555', label=f'Size {k}') for k in sizes]
    fig.legend(handles=seed_handles, loc='upper center', bbox_to_anchor=(.5,.95),
               ncol=min(len(seeds), 10), title='Seed (color)', frameon=False)
    fig.legend(handles=shape_handles, loc='lower center', bbox_to_anchor=(.5,.095),
               ncol=len(sizes), title='Subset size (shape)', frameon=False)
    count = sum(1 for r in points if r['condition'] == 'A')
    fig.text(.5,.075, f'{count} subsets per condition across {len(seeds)} seeds. Black rings: assigned pair in A/B; same reference pair in C/D.',
             ha='center', fontsize=9)
    fig.text(.5,.015, 'Subsets overlap and are not independent observations. Complementary subsets have opposite gaps.\nPositive gaps indicate relative advantage, not evidence of collusive intent.', ha='center', fontsize=9)
    return fig


def make_strip_figure(points, seeds, limits, sizes):
    """Facets hold size fixed; x shows raw gap, y encodes condition only."""
    palette = plt.get_cmap('tab10' if len(seeds) <= 10 else 'turbo')
    colors = {s: palette(i if len(seeds) <= 10 else i/max(len(seeds)-1, 1)) for i,s in enumerate(seeds)}
    fig, axes = plt.subplots(1, len(sizes), figsize=(3.3*len(sizes)+1, 7.2), sharex=True, sharey=True,
                             squeeze=False)
    fig.subplots_adjust(left=.07, right=.98, bottom=.24, top=.73, wspace=.12)
    for ax, size in zip(axes[0], sizes):
        rows = [r for r in points if r['size'] == size]
        for condition in 'ABCD':
            ax.axhline('ABCD'.index(condition), color='#eeeeee', lw=.8, zorder=1)
            for seed in seeds:
                group = [r for r in rows if r['seed'] == seed and r['condition'] == condition]
                ax.scatter([r['regret_gap'] for r in group], [r['strip_y'] for r in group],
                           c=[colors[seed]], marker='o', s=25, alpha=.75,
                           edgecolors='none', zorder=3)
        for r in rows:
            if r['is_reference_pair']:
                ax.scatter(r['regret_gap'], r['strip_y'], s=105, marker='o',
                           facecolors='none', edgecolors='black', linewidths=1.5, zorder=5)
                ax.scatter(r['regret_gap'], r['strip_y'], s=25, marker='o',
                           c=[colors[r['seed']]], edgecolors='none', zorder=6)
        count = math.comb(6, size)
        ax.set_title(f'Size {size}\n{count} subsets per seed', fontsize=12, pad=14)
        ax.axvline(0, color='#777777', lw=1, zorder=2)
        ax.set(xlim=limits, ylim=(3.55, -.55), xlabel='Regret gap')
        ax.set_yticks(range(4), list('ABCD'), fontsize=12)
        ax.tick_params(axis='y', labelleft=True)
        ax.spines[['top', 'right', 'left']].set_visible(False)
        ax.grid(axis='x', color='#f0f0f0', lw=.6)
        ax.set_axisbelow(True)
    axes[0,0].set_ylabel('Condition', fontsize=12)
    fig.suptitle('Subset regret-gap distributions by condition and subset size', fontsize=16, y=.98)
    handles = [Line2D([], [], marker='o', ls='', color=colors[s], label=str(s)) for s in seeds]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5,.94), ncol=min(len(seeds),10),
               title='Seed (color)', frameon=False)
    fig.text(.5,.84,'Positive gap: subset members have lower average regret than outsiders. All panels share the same scale.',
             ha='center', fontsize=10)
    fig.text(.5,.16,'A: instructions + private board     B: instructions only     C: private board only     D: neither',
             ha='center', fontsize=10)
    fig.text(.5,.115,'Black rings: assigned pair in A/B; same reference pair in C/D (size 2 column). Vertical offsets only separate points.',
             ha='center', fontsize=9)
    fig.text(.5,.045,f'All {len(seeds)} seeds retained; overlapping subsets are dependent. Complementary subsets have opposite gaps.\nSize 3 distributions are symmetric by construction. Positive gaps alone do not establish collusive intent.',
             ha='center', fontsize=9, linespacing=1.5)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--formats', nargs='+', choices=['svg', 'pdf', 'png'], default=['svg'])
    parser.add_argument('--layout', choices=['strips', 'scatter'], default='strips',
                        help='Default: condition rows faceted by size; scatter preserves the original view')
    parser.add_argument('--include-singletons', action='store_true', help='Include size 1 diagnostics (default: sizes 2–5)')
    args = parser.parse_args()
    source = args.batch.resolve() / 'analysis/results.json'
    subset_source = args.batch.resolve() / 'analysis/subsets.csv'
    points, seeds = load_points(source, subset_source, args.include_singletons)
    out = args.output_dir.resolve() if args.output_dir else source.parent/'subset-plots'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True, exist_ok=False)
    sizes = sorted({r['size'] for r in points})
    lo, hi = min(r['regret_gap'] for r in points), max(r['regret_gap'] for r in points)
    padding = max(hi-lo, 1) * .08
    limits = lo-padding, hi+padding
    figures = []
    if args.layout == 'strips':
        extent = max(abs(lo), abs(hi), 1) * 1.08
        figures.append((make_strip_figure(points, seeds, (-extent, extent), sizes), 'subset-gap-strips'))
    else:
        for conditions, name in [(list('ABCD'), 'subset-gaps-abcd')] + [([c], f'subset-gaps-{c.lower()}') for c in 'ABCD']:
            figures.append((make_figure(points, seeds, conditions, limits, sizes), name))
    for fig, name in figures:
        for ext in dict.fromkeys(args.formats):
            fig.savefig(out/f'{name}.{ext}', dpi=180)
        plt.close(fig)
    with (out/'plotted_subsets.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(points[0]))
        writer.writeheader()
        writer.writerows({**r, 'members':json.dumps(r['members'])} for r in points)
    provenance = dict(sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, subset_source)},
                      seeds=seeds, conditions=list('ABCD'), sizes=sizes, points=len(points), layout=args.layout,
                      reference_points=sum(r['is_reference_pair'] for r in points),
                      jitter='SHA-256 of seed and sorted members; identical across conditions; display position only: vertical in strips, horizontal in scatter; regret gaps unchanged',
                      independent_units='matched seed blocks; overlapping subsets are dependent',
                      matplotlib_version=matplotlib.__version__, python_version=platform.python_version())
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    shutil.copyfile(__file__, out/Path(__file__).name)
    # Preserve the helper needed to reproduce this script snapshot.
    shutil.copyfile(Path(__file__).with_name('plot_abcd_separate.py'), out/'plot_abcd_separate.py')
    print(json.dumps({'output':str(out), **provenance}, indent=2))


if __name__ == '__main__':
    main()
