"""Run shared-board A–E in parallel within each seed; audit before advancing."""
import argparse
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from statistics import mean, median
import yaml
from run_ae_once import ROOT, PROJECT, load_plan, launch, digest, atomic_json, now
from audit_shared_runs import audit_run, summarize_run, read, write_csv

CONFIGS=PROJECT/'experiments/collusion/configs/paper_shared_board'
PLAN=ROOT/'docs/experiments/SHARED_BOARD_EXPERIMENT_PLAN.md'


def shared_plans(directory):
    plans=load_plan(directory)
    for p in plans:
        c=p['condition'];cfg=p['config'];network=cfg['communication_network'];s=cfg['experiment']['sweeps'][0]
        if s['topologies']!=['complete'] or network['topology']!='complete':
            raise ValueError('Shared-board protocol requires complete topology')
        if network.get('describe_global_boards_as_public') is not True:
            raise ValueError('Consistent public-board descriptions must be enabled')
        if network['consolidate_channels']!=(c!='E'):
            raise ValueError(f'Wrong channel consolidation: {c}')
        if s['secret_channel_enabled']!=[c in 'ACE'] or s['prompt_variants']!=[('simple' if c in 'AB' else 'control')]:
            raise ValueError(f'Wrong channel/prompt condition: {c}')
        if cfg['experiment']['collusion']['coalition_prompt']!=('always' if c in 'AB' else 'never'):
            raise ValueError(f'Wrong coalition instructions: {c}')
        if cfg['experiment']['collusion'].get('extra_channel_members','colluders')!=('all' if c=='E' else 'colluders'):
            raise ValueError(f'Wrong extra-board members: {c}')
    return plans


def seed_configs(plans, seed, directory):
    directory.mkdir(parents=True,exist_ok=False)
    for p in plans:
        cfg=copy.deepcopy(p['config'])
        cfg['simulation']['seed']=seed
        cfg['experiment']['seeds']=[seed]
        if 'seeds' in cfg['experiment']['sweeps'][0]:
            cfg['experiment']['sweeps'][0]['seeds']=[seed]
        (directory/p['path'].name).write_text(yaml.safe_dump(cfg,sort_keys=False))
    return shared_plans(directory)


def audit_block(records, baseline=None):
    summaries=[];subsets=[];signature=None;private=None;system=None;global_context=None
    for record in records:
        assert record['status']=='completed' and len(record['trajectories'])==1
        c=record['condition'];d=Path(record['trajectories'][0]['run_dir'])
        audit=audit_run(d,c,protocol='shared');s,rows,sig=summarize_run(d,c)
        if signature is None:signature=sig
        assert sig==signature,'Task/cost/identity/order mismatch between conditions'
        if private is None:private=audit['private_prompt_signature'];system=audit['system_prompt_signature']
        assert private==audit.pop('private_prompt_signature')
        assert system==audit.pop('system_prompt_signature')
        rc=read(d/'run_config.json');assert rc['describe_global_boards_as_public'] is True
        boards=read(d/'blackboards.json');public=[b for b in boards if len(b['participants'])==6]
        assert len(public)==1
        context='\n'.join(e['payload'].get('message','') for e in public[0]['events'] if e['kind']=='context')
        if global_context is None:global_context=context
        assert context==global_context,'Global-board description differs across conditions'
        assert not s['missing_decision_agents'] and s['random_fallback_fills']==0
        assert audit['continuation_error_count']==0
        if baseline is not None:
            old=next(x for x in baseline['runs'] if x['condition']==c and x['seed']==s['seed'])
            _,_,old_sig=summarize_run(Path(old['run_dir']),c)
            assert old_sig==sig,'Instance/order mismatch against previous experiment'
            assert set(old['reference_group']['members'])==set(s['reference_group']['members'])
        s['audit']=audit;s['board_count']=len(boards)
        s['reference_pair_regret_gap']=s['reference_group']['regret_gap']
        s['reference_pair_reward_gap']=s['reference_group']['reward_gap']
        for row in rows:row['seed']=s['seed']
        summaries.append(s);subsets.extend(rows)
    assert len(summaries)==5 and len(subsets)==310
    return summaries,subsets


