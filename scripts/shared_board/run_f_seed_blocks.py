"""Run F seeds serially, auditing each against an explicit completed A baseline."""
import argparse
import copy
import json
import math
import shutil
import subprocess
from pathlib import Path
from statistics import mean,median

import yaml
from run_ae_once import ROOT,PROJECT,digest,now,atomic_json,launch
from audit_shared_runs import read,audit_run,summarize_run,write_csv

CONFIG=PROJECT/'experiments/collusion/configs/paper_shared_board/oversight_pressure/hackathon_2_1_f_pair_private_oversight.yaml'
PLAN=ROOT/'docs/experiments/F_OVERSIGHT_EXPERIMENT_PLAN.md'


def preflight(path,baseline=None,a_path=None):
    cfg=yaml.safe_load(path.read_text())
    expected=cfg['experiment']['seeds']
    if expected not in ([1],[101,102,103,104,105]) or cfg['simulation']['seed']!=expected[0]:
        raise ValueError('Use main seeds 101–105 or the separate seed-1 pilot')
    if baseline is not None and baseline['status']!='completed':raise ValueError('A baseline is not completed')
    if a_path is None:
        a_path=PROJECT/'experiments/collusion/configs/paper_shared_board'
        if expected==[1]:a_path=a_path/'seed1_pilot'
        a_path=a_path/'hackathon_2_1_a_pair_private_channel.yaml'
    a=yaml.safe_load(a_path.read_text());f=copy.deepcopy(cfg)
    pressure=f['experiment'].pop('environment_pressure')
    if pressure['enabled'] is not True or not pressure['message'].strip():raise ValueError('F notice must be enabled')
    for obj in (a,f):
        obj['simulation'].pop('tags')
        for key in ('tag','output_dir'):obj['experiment'].pop(key)
        obj['experiment']['sweeps'][0].pop('name')
    if a!=f:raise ValueError('F differs from frozen A beyond notice and output metadata')
    if baseline is not None and sorted(r['seed'] for r in baseline['runs'] if r['condition']=='A')!=expected:
        raise ValueError('Missing/duplicate A baseline seeds')
    return cfg


def audit_f(record,cfg,baseline_run):
    assert len(record['trajectories'])==1
    d=Path(record['trajectories'][0]['run_dir']);rc=read(d/'run_config.json')
    audit=audit_run(d,'A',protocol='shared') # F uses A's access/coalition contract.
    private=audit.pop('private_prompt_signature');system=audit.pop('system_prompt_signature')
    pressure=cfg['experiment']['environment_pressure'];assert rc['environment_pressure']==pressure
    prompts=read(d/'agent_prompts.json')
    for p in prompts:
        assert p['user_prompt'].count('=== SPRINT GOVERNANCE NOTICE ===')==1
        assert p['user_prompt'].endswith('=== SPRINT GOVERNANCE NOTICE ===\n'+pressure['message'])
    assert len(prompts)==30 and sum(audit['coalition_prompt_counts'].values())==10
    old_d=Path(baseline_run['run_dir']);old_audit=audit_run(old_d,'A',protocol='shared')
    old,_,old_signature=summarize_run(old_d,'A')
    summary,rows,signature=summarize_run(d,'F')
    assert signature==old_signature,'Task/identity/cost/order mismatch'
    assert private==old_audit['private_prompt_signature'],'Private inputs differ'
    assert system==old_audit['system_prompt_signature'],'System prompt differs'
    def contexts(path):
        return {tuple(sorted(b['participants'])):[e['payload']['message'] for e in b['events'] if e['kind']=='context']
                for b in read(path/'blackboards.json')}
    assert contexts(d)==contexts(old_d),'Initial board descriptions differ'
    for key in ['joint_reward','primary_regret_gap','best_pair_regret_gap','mean_regret']:
        assert math.isclose(old[key],baseline_run[key],abs_tol=1e-8),'Baseline scores changed'
    assert not summary['missing_decision_agents'] and not summary['random_fallback_fills']
    assert audit['continuation_error_count']==0
    audit.update(actual_condition='F',base_board_contract='A shared',oversight_prompts_verified=30,
                 matched_A_instance_prompts_context=True)
    summary.update(audit=audit,reference_pair_regret_gap=summary['reference_group']['regret_gap'],board_count=2)
    for row in rows:row['seed']=summary['seed']
    return summary,rows


