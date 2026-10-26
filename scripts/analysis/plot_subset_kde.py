"""Descriptive KDE views of subset regret gaps; no normal-distribution fit."""
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
import numpy as np
from plot_subset_distributions import load_points

COLORS={'A':'#2463a6','B':'#d17b28','C':'#3b9364','D':'#8456a2'}
LABELS={'A':'A: instructions + private board','B':'B: instructions only',
        'C':'C: private board only','D':'D: neither'}


def compute_curves(points, seeds, bandwidth_scale=1):
    sizes=sorted({r['size'] for r in points})
    bandwidths={}
    for k in sizes:
        pooled=np.array([r['regret_gap'] for r in points if r['size']==k])
        per_condition=len(pooled)//4
        # This Scott-style rule is a display heuristic, not an independence or
        # normality assumption. One absolute bandwidth is shared within a panel.
        scale=float(np.std(pooled,ddof=0))
        bandwidths[k]=max(scale,.1)*per_condition**(-.2)*bandwidth_scale
    extent=max(abs(r['regret_gap']) for r in points)+4*max(bandwidths.values())
    grid=np.linspace(-extent,extent,1401)
    curves={}
    for k in sizes:
        h=bandwidths[k]
        for c in 'ABCD':
            seed_curves=[]
            for s in seeds:
                values=np.array([r['regret_gap'] for r in points if r['condition']==c and r['seed']==s and r['size']==k])
                z=(grid[:,None]-values[None,:])/h
                seed_curves.append(np.exp(-.5*z*z).mean(axis=1)/(h*math.sqrt(2*math.pi)))
            curves[c,k]=np.mean(seed_curves,axis=0)
    return grid,curves,bandwidths


def make_figure(points,seeds,grid,curves,bandwidths):
    sizes=sorted(bandwidths)
    fig,axes=plt.subplots(1,len(sizes),figsize=(14,6),sharex=True,sharey=True,squeeze=False)
    fig.subplots_adjust(left=.065,right=.985,bottom=.29,top=.70,wspace=.12)
    ymax=max(float(v.max()) for v in curves.values())*1.12
    for ax,k in zip(axes[0],sizes):
        for i,c in enumerate('ABCD'):
            density=curves[c,k]
            ax.plot(grid,density,color=COLORS[c],lw=2)
            ax.fill_between(grid,0,density,color=COLORS[c],alpha=.045)
            values=[r['regret_gap'] for r in points if r['condition']==c and r['size']==k]
            ax.plot(values,[.015+i*.022]*len(values),'|',color=COLORS[c],alpha=.35,markersize=4,
                    transform=ax.get_xaxis_transform(),zorder=4)
        count=sum(r['condition']=='A' and r['size']==k for r in points)
        ax.set_title(f'Size {k}: {count} scores / condition\nShared bandwidth = {bandwidths[k]:.2f}',fontsize=11,pad=14)
        ax.set(xlabel='Subset regret gap',xlim=(grid[0],grid[-1]),ylim=(0,ymax))
        ax.axvline(0,color='#777777',lw=.8,zorder=1)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',color='#eeeeee',lw=.6)
        ax.set_axisbelow(True)
    axes[0,0].set_ylabel('Density (area under each curve = 1)')
    fig.suptitle('Smoothed subset regret-gap distributions',fontsize=16,y=.98)
    fig.legend(handles=[Line2D([],[],color=COLORS[c],lw=2,label=LABELS[c]) for c in 'ABCD'],
               loc='upper center',bbox_to_anchor=(.5,.92),ncol=2,frameon=False)
    fig.text(.5,.82,f'Gaussian-kernel KDE, not a fitted normal curve. Equal weight for each of {len(seeds)} matched seeds.',
             ha='center',fontsize=10)
    fig.text(.5,.18,'Small colored ticks show actual observations; curve height is density, not a count or probability at a point.',
             ha='center',fontsize=10)
    fig.text(.5,.105,'All conditions within a size use the same smoothing bandwidth. Shapes and peaks depend on smoothing.\nOverlapping subsets are dependent; these curves do not provide confidence intervals or tests of condition effects.',
             ha='center',fontsize=9,linespacing=1.6)
    fig.text(.5,.025,'Complementary subsets have opposite gaps; size-3 distributions are symmetric by construction. Positive gaps alone do not establish collusion.',
             ha='center',fontsize=9)
    return fig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--formats',nargs='+',choices=['svg','pdf','png'],default=['svg'])
    parser.add_argument('--bandwidth-scale',type=float,default=1,help='Exploratory smoothing multiplier; default 1')
    args=parser.parse_args()
    if not math.isfinite(args.bandwidth_scale) or args.bandwidth_scale<=0:
        parser.error('--bandwidth-scale must be finite and positive')
    source=args.batch.resolve()/'analysis/results.json';subset_source=source.with_name('subsets.csv')
    points,seeds=load_points(source,subset_source)
    grid,curves,bandwidths=compute_curves(points,seeds,args.bandwidth_scale)
    out=args.output_dir.resolve() if args.output_dir else source.parent/'kde-plots'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True,exist_ok=False)
    fig=make_figure(points,seeds,grid,curves,bandwidths)
    for ext in dict.fromkeys(args.formats):fig.savefig(out/f'subset-gap-kde.{ext}',dpi=180)
    plt.close(fig)
    with (out/'density_curves.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['condition','subset_size','regret_gap','density','bandwidth'])
        for (c,k),density in curves.items():
            w.writerows((c,k,float(x),float(y),bandwidths[k]) for x,y in zip(grid,density))
    with (out/'observed_scores.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['condition','seed','size','members','regret_gap'])
        w.writerows((r['condition'],r['seed'],r['size'],json.dumps(r['members']),r['regret_gap']) for r in points)
    areas={f'{c}-size{k}':float(np.trapezoid(d,grid)) for (c,k),d in curves.items()}
    if any(abs(a-1)>1e-4 for a in areas.values()):raise ValueError('Insufficient grid support for density normalization')
    provenance=dict(sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,subset_source)},
                    seeds=seeds,points=len(points),bandwidth_scale=args.bandwidth_scale,bandwidths=bandwidths,
                    bandwidth_rule='Pooled population SD within size times per-condition subset-score count^(-1/5), times multiplier; display heuristic only',
                    weighting='Equal-weight mean of seed-specific densities; all seed scores retained',
                    grid_points=len(grid),integrated_areas=areas,normal_fit=False,inferential=False,
                    matplotlib_version=matplotlib.__version__,numpy_version=np.__version__)
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    for name in ['plot_subset_kde.py','plot_subset_distributions.py','plot_abcd_separate.py']:
        shutil.copyfile(Path(__file__).with_name(name),out/name)
    print(json.dumps({'output':str(out),'bandwidths':bandwidths,'area_range':[min(areas.values()),max(areas.values())]},indent=2))


if __name__=='__main__':main()
