"""Derive descriptive pair rankings, subset dispersion and top-subset inclusion."""
import argparse
import csv
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev, stdev

from plot_abcd_separate import load_runs
from plot_subset_distributions import load_points

TOL = 1e-9


def percentile(values, q):
    """Linear interpolation between ordered values, equivalent to numpy's default."""
    ordered = sorted(values)
    x = (len(ordered)-1)*q
    low, high = math.floor(x), math.ceil(x)
    return ordered[low] + (ordered[high]-ordered[low])*(x-low)


def pair_metrics(values, reference):
    # Compare with other pairs, excluding the reference itself. Ties receive half credit.
    others = list(values)
    index = next(i for i,v in enumerate(others) if abs(v-reference) <= TOL)
    others.pop(index)
    lower = sum(v < reference-TOL for v in others)
    tied = sum(abs(v-reference) <= TOL for v in others)
    return dict(reference_pair_gap=reference,
                reference_pair_percentile=100*(lower+.5*tied)/len(others),
                reference_pair_rank=1+sum(v > reference+TOL for v in others),
                best_pair_gap=max(values), distance_from_best_pair=max(values)-reference)


def size_metrics(rows, reference, n_agents, fraction):
    size = rows[0]['size']
    gaps = [r['regret_gap'] for r in rows]
    count = max(1, math.ceil(fraction*len(rows)))
    cutoff = sorted(gaps, reverse=True)[count-1]
    selected = [r for r in rows if r['regret_gap'] >= cutoff-TOL]
    overlap = [len(set(r['members']) & reference) for r in selected]
    baseline = {'both':size*(size-1)/(n_agents*(n_agents-1)),
                'one':2*size*(n_agents-size)/(n_agents*(n_agents-1)),
                'neither':(n_agents-size)*(n_agents-size-1)/(n_agents*(n_agents-1))}
    result = dict(subset_count=len(rows), gap_p90=percentile(gaps,.9),
                  gap_population_sd=pstdev(gaps), gap_iqr=percentile(gaps,.75)-percentile(gaps,.25),
                  mean_gap=mean(gaps), top_requested_count=count, top_actual_count=len(selected), top_cutoff=cutoff, top_has_both=int(2 in overlap))
    for label, number in [('both',2),('one',1),('neither',0)]:
        actual = 100*overlap.count(number)/len(overlap)
        result.update({f'top_{label}_count':overlap.count(number), f'top_{label}_pct':actual,
                       f'baseline_{label}_pct':100*baseline[label],
                       f'top_{label}_excess_pp':actual-100*baseline[label]})
    if abs(result['mean_gap']) > 1e-8:
        raise ValueError('Mean over a complete fixed-size subset enumeration must be zero')
    return result, selected