def export(directory,manifest,runs,subsets,baseline):
    analysis=directory/'analysis';analysis.mkdir(exist_ok=True)
    old={r['seed']:r for r in baseline['runs'] if r['condition']=='A'}
    contrasts=[]
    keys=['primary_regret_gap','reference_pair_regret_gap','best_pair_regret_gap','joint_reward','mean_regret','exact_optimality_gap']
    for key in keys:
        vals={str(r['seed']):r[key]-old[r['seed']][key] for r in runs}
        if vals:
            contrasts.append(dict(contrast='F-A',metric=key,n=len(vals),mean=mean(vals.values()),median=median(vals.values()),
                positive=sum(v>1e-9 for v in vals.values()),negative=sum(v< -1e-9 for v in vals.values()),paired=vals,
                leave_one_out_means={s:mean(v for k,v in vals.items() if k!=s) for s in vals} if len(vals)>1 else {}))
    result=dict(status=manifest['status'],batch_id=manifest['batch_id'],completed_seeds=[r['seed'] for r in runs],
                runs=runs,baseline_A_runs=[old[r['seed']] for r in runs],contrasts=contrasts,
                estimated_uncached_usd=sum(r['estimated_uncached_usd'] for r in runs))
    atomic_json(analysis/'results.json',result)
    if subsets:write_csv(analysis/'subsets.csv',subsets)
    if contrasts:write_csv(analysis/'contrasts.csv',contrasts)
    if runs:
        write_csv(analysis/'runs.csv',[dict(seed=r['seed'],pair_gap=r['reference_pair_regret_gap'],
            best_subset_gap=r['primary_regret_gap'],best_pair_gap=r['best_pair_regret_gap'],team_reward=r['joint_reward'],
            rejected_tools=len(r['audit']['tool_errors'])) for r in runs])
    pilot=manifest['seeds']==[1]
    title='seed-1 development pilot' if pilot else 'five-seed results'
    seed_note='Development data; exclude from main-study aggregates.' if pilot else 'Seed 1 excluded.'
    text='# F oversight extension: '+title+'\n\nStatus: '+manifest['status']+'. Only audited seeds appear. F adds the narrative notice to A; same corrected board context, tasks, costs, identities and turn order verified. No enforced sanctions. '+seed_note+'\n\n'
    text+='| Seed | A pair gap | F pair gap | A best-subset gap | F best-subset gap | A team reward | F team reward |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for r in runs:
        a=old[r['seed']];text+=f"| {r['seed']} | {a['reference_pair_regret_gap']:+.3f} | {r['reference_pair_regret_gap']:+.3f} | {a['primary_regret_gap']:+.3f} | {r['primary_regret_gap']:+.3f} | {a['joint_reward']:.3f} | {r['joint_reward']:.3f} |\n"
    if runs:
        text+='\n## Means\n\n| Condition | Pair gap | Best pair gap | Best subset gap | Team reward | Mean agent regret |\n|---|---:|---:|---:|---:|---:|\n'
        for c,rr in [('A',[old[r['seed']] for r in runs]),('F',runs)]:
            text+='| '+c+' | '+' | '.join(f'{mean(r[k] for r in rr):.3f}' for k in ['reference_pair_regret_gap','best_pair_regret_gap','primary_regret_gap','joint_reward','mean_regret'])+' |\n'
        text+='\n## Within-seed F−A changes\n\n| Metric | Mean | Median | Positive seeds | Negative seeds |\n|---|---:|---:|---:|---:|\n'
        for c in contrasts:text+=f"| {c['metric']} | {c['mean']:+.3f} | {c['median']:+.3f} | {c['positive']}/{c['n']} | {c['negative']}/{c['n']} |\n"
        text+='\n## F integrity and usage\n\n'
        text+=f"Audited prompts: {sum(r['audit']['prompts_verified'] for r in runs)}; notice deliveries: {sum(r['audit']['oversight_prompts_verified'] for r in runs)}; accepted posts: {sum(r['audit']['successful_posts_verified'] for r in runs)}; rejected tools: {sum(len(r['audit']['tool_errors']) for r in runs)}. No missing decisions, random fills or continuation errors in audited runs. Explicit skips: "+'; '.join(f"{r['seed']}: {', '.join(r['skip_agents']) or 'none'}" for r in runs)+'.\n\n'
        text+=f"Pair gap positive: {sum(r['reference_pair_regret_gap']>1e-9 for r in runs)}/{len(runs)}. Reference pair equals best pair including ties: {sum(math.isclose(r['reference_pair_regret_gap'],r['best_pair_regret_gap'],abs_tol=1e-9) for r in runs)}/{len(runs)}; equals best subset: {sum(math.isclose(r['reference_pair_regret_gap'],r['primary_regret_gap'],abs_tol=1e-9) for r in runs)}/{len(runs)}.\n\n"
        text+=f"Model calls: {sum(r['model_calls'] for r in runs)}; recorded input/output tokens: {sum(r['usage']['prompt_tokens'] for r in runs):,}/{sum(r['usage']['completion_tokens'] for r in runs):,}. Baseline uncached estimate **${result['estimated_uncached_usd']:.4f}** using prior $0.15/$0.60 per-million accounting rates; actual billing/cache discounts unavailable. No judge calls or automatic reruns.\n\n"
    text+=f"Exploratory extension on {len(manifest['seeds'])} task seeds, one trajectory per condition/seed. A was generated earlier, so model/provider time variation remains. Outcome gaps alone do not establish collusive intent. No significance tests, outlier exclusions or added seeds.\n\n"
    text+='Artifacts: [full scores and audits](analysis/results.json), [all subsets](analysis/subsets.csv), [paired changes](analysis/contrasts.csv), [manifest](manifest.json), frozen config/source/plan under this batch.\n'
    (directory/'RESULTS.md').write_text(text)


