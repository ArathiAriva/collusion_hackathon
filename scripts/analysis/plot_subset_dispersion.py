"""Plot within-run subset-gap dispersion averaged across matched seeds."""
import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS = {'A':'#2463a6', 'B':'#d17b28', 'C':'#3b9364', 'D':'#8456a2', 'E':'#b44955'}
MARKERS = {'A':'o', 'B':'s', 'C':'^', 'D':'D', 'E':'v'}
LABELS = {'A':'A: instructions + private board', 'B':'B: instructions only',
          'C':'C: private board only', 'D':'D: neither', 'E':'E: all pairwise private boards'}
METRICS = [('gap_population_sd','Standard deviation','SD of subset regret gaps'),
           ('gap_iqr','Interquartile range','IQR of subset regret gaps')]


def load_data(source, conditions):
    with source.open() as f:
        rows = [r for r in csv.DictReader(f) if r['condition'] in conditions]
    lookup = {}
    for r in rows:
        key = r['condition'], int(r['seed']), int(r['size'])
        if key in lookup:
            raise ValueError(f'Duplicate condition/seed/size: {key}')
        lookup[key] = {metric:float(r[metric]) for metric,_,_ in METRICS}
        if any(not math.isfinite(v) or v < 0 for v in lookup[key].values()):
            raise ValueError(f'Invalid dispersion: {key}')
    seeds = sorted({s for _,s,_ in lookup})
    sizes = sorted({k for _,_,k in lookup})
    if not seeds or not sizes:
        raise ValueError('No matching data')
    if set(lookup) != {(c,s,k) for c in conditions for s in seeds for k in sizes}:
        raise ValueError('Require complete matched condition/seed/size blocks')
    aggregates = [dict(condition=c, size=k, metric=metric,
                       mean_dispersion=mean(lookup[c,s,k][metric] for s in seeds), n_seeds=len(seeds))
                  for metric,_,_ in METRICS for c in conditions for k in sizes]
    return lookup, seeds, sizes, aggregates


def make_figure(aggregates, conditions, sizes, seeds):
    lookup = {(r['condition'],r['size'],r['metric']):r['mean_dispersion'] for r in aggregates}
    fig, axes = plt.subplots(1,2,figsize=(11,6))
    fig.subplots_adjust(left=.08, right=.98, bottom=.27, top=.73, wspace=.25)
    for ax,(metric,title,ylabel) in zip(axes,METRICS):
        for c in conditions:
            ax.plot(sizes,[lookup[c,k,metric] for k in sizes], color=COLORS[c], marker=MARKERS[c],
                    lw=1.8, ms=6, label=LABELS[c])
        ax.set(title=title, xlabel='Subset size', ylabel=ylabel)
        ax.set_xticks(sizes)
        ax.set_ylim(bottom=0)
        ax.margins(x=.09,y=.15)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',color='#eeeeee',lw=.7)
        ax.set_axisbelow(True)
    fig.suptitle('How subset regret-gap dispersion varies across conditions',fontsize=15,y=.98)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.93),ncol=2,frameon=False,fontsize=10)
    fig.text(.5,.77,f'Each point: mean within-run dispersion across {len(seeds)} matched seeds. No error bars.',
             ha='center',fontsize=10)
    fig.text(.5,.15,'SD: spread across all subsets of a fixed size. IQR: width of the middle 50% of subset gaps.',
             ha='center',fontsize=10)
    fig.text(.5,.095,'These describe outcome variation within runs, not uncertainty in condition differences.\nSizes 2 and 4 have identical dispersion because complementary subsets have opposite gaps.',
             ha='center',fontsize=9,linespacing=1.5)
    fig.text(.5,.025,'Lines guide comparisons across discrete subset sizes; they are not time trajectories. All conditions share a global board.',
             ha='center',fontsize=9)
    return fig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics-dir',type=Path,required=True,help='Output directory from derive_subset_metrics.py')
    parser.add_argument('--conditions',nargs='+',choices=list('ABCDE'),default=list('ABCD'))
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--formats',nargs='+',choices=['svg','pdf','png'],default=['svg'])
    args=parser.parse_args()
    conditions=list(dict.fromkeys(args.conditions))
    source=args.metrics_dir.resolve()/'subset_metrics_by_size_seed.csv'
    lookup,seeds,sizes,aggregates=load_data(source,conditions)
    out=args.output_dir.resolve() if args.output_dir else args.metrics_dir.resolve()/'dispersion-plots'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True,exist_ok=False)
    fig=make_figure(aggregates,conditions,sizes,seeds)
    for ext in dict.fromkeys(args.formats):fig.savefig(out/f'subset-gap-dispersion.{ext}',dpi=180)
    plt.close(fig)
    with (out/'chart_means.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(aggregates[0]));w.writeheader();w.writerows(aggregates)
    shutil.copyfile(source,out/source.name)
    provenance=dict(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    conditions=conditions,seeds=seeds,sizes=sizes,
                    aggregation='Equal-weight mean across seeds of within-run fixed-size population SD or IQR',
                    error_bars=None,independent_units='matched seed blocks; subsets overlap and are dependent',
                    matplotlib_version=matplotlib.__version__,python_version=platform.python_version())
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    shutil.copyfile(__file__,out/Path(__file__).name)
    print(out)


if __name__=='__main__':main()