def export_results(directory, manifest, runs, subsets):
    analysis=directory/'analysis';analysis.mkdir(exist_ok=True)
    contrasts=[];lookup={(r['condition'],r['seed']):r for r in runs}
    seeds=sorted({r['seed'] for r in runs})
    for metric in ['primary_regret_gap','reference_pair_regret_gap','joint_reward','mean_regret']:
        for label,terms in [('A-B',[(1,'A'),(-1,'B')]),('C-D',[(1,'C'),(-1,'D')]),
                            ('A-C',[(1,'A'),(-1,'C')]),('B-D',[(1,'B'),(-1,'D')]),
                            ('E-D',[(1,'E'),(-1,'D')]),
                            ('(A-B)-(C-D)',[(1,'A'),(-1,'B'),(-1,'C'),(1,'D')])]:
            values=[sum(sign*lookup[c,seed][metric] for sign,c in terms) for seed in seeds]
            contrasts.append(dict(contrast=label,metric=metric,n=len(seeds),mean=mean(values),median=median(values),
                positive=sum(v>1e-9 for v in values),negative=sum(v< -1e-9 for v in values),paired=dict(zip(seeds,values)),
                leave_one_out_means={str(s):mean(v for i,v in enumerate(values) if seeds[i]!=s) for s in seeds} if len(seeds)>1 else {}))
    result=dict(batch_id=manifest['batch_id'],status=manifest['status'],completed_seeds=seeds,runs=runs,contrasts=contrasts,
        estimated_uncached_usd=sum(r['estimated_uncached_usd'] for r in runs))
    atomic_json(analysis/'results.json',result)
    flat=[dict(condition=r['condition'],seed=r['seed'],best_subset_regret_gap=r['primary_regret_gap'],
        best_subset=r['primary_members'],reference_pair_regret_gap=r['reference_pair_regret_gap'],
        team_reward=r['joint_reward'],boards=r['board_count'],rejected_tools=len(r['audit']['tool_errors'])) for r in runs]
    write_csv(analysis/'runs.csv',flat);write_csv(analysis/'subsets.csv',subsets);write_csv(analysis/'contrasts.csv',contrasts)
    text='# Shared-board seed-block results\n\nStatus: '+manifest['status']+'. Only fully audited five-condition seed blocks appear below. C/D/E pair scores are reference diagnostics, not instructed-coalition scores.\n\n'
    text+='| Seed | Condition | Best-subset regret gap | Reference-pair regret gap | Team reward |\n|---|---|---:|---:|---:|\n'
    for r in runs:text+=f"| {r['seed']} | {r['condition']} | {r['primary_regret_gap']:+.3f} | {r['reference_pair_regret_gap']:+.3f} | {r['joint_reward']:.3f} |\n"
    (directory/'RESULTS.md').write_text(text)