def write_csv(path, rows):
    with path.open('w') as f:
        w = csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--conditions', nargs='+', choices=list('ABCDE'), default=list('ABCD'))
    parser.add_argument('--top-fraction',type=float,default=.1)
    args=parser.parse_args()
    if not 0 < args.top_fraction <= 1:
        parser.error('--top-fraction must lie in (0,1]')
    source=args.batch.resolve()/'analysis/results.json'
    subset_source=source.with_name('subsets.csv')
    conditions=list(dict.fromkeys(args.conditions))
    if len(conditions)<2:
        parser.error('Select at least two distinct conditions')
    runs,seeds=load_runs(source, conditions=conditions)
    points,_=load_points(source,subset_source, conditions=conditions)
    pair_rows=[];size_rows=[];top_rows=[];flat={}
    for c in conditions:
        for seed in seeds:
            run=runs[c,seed];ref=set(run['reference_group']['members'])
            regrets={a['agent_name']:a['regret'] for a in run['agent_outcomes']}
            rows=[r for r in points if r['condition']==c and r['seed']==seed]
            for r in rows:
                inside=set(r['members']);outside=set(regrets)-inside
                computed=mean(regrets[a] for a in outside)-mean(regrets[a] for a in inside)
                if not math.isclose(computed,r['regret_gap'],abs_tol=1e-8):
                    raise ValueError(f'Subset score disagrees with agent regrets: {c}, {seed}')
            metrics=pair_metrics([r['regret_gap'] for r in rows if r['size']==2],run['reference_group']['regret_gap'])
            metrics.update(pair_mean_regret=mean(regrets[a] for a in ref),
                           outsider_mean_regret=mean(v for a,v in regrets.items() if a not in ref),
                           team_reward=run['joint_reward'], mean_agent_regret=mean(regrets.values()),
                           best_subset_gap=run['primary_regret_gap'])
            pair_rows.append(dict(condition=c,seed=seed,**metrics))
            flat[c,seed]=dict(metrics)
            for k in range(2,6):
                metrics,selected=size_metrics([r for r in rows if r['size']==k],ref,len(regrets),args.top_fraction)
                size_rows.append(dict(condition=c,seed=seed,size=k,**metrics))
                flat[c,seed].update({f'size{k}_{key}':value for key,value in metrics.items()})
                for r in selected:
                    top_rows.append(dict(condition=c,seed=seed,size=k,members=json.dumps(r['members']),
                                         regret_gap=r['regret_gap'],reference_members_inside=len(set(r['members'])&ref),
                                         cutoff=metrics['top_cutoff']))
    summary=[]
    for c in conditions:
        for key in flat[c,seeds[0]]:
            values=[flat[c,s][key] for s in seeds]
            summary.append(dict(condition=c,metric=key,mean=mean(values),median=median(values),
                                sample_sd_across_seeds=stdev(values),n_seeds=len(seeds)))
    contrasts=[]
    terms={'A-B':[(1,'A'),(-1,'B')],'C-D':[(1,'C'),(-1,'D')],
           'A-C':[(1,'A'),(-1,'C')],'B-D':[(1,'B'),(-1,'D')],
           '(A-B)-(C-D)':[(1,'A'),(-1,'B'),(-1,'C'),(1,'D')],
           'E-D':[(1,'E'),(-1,'D')]}
    terms={label:weights for label,weights in terms.items() if all(c in conditions for _,c in weights)}
    if not terms:
        terms={f'{conditions[1]}-{conditions[0]}':[(1,conditions[1]),(-1,conditions[0])]}
    for label,weights in terms.items():
        for key in flat[conditions[0],seeds[0]]:
            vals=[sum(w*flat[c,s][key] for w,c in weights) for s in seeds]
            contrasts.append(dict(contrast=label,metric=key,mean=mean(vals),median=median(vals),
                                  sample_sd_of_paired_differences=stdev(vals),
                                  positive_seeds=sum(v>TOL for v in vals),negative_seeds=sum(v< -TOL for v in vals),
                                  n_seeds=len(seeds),paired_values=dict(zip(seeds,vals))))
    out=args.output_dir.resolve() if args.output_dir else source.parent/'derived-subset-metrics'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True,exist_ok=False)
    write_csv(out/'pair_metrics_by_seed.csv',pair_rows)
    write_csv(out/'subset_metrics_by_size_seed.csv',size_rows)
    write_csv(out/'top_subsets.csv',top_rows)
    write_csv(out/'condition_summary.csv',summary)
    write_csv(out/'paired_contrasts.csv',[{**r,'paired_values':json.dumps(r['paired_values'])} for r in contrasts])
    provenance=dict(sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,subset_source]},
                    seeds=seeds,conditions=conditions,top_fraction=args.top_fraction,tie_tolerance=TOL,
                    percentile='percent of other 14 pairs below reference, ties half-weighted; all ties = 50',
                    top_rule='ceil(fraction * subset count), include all ties at cutoff, separately within each size/run',
                    dispersion='population SD across enumerated subsets; sample SD across independent seeds',
                    baseline='uniform random fixed-size subset membership, descriptive combinatorial baseline',
                    exploratory=True)
    (out/'metrics.json').write_text(json.dumps(dict(provenance=provenance,pair_metrics=pair_rows,
        subset_metrics=size_rows,condition_summary=summary,paired_contrasts=contrasts),indent=2)+'\n')
    for name in ['derive_subset_metrics.py','plot_abcd_separate.py','plot_subset_distributions.py']:
        shutil.copyfile(Path(__file__).with_name(name),out/name)
    averages={(r['condition'],r['metric']):r['mean'] for r in summary}
    text='# Derived subset metrics: '+', '.join(conditions)+'\n\n'
    text+=f'Exploratory descriptive analysis of {len(seeds)} matched seeds: '+', '.join(map(str,seeds))+'. All seeds retained; no new model calls. Only A/B give the reference pair coalition instructions.\n\n'
    if set(conditions)=={'D','E'}:
        text+='D: global board only. E: global board plus all 15 pairwise private boards. Neither receives coalition instructions. The pair is a diagnostic reference in both conditions. E−D adds private communication opportunities for every pair.\n\n'
    text+='## Reference-pair performance\n\nCondition means; percentiles computed within each run against the other 14 pairs (ties half-weighted). Higher percentile is better; smaller distance from the best pair is better.\n\n'
    text+='| Condition | Pair gap | Pair percentile | Mean rank / 15 | Best pair gap | Distance from best pair | Pair regret | Outsider regret |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    keys=['reference_pair_gap','reference_pair_percentile','reference_pair_rank','best_pair_gap','distance_from_best_pair','pair_mean_regret','outsider_mean_regret']
    for c in conditions:text+='| '+c+' | '+' | '.join(f'{averages[c,k]:.2f}' for k in keys)+' |\n'
    text+='\n## Whole-run outcomes\n\n| Condition | Team reward | Mean agent regret | Best subset gap |\n|---|---:|---:|---:|\n'
    for c in conditions:text+='| '+c+' | '+' | '.join(f'{averages[c,k]:.2f}' for k in ['team_reward','mean_agent_regret','best_subset_gap'])+' |\n'
    text+='\n## Pair outcomes by seed\n\n| Condition | Seed | Pair gap | Percentile | Rank / 15 | Distance from best | Pair regret | Outsider regret |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for r in pair_rows:text+='| '+r['condition']+' | '+str(r['seed'])+' | '+' | '.join(f'{r[k]:.2f}' for k in ['reference_pair_gap','reference_pair_percentile','reference_pair_rank','distance_from_best_pair','pair_mean_regret','outsider_mean_regret'])+' |\n'
    text+='\n## Fixed-size distribution summaries\n\nMean across seeds. P90 uses linear interpolation. SD is population SD over all subsets of that size in a run; IQR = P75 − P25.\n\n| Size | Condition | P90 gap | Subset SD | IQR |\n|---|---|---:|---:|---:|\n'
    for k in range(2,6):
        for c in conditions:text+=f'| {k} | {c} | '+ ' | '.join(f'{averages[c,f"size{k}_{metric}"]:.2f}' for metric in ['gap_p90','gap_population_sd','gap_iqr'])+' |\n'
    text+=f'\n## Reference-pair inclusion in top subsets\n\nTop {100*args.top_fraction:g}% separately by subset size and run: select ceil(fraction × count), including all ties at the cutoff. For 10%, nominal counts per seed are 2/15 pairs, 2/20 triples, 2/15 quadruples and 1/6 quintuples; ties can increase these counts. Percentages below are averaged equally across seeds, not pooled over subsets.\n\n'
    text+='| Size | Condition | Mean top count | Both (%) | Exactly one (%) | Neither (%) | Both: excess vs uniform (pp) | Seeds with any both |\n|---|---|---:|---:|---:|---:|---:|---:|\n'
    for k in range(2,6):
        for c in conditions:text+=f'| {k} | {c} | '+' | '.join(f'{averages[c,f"size{k}_{metric}"]:.2f}' for metric in ['top_actual_count','top_both_pct','top_one_pct','top_neither_pct','top_both_excess_pp'])+f' | {sum(r["top_has_both"] for r in size_rows if r["condition"]==c and r["size"]==k)}/{len(seeds)} |\n'
    text+='\nUniform-subset baseline (both / exactly one / neither): sizes 2: 6.67 / 53.33 / 40%; 3: 20 / 60 / 20%; 4: 40 / 53.33 / 6.67%; 5: 66.67 / 33.33 / 0%. Higher inclusion is partly mechanical for large subsets. Baseline differences are descriptive, not significance tests.\n\n'
    text+='## Matched changes\n\nMeans of within-seed differences. Percentile and inclusion changes are percentage points.\n\n| Contrast | Pair gap | Percentile | Distance from best | Pair regret | Outsider regret | Top-pair inclusion: both (pp) |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for label in terms:
        text+='| '+label+' | '+' | '.join(f'{next(r["mean"] for r in contrasts if r["contrast"]==label and r["metric"]==k):+.2f}' for k in ['reference_pair_gap','reference_pair_percentile','distance_from_best_pair','pair_mean_regret','outsider_mean_regret','size2_top_both_pct'])+' |\n'
    text+='\n## Paired-change consistency\n\nPositive/negative counts describe the signed metric change, not necessarily improvement (lower regret/distance is better).\n\n| Contrast | Metric | Mean | Median | Positive seeds | Negative seeds |\n|---|---|---:|---:|---:|---:|\n'
    for r in contrasts:
        if r['metric'] in ['reference_pair_gap','reference_pair_percentile','distance_from_best_pair','team_reward','mean_agent_regret','best_pair_gap','best_subset_gap','size2_gap_population_sd']:
            text+=f"| {r['contrast']} | {r['metric']} | {r['mean']:+.2f} | {r['median']:+.2f} | {r['positive_seeds']}/{len(seeds)} | {r['negative_seeds']}/{len(seeds)} |\n"
    text+='\n## Interpretation and limits\n\nThese statistics summarize individual regret outcomes, not independent evidence of coordinated intent. Mean gap across the complete enumeration is zero at every fixed size (verified). Complementary subset gaps have opposite signs; size-3 distributions are symmetric. In fact, the maximum gap at fixed size always selects the lowest-regret agents, so “best pair” is the two lowest-regret agents. Dispersion measures inequality of individual regrets; the all-subset SD is a deterministic rescaling of individual-regret dispersion. For size 2, “both reference agents included” means the top pair is exactly the reference pair. No hypothesis tests or exclusions were added.\n\n'
    text+='Files: [per-seed pair metrics](pair_metrics_by_seed.csv), [per-size/per-seed metrics](subset_metrics_by_size_seed.csv), [selected top subsets](top_subsets.csv), [condition means/SD](condition_summary.csv), [paired differences](paired_contrasts.csv), [full results and provenance](metrics.json).\n'
    (out/'REPORT.md').write_text(text)
    print(out)


if __name__=='__main__':main()
