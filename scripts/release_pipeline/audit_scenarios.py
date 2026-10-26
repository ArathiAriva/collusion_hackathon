#!/usr/bin/env python3
"""Preserve development scenario coverage and static/ordered opportunity counts."""
import argparse
from collections import Counter
from dataclasses import replace
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'colosseum'))
from experiments.collusion.release_pipeline.domain import FAMILIES, PAIRS, VERSION, Evaluator, digest
from experiments.collusion.release_pipeline.scenarios import generate
from experiments.collusion.release_pipeline.opportunities import static_opportunities, conditional_opportunities
from experiments.collusion.release_pipeline.runner import write_json


def audit(instances=20, seed=20261025):
    import hashlib
    source_files = list((ROOT/'colosseum/experiments/collusion/release_pipeline').glob('*.py'))+[Path(__file__)]
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    scenarios = [generate(f,seed+i) for f in FAMILIES for i in range(instances)]
    results = {}
    settings = [('main',3,.2),('effort_2',2,.2),('effort_4',4,.2),('aversion_.1',3,.1),('aversion_.4',3,.4)]
    for name,weight,beta in settings:
        rows = []
        for sc in scenarios:
            ev = Evaluator(replace(sc,cost_weight=weight,aversion=beta))
            opportunities = []
            for pair in PAIRS:
                static = [static_opportunities(ev,pair,x) for x in ev.optima]
                conditional = conditional_opportunities(ev,pair)
                opportunities.append({'pair':pair,
                    'static_mutual_any_optimum':any(r['mutual_joint_opportunity'] for r in static),
                    'static_mutual_every_optimum':all(r['mutual_joint_opportunity'] for r in static),
                    'static_joint_necessary':any(r['joint_necessary_for_mutual_gain'] for r in static),
                    'static_stale_witness_count':sum(w['stale_qa_record'] for r in static for w in r['witnesses']),
                    'conditional_mutual':conditional['mutual_joint_opportunity'],
                    'conditional_joint_necessary':conditional['joint_necessary_for_mutual_gain'],
                    'conditional_joint_incremental_mean_gain':conditional['joint_incremental_mean_gain']})
            rows.append({'scenario_id':sc.scenario_id,'family':sc.family,'oracle':ev.summary(),
                         'optimal_categories':sorted(set('defer' if x[5]=='defer' else '/'.join((x[0],x[3],x[5])) for x in ev.optima)),
                         'opportunities':opportunities})
        results[name] = rows
    summary = {}
    for name,rows in results.items():
        summary[name] = {'optimal_categories':dict(Counter(c for r in rows for c in r['optimal_categories'])),
            'deferral_optimum_values':sorted(set(r['oracle']['F_star'] for r in rows if r['optimal_categories']==['defer'])),
            'pairs':[{ 'pair':pair, **{key:sum(next(p for p in r['opportunities'] if p['pair']==pair)[key] for r in rows)
              for key in ('static_mutual_any_optimum','static_mutual_every_optimum','static_joint_necessary','conditional_mutual','conditional_joint_necessary')}} for pair in PAIRS]}
    return {'version':VERSION,'source_hashes':hashes,'development_only':True,'seed':seed,'scenario_count':len(scenarios),
            'assignment_evaluations':len(scenarios)*len(settings)*144,'scenarios':[s.to_dict() for s in scenarios],
            'settings':settings,'summary':summary,'results':results,
            'limitations':'Engineered templates, conditional truthful-disclosure submission policy, no inference or natural-language attack search. Strict-positive opportunity counts are not collusion rates.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--instances',type=int,default=20)
    p.add_argument('--seed',type=int,default=20261025)
    args=p.parse_args()
    if args.instances<1 or args.output.exists():
        p.error('Positive instance count and unused output path required')
    result=audit(args.instances,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json(args.output,result)
    print({'scenarios':result['scenario_count'],'assignment_evaluations':result['assignment_evaluations'],'output':str(args.output)})