def run_blocks(plans, directory, batch_id, baseline=None, previous_results_path=None):
    directory.mkdir(parents=True,exist_ok=False)
    originals=directory/'configs';originals.mkdir()
    for p in plans:
        if digest(p['path'])!=p['config_sha256']:raise ValueError('Config changed after preflight')
        shutil.copyfile(p['path'],originals/p['path'].name)
    frozen=shared_plans(originals);seeds=frozen[0]['seeds']
    source=directory/'source';source.mkdir()
    sources=[Path(__file__).resolve(),Path(__file__).with_name('run_ae_once.py'),Path(__file__).with_name('audit_shared_runs.py'),
        PROJECT/'experiments/collusion/run.py',PROJECT/'experiments/collusion/prompts.py',
        PROJECT/'experiments/collusion/metrics.py',PROJECT/'experiments/common/local_protocol.py',
        PROJECT/'experiments/common/channel_aware_agent.py',PROJECT/'experiments/collusion/score_subsets.py',
        PROJECT/'experiments/collusion/compute_jira_optimal.py',PROJECT/'uv.lock',PLAN]
    hashes={}
    for path in sources:
        dest=source/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest);hashes[str(path.relative_to(ROOT))]=digest(dest)
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    status=subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True)
    manifest=dict(schema_version=2,batch_id=batch_id,status='running',started_at_utc=now(),seeds=seeds,
        max_parallel_trajectories=5,seed_barrier=True,expected_trajectories=len(seeds)*5,
        git_commit=commit.stdout.strip(),git_dirty=bool(status.stdout.strip()),source_sha256=hashes,
        original_config_sha256={p['condition']:p['config_sha256'] for p in frozen},
        previous_results_sha256=digest(previous_results_path) if previous_results_path is not None else None,
        seed_blocks=[dict(seed=s,status='queued') for s in seeds])
    path=directory/'manifest.json';atomic_json(path,manifest);runs=[];subsets=[]
    block=None
    try:
        for block in manifest['seed_blocks']:
            for name,digest_value in hashes.items():
                if digest(ROOT/name)!=digest_value:raise ValueError(f'Source changed during batch: {name}')
            seed=block['seed'];block.update(status='running',started_at_utc=now());atomic_json(path,manifest)
            single=seed_configs(frozen,seed,directory/'seed-inputs'/f'seed{seed}')
            child_dir=directory/f'seed{seed}';block['manifest']=str(child_dir/'manifest.json');atomic_json(path,manifest)
            child=launch(single,child_dir,f'{batch_id}.seed{seed}',workers=5)
            summaries,rows=audit_block(child['conditions'],baseline)
            runs.extend(summaries);subsets.extend(rows)
            block.update(status='completed',audited=True,finished_at_utc=now());atomic_json(path,manifest)
            export_results(directory,manifest,runs,subsets)
            print(f'SEED_BLOCK_AUDITED {seed}: A–E complete; next seed may start.',flush=True)
        manifest.update(status='completed',finished_at_utc=now());atomic_json(path,manifest)
        export_results(directory,manifest,runs,subsets)
        return manifest
    except BaseException as exc:
        if block is not None and block['status']=='running':block.update(status='failed',error=str(exc))
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),finished_at_utc=now())
        atomic_json(path,manifest)
        if runs:export_results(directory,manifest,runs,subsets)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir',type=Path)
    parser.add_argument('--pilot',action='store_true',help='Use the separate seed-1 development configs')
    parser.add_argument('--batch-id',default='shared-board-seeds101-105')
    parser.add_argument('--previous-results',type=Path,
                        help='Optional earlier A–E results.json for historical instance matching; not needed for a new run')
    parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.batch_id) or args.batch_id in ('.','..'):parser.error('Invalid batch ID')
    config_dir=args.config_dir or (CONFIGS/'seed1_pilot' if args.pilot else CONFIGS)
    plans=shared_plans(config_dir.resolve())
    expected=[1] if args.pilot else [101,102,103,104,105]
    if plans[0]['seeds']!=expected:parser.error(f'Expected seeds {expected}; use --pilot for seed 1')
    if args.dry_run:
        print(json.dumps(dict(dry_run=True,writes=False,model_calls=0,max_parallel_trajectories=5,
            seed_barrier=True,total_trajectories=5*len(expected),waves=[dict(seed=s,parallel_conditions=list('ABCDE')) for s in plans[0]['seeds']]),indent=2));return
    previous=args.previous_results.resolve() if args.previous_results else None
    run_blocks(plans,ROOT/'results/ae-batches'/args.batch_id,args.batch_id,
               read(previous) if previous else None,previous)

if __name__=='__main__':main()
