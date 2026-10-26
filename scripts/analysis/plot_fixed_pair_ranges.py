"""Per-seed fixed-pair bars with the full range of pair regret gaps in A–D."""
import argparse
import csv
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from plot_subset_distributions import load_points

COLORS={'A':'#2463a6','B':'#d17b28','C':'#3b9364','D':'#8456a2'}


def summarize_pairs(points,seeds):
    rows=[]
    for c in 'ABCD':
        for seed in seeds:
            pairs=[p for p in points if p['condition']==c and p['seed']==seed and p['size']==2]
            if len(pairs)!=15:raise ValueError(f'Expected 15 pairs for {c}, seed {seed}')
            reference=[p for p in pairs if p['is_reference_pair']]
            if len(reference)!=1:raise ValueError('Expected exactly one reference pair')
            low=min(p['regret_gap'] for p in pairs);high=max(p['regret_gap'] for p in pairs)
            fixed=reference[0]['regret_gap']
            assert low-1e-9<=fixed<=high+1e-9
            rows.append(dict(condition=c,seed=seed,fixed_pair_gap=fixed,min_pair_gap=low,max_pair_gap=high,
                fixed_pair_members=list(reference[0]['members']),
                min_pair_members=[list(p['members']) for p in pairs if math.isclose(p['regret_gap'],low,abs_tol=1e-9)],
                max_pair_members=[list(p['members']) for p in pairs if math.isclose(p['regret_gap'],high,abs_tol=1e-9)],
                pair_count=15))
    return rows


def make_figure(rows,seeds):
    fig,axes=plt.subplots(1,4,figsize=(13.5,4.5),sharey=True)
    fig.subplots_adjust(left=.065,right=.99,bottom=.16,top=.78,wspace=.12)
    low=min(0,min(r['min_pair_gap'] for r in rows));high=max(0,max(r['max_pair_gap'] for r in rows))
    padding=max(high-low,1)*.10
    for ax,c in zip(axes,'ABCD'):
        rr=[r for r in rows if r['condition']==c]
        xs=list(range(len(seeds)))
        ax.bar(xs,[r['fixed_pair_gap'] for r in rr],width=.58,color=COLORS[c],alpha=.82,zorder=2)
        for x,r in zip(xs,rr):
            ax.vlines(x,r['min_pair_gap'],r['max_pair_gap'],color='#333333',lw=1.25,zorder=3)
            ax.hlines([r['min_pair_gap'],r['max_pair_gap']],x-.13,x+.13,color='#333333',lw=1.6,zorder=3)
            ax.scatter(x,r['fixed_pair_gap'],s=24,color=COLORS[c],edgecolors='white',linewidth=.6,zorder=4)
        ax.axhline(0,color='#666666',lw=.9,zorder=1)
        ax.set_xticks(xs,[str(s) for s in seeds],fontsize=11)
        ax.set_title(c,fontsize=14,pad=8)
        ax.set_ylim(low-padding,high+padding)
        ax.tick_params(axis='y',labelsize=11)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',color='#eeeeee',lw=.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel('Regret gap',fontsize=13)
    fig.supxlabel('Seed',fontsize=12,y=.025)
    fig.suptitle('Fixed pair within the range of all pairs',fontsize=16,y=.99)
    fig.legend(handles=[Patch(facecolor='#888888',label='Bar: fixed pair'),
                        Line2D([],[],color='#333333',marker='_',markersize=10,lw=1.25,
                               label='Capped line: lowest–highest pair gap')],
               loc='upper center',bbox_to_anchor=(.5,.93),frameon=False,ncol=2,fontsize=11)
    return fig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--formats',nargs='+',choices=['svg','pdf','png'],default=['svg'])
    args=parser.parse_args()
    source=args.batch.resolve()/'analysis/results.json';subset_source=source.with_name('subsets.csv')
    points,seeds=load_points(source,subset_source);rows=summarize_pairs(points,seeds)
    out=args.output_dir.resolve() if args.output_dir else source.parent/'fixed-pair-ranges'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True,exist_ok=False)
    fig=make_figure(rows,seeds)
    for ext in dict.fromkeys(args.formats):fig.savefig(out/f'fixed-pair-ranges.{ext}',dpi=180,bbox_inches='tight',pad_inches=.08)
    plt.close(fig)
    with (out/'pair_ranges.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        w.writerows({k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items()} for row in rows)
    caption=(f'Each bar shows the fixed-pair regret gap in one condition and seed. Capped lines span the '
        f'minimum to maximum gap over all 15 size-2 subsets in that same run; these are full observed ranges, '
        f'not SD, standard errors, or confidence intervals. All panels share the vertical scale. '
        f'The same pair identities are scored across conditions within each of {len(seeds)} seeds. '
        'Only A/B give the pair coalition instructions; C/D use it as a reference. '
        'A: instructions + private pair board; B: instructions only; C: private pair board only; D: neither. '
        'All conditions have the global board. Subsets overlap and are not independent replications. '
        'Positive regret gap means lower mean regret for the pair than outsiders, not proof of collusive intent.\n')
    (out/'caption.md').write_text(caption)
    (out/'provenance.json').write_text(json.dumps(dict(sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,subset_source]},
        conditions=list('ABCD'),seeds=seeds,pairs_per_condition_seed=15,condition_seed_groups=len(rows),
        range_definition='min/max over all pairs in the same condition/seed, not uncertainty intervals',
        matplotlib_version=matplotlib.__version__),indent=2)+'\n')
    for name in ['plot_fixed_pair_ranges.py','plot_subset_distributions.py','plot_abcd_separate.py']:
        shutil.copyfile(Path(__file__).with_name(name),out/name)
    print(out)


if __name__=='__main__':main()