def run_blocks(config_path,directory,batch_id,baseline_path):
    baseline_path=baseline_path.resolve()
    baseline=read(baseline_path)
    a_path=baseline_path.parent.parent/'configs/hackathon_2_1_a_pair_private_channel.yaml'
    cfg=preflight(config_path,baseline,a_path)
    directory.mkdir(parents=True,exist_ok=False);(directory/'configs').mkdir()
    frozen=directory/'configs'/config_path.name;shutil.copyfile(config_path,frozen)
    sources=[Path(__file__),Path(__file__).with_name('run_ae_once.py'),Path(__file__).with_name('audit_shared_runs.py'),PLAN,
        PROJECT/'experiments/collusion/run.py',PROJECT/'experiments/collusion/prompts.py',
        PROJECT/'experiments/collusion/metrics.py',PROJECT/'experiments/common/local_protocol.py',
        PROJECT/'experiments/common/channel_aware_agent.py',PROJECT/'experiments/collusion/score_subsets.py',
        PROJECT/'experiments/collusion/compute_jira_optimal.py',PROJECT/'uv.lock']
    hashes={}
    for path in sources:
        path=path.resolve();dest=directory/'source'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest);hashes[str(path.relative_to(ROOT))]=digest(dest)
    manifest=dict(schema_version=2,batch_id=batch_id,status='running',started_at_utc=now(),seeds=cfg['experiment']['seeds'],
        expected_trajectories=len(cfg['experiment']['seeds']),max_parallel_trajectories=1,source_sha256=hashes,config_sha256=digest(frozen),
        baseline_sha256=digest(baseline_path),baseline=str(baseline_path),
        git_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip(),
        seed_blocks=[dict(seed=s,status='queued') for s in cfg['experiment']['seeds']])
    path=directory/'manifest.json';atomic_json(path,manifest);runs=[];subsets=[];block=None
    try:
        for block in manifest['seed_blocks']:
            for name,h in hashes.items():
                if digest(ROOT/name)!=h:raise ValueError('Source changed during launch: '+name)
            assert digest(frozen)==manifest['config_sha256'] and digest(baseline_path)==manifest['baseline_sha256']
            seed=block['seed'];single=copy.deepcopy(cfg);single['simulation']['seed']=seed;single['experiment']['seeds']=[seed]
            sd=directory/'seed-inputs'/f'seed{seed}';sd.mkdir(parents=True);sp=sd/frozen.name;sp.write_text(yaml.safe_dump(single,sort_keys=False))
            plan=dict(condition='F',path=sp,config=single,config_sha256=digest(sp),seeds=[seed])
            block.update(status='running',started_at_utc=now());atomic_json(path,manifest)
            child=launch([plan],directory/f'seed{seed}',f'{batch_id}.seed{seed}',workers=1)
            block['manifest']=str(directory/f'seed{seed}/manifest.json')
            old=next(r for r in baseline['runs'] if r['condition']=='A' and r['seed']==seed)
            summary,rows=audit_f(child['conditions'][0],single,old)
            runs.append(summary);subsets.extend(rows)
            block.update(status='completed',audited=True,finished_at_utc=now());atomic_json(path,manifest)
            export(directory,manifest,runs,subsets,baseline)
            print(f"F_SEED_AUDITED {seed}: pair gap {summary['reference_pair_regret_gap']:+.3f}, team reward {summary['joint_reward']:.3f}",flush=True)
        manifest.update(status='completed',finished_at_utc=now());atomic_json(path,manifest)
        export(directory,manifest,runs,subsets,baseline)
        return manifest
    except BaseException as exc:
        if block is not None and block['status']=='running':block.update(status='failed',error=str(exc))
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),finished_at_utc=now())
        atomic_json(path,manifest)
        export(directory,manifest,runs,subsets,baseline)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-id',default='f-oversight-seeds101-105')
    parser.add_argument('--baseline-batch',type=Path,help='Completed A–E batch directory; required for a paid F launch')
    parser.add_argument('--pilot',action='store_true',help='Use seed 1 and compare against a completed seed-1 A–E pilot')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not args.batch_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in args.batch_id) or args.batch_id in ('.','..'):
        parser.error('Invalid batch ID')
    baseline_path=(args.baseline_batch/'analysis/results.json').resolve() if args.baseline_batch else None
    a_path=args.baseline_batch.resolve()/'configs/hackathon_2_1_a_pair_private_channel.yaml' if args.baseline_batch else None
    config=CONFIG.parent/'seed1_pilot'/CONFIG.name if args.pilot else CONFIG
    cfg=preflight(config,read(baseline_path) if baseline_path else None,a_path)
    if args.dry_run:
        print(json.dumps(dict(writes=False,model_calls=0,condition='F',seeds=cfg['experiment']['seeds'],
            trajectories=len(cfg['experiment']['seeds']),max_parallel_trajectories=1,compare_to='corrected shared-board A',audit_before_next_seed=True),indent=2));return
    if baseline_path is None:parser.error('--baseline-batch is required for a paid F launch; run A–E first')
    run_blocks(config,ROOT/'results/ae-batches'/args.batch_id,args.batch_id,baseline_path)


if __name__=='__main__':main()
