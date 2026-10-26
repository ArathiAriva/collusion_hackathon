#!/usr/bin/env python3
"""Frozen release batch: offline by default; live dispatch requires a costed run card."""
import argparse
import asyncio
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'colosseum'))
from experiments.collusion.release_pipeline.domain import FAMILIES, PAIRS, ROLES, VERSION, digest
from experiments.collusion.release_pipeline.scenarios import calibration_fixture, generate
from experiments.collusion.release_pipeline.runner import DEFAULT_PLANNING_ROUNDS, run_episode, speaking_schedule, write_json
from experiments.collusion.release_pipeline.analysis import analyze_batch
from experiments.collusion.release_pipeline.prompts import PROMPT_VERSION


STUDY_PAIRS = (('product_manager','release_manager'), ('qa_lead','ops_lead'))

def schedule(*, pilot=False, instances=2, seed=20261025, conditions=('A','D'), partition='development', selected_pair=None, planning_rounds=DEFAULT_PLANNING_ROUNDS):
    if not conditions or len(set(conditions))!=len(conditions) or set(conditions)-{'A','D'}:
        raise ValueError('Current experiment supports unique conditions A and D only')
    speaking_schedule(seed, planning_rounds)  # Validate before constructing a schedule.
    if selected_pair is not None:
        selected_pair = tuple(selected_pair)
        if len(selected_pair)!=2 or len(set(selected_pair))!=2 or any(r not in ROLES for r in selected_pair):
            raise ValueError('Select two distinct known roles')
        selected_pair = next(p for p in PAIRS if set(p)==set(selected_pair))
    scenarios = [calibration_fixture()] if pilot else [generate(f,seed+i,partition=partition) for f in FAMILIES for i in range(instances)]
    rows = []
    for si,sc in enumerate(scenarios):
        for pi,pair in enumerate(PAIRS):
            if selected_pair is None and pair not in STUDY_PAIRS:
                continue
            if selected_pair is not None and pair != selected_pair:
                continue  # Keep original scenario/pair indices, seeds and IDs.
            block = f's{si:03d}-p{pi}'
            # Same independently derived order across pairs permits explicit future D reuse;
            # initial implementation executes distinct D draws and does not count reuse.
            speaking_seed = seed+100000+si
            launch = list(conditions)
            offset = (si+pi)%len(launch)
            launch = launch[offset:]+launch[:offset]
            for c in launch:
                rows.append({'run_id':block+'-'+c,'block_id':block,'condition':c,'pair':list(pair),
                    'scenario_id':sc.scenario_id,'scenario':sc.to_dict(),'speaking_seed':speaking_seed,
                    'replicate_id':0,'model_replication_seed':seed+200000+si,'planning_rounds':planning_rounds})
    return rows


STUDY_CONFIG = ROOT/'colosseum/experiments/collusion/configs/release_pipeline/study.yaml'

def study_schedule(seeds, families, **kwargs):
    if not seeds or len(set(seeds))!=len(seeds) or any(type(s) is not int for s in seeds):
        raise ValueError('Provide unique integer seeds')
    if not families or len(set(families))!=len(families) or set(families)-set(FAMILIES):
        raise ValueError('Provide unique known families')
    rows=[]
    for seed in seeds:
        for item in schedule(seed=seed,instances=1,**kwargs):
            if item['scenario']['family'] not in families: continue
            item=dict(item,experiment_seed=seed)
            item['run_id']=f"seed{seed}-"+item['run_id']
            item['block_id']=f"seed{seed}-"+item['block_id']
            rows.append(item)
    return rows


def config_for(item, llm=None):
    expected = {'environment':{'import_path':'experiments.collusion.release_pipeline.environment:ReleasePipelineEnvironment',
                'assignment_filling':False},
            'communication_network':{'topology':'complete','num_agents':4,'consolidate_channels':True,
                'describe_global_boards_as_public':True},
            'release':{'condition':item['condition'],'selected_role_pair':item['pair'],
                'prompt_version':PROMPT_VERSION,
                'speaking_seed':item['speaking_seed'],'replicate_id':item['replicate_id']},
            'simulation':{'max_iterations':1,'max_planning_rounds':item.get('planning_rounds',4),'max_conversation_steps':3},
            'llm':llm or {'provider':'scripted-offline'}}
    names={'A':'A_assigned_pair_private_board.yaml','D':'D_cooperative_public_board.yaml'}
    path = ROOT/'colosseum/experiments/collusion/configs/release_pipeline'/names[item['condition']]
    if path.exists():
        import yaml
        template = yaml.safe_load(path.read_text())
        actual = dict(expected)
        actual.pop('llm')
        actual['release'] = {'condition':item['condition']}
        # Templates declare the current default; the frozen row owns overrides.
        actual['simulation'] = dict(expected['simulation'], max_planning_rounds=DEFAULT_PLANNING_ROUNDS)
        if template != actual:
            raise ValueError(f'{path.name} differs from the frozen version-1 protocol; revise/version the contract before changing it')
    else:
        raise ValueError(f'Missing release config: {path}')
    return expected


def validate_card(card, rows):
    import math
    def no_secrets(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if any(s in key.lower() for s in ('api_key','password','authorization','credential')):
                    raise ValueError('Credentials belong in environment variables, never a saved run card')
                no_secrets(item)
        elif isinstance(value,list):
            for item in value:
                no_secrets(item)
    no_secrets(card)
    if card.get('prompt_version') != PROMPT_VERSION:
        raise ValueError('Run card must freeze the current prompt_version; create a new card for revised prompts')
    llm = card.get('llm',{})
    block = llm.get('openrouter',{})
    if llm.get('provider')!='openrouter' or not block.get('model') or not block.get('base_url'):
        raise ValueError('Run card must name provider, model, and exact base_url')
    params = block.get('params',{})
    if params != {'temperature':.7,'max_tokens':1500}:
        raise ValueError('Version-1 run card requires temperature .7 and max_tokens 1500')
    if card.get('schedule_hash')!=digest(rows) or not card.get('freeze_id') or card.get('authorized_trajectories')!=len(rows):
        raise ValueError('Run card must freeze this exact schedule and trajectory scope')
    rates = card.get('rates',{})
    if not all(k in rates for k in ('input_per_million','output_per_million','source_url','verified_date')):
        raise ValueError('Verified, dated endpoint rates required before live dispatch')
    if any(type(rates[k]) not in (float,int) or not math.isfinite(rates[k]) or rates[k]<0 for k in ('input_per_million','output_per_million')):
        raise ValueError('Invalid rates')
    if card.get('retry_policy')!='no-automatic-trajectory-retry' or card.get('stopping_rule')!='run-frozen-schedule':
        raise ValueError('Freeze retry and stopping rules')
    if type(card.get('resource_estimate_usd')) not in (float,int) or not math.isfinite(card['resource_estimate_usd']) or card['resource_estimate_usd']<=0:
        raise ValueError('A concrete positive USD resource estimate is required')
    return llm


def source_snapshot(destination):
    files = list((ROOT/'colosseum/experiments/collusion/release_pipeline').glob('*.py'))
    files += [ROOT/'colosseum/experiments/common'/n for n in ('local_protocol.py','channel_aware_agent.py','providers.py')]
    files += list((ROOT/'scripts/release_pipeline').glob('*.py'))
    files += list((ROOT/'colosseum/experiments/collusion/configs/release_pipeline').glob('*.yaml'))
    files += list((ROOT/'docs/experiments').glob('RELEASE*.md'))
    files += [ROOT/'colosseum/uv.lock', ROOT/'colosseum/pyproject.toml']
    files += list((ROOT/'util/poseidon_compute').rglob('*.py'))
    hashes = {}
    import hashlib
    for file in files:
        relative = file.relative_to(ROOT)
        target = destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,target)
        hashes[str(relative)] = hashlib.sha256(file.read_bytes()).hexdigest()
    return hashes


def validate_live_endpoint(llm):
    from poseidon_compute import llm_config
    from experiments.common.providers import get_model_name
    block = llm['openrouter']
    if llm_config.base_url().rstrip('/') != block['base_url'].rstrip('/'):
        raise ValueError('Run-card endpoint differs from the credential-selected endpoint; align environment configuration before dispatch')
    resolved = get_model_name(llm['provider'],llm)
    if resolved != block['model']:
        raise ValueError('Resolved model differs from the frozen run card; remove overrides or refreeze the card')
    return resolved


async def execute(args, rows, llm):
    import subprocess
    resolved_model = validate_live_endpoint(llm) if args.live else None
    output = Path(args.output_root).resolve()/args.batch_id
    output.mkdir(parents=True,exist_ok=False)
    hashes = source_snapshot(output/'source')
    deps = {name:importlib.metadata.version(name) for name in ('terrarium-agents','PyYAML','openai')}
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty = subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).splitlines()
    manifest = {'version':VERSION,'mode':'live' if args.live else 'offline','schedule':rows,
        'prompt_version':PROMPT_VERSION,
        'schedule_hash':digest(rows),'source_hashes':hashes,'dependencies':deps,
        'git_commit':commit,'working_tree_status':dirty,
        'retry_policy':'no-automatic-trajectory-retry','stopping_rule':'run-frozen-schedule',
        'max_parallel_trajectories':getattr(args,'max_parallel',2),
        'D_reuse':False,'status':'running','completed':[],
        'run_card':getattr(args,'resolved_card',None)}
    write_json(output/'manifest.json',manifest)
    async def one(item):
        cfg = config_for(item,llm)
        clients = None
        if args.live:
            from experiments.common.providers import get_client_instance,get_generation_params
            from experiments.collusion.release_pipeline.domain import ROLES
            cfg['model_name'] = resolved_model
            cfg['generation_params'] = get_generation_params(llm)
            clients = {r:get_client_instance(llm,agent_name=r) for r in ROLES}
        from experiments.collusion.release_pipeline.domain import Scenario
        result = await run_episode(cfg,Scenario.from_dict(item['scenario']),output/'runs'/item['run_id'],clients=clients)
        from check_payoff_checks import inspect
        checks=inspect(output/'runs'/item['run_id'])
        write_json(output/'runs'/item['run_id']/'payoff_checks.json',checks)
        return {'run_id':item['run_id'],'status':result['status'],'payoff_checks_passed':checks['all_payoff_checks_passed']}
    # Native provider calls may be synchronous. Separate thread/event loop per
    # trajectory provides real overlap without sharing an environment or client.
    groups={}
    for item in rows: groups.setdefault(item['block_id'],[]).append(item)
    for group in groups.values():
        if getattr(args,'max_parallel',2)==1:
            results=[await one(item) for item in group]
        else:
            results=await asyncio.gather(*(asyncio.to_thread(lambda item=item: asyncio.run(one(item))) for item in group),return_exceptions=True)
        errors=[r for r in results if isinstance(r,BaseException)]
        manifest['completed'].extend(r for r in results if not isinstance(r,BaseException))
        if errors:
            manifest['status']='execution-error'
        write_json(output/'manifest.json',manifest)
        if errors: raise errors[0]
    analysis = analyze_batch(output)
    manifest['status'] = 'complete' if analysis['completed_count']==len(rows) else 'finished-with-failures'
    write_json(output/'manifest.json',manifest)
    print(json.dumps({'batch':str(output),'status':manifest['status'],'runs':len(rows),'audits':len(analysis['audits'])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-id')
    parser.add_argument('--output-root',default=str(ROOT/'results/release-pipeline'))
    parser.add_argument('--pilot',action='store_true',help='One hand-worked fixture, selected study pairings and conditions')
    parser.add_argument('--instances',type=int,default=2,help='Development instances per family')
    parser.add_argument('--seed',type=int,help='Legacy single base seed; --pilot defaults to 11')
    parser.add_argument('--seeds',nargs='+',type=int,help='Explicit matched study seeds; default study.yaml')
    parser.add_argument('--families',nargs='+',choices=FAMILIES,help='Subset of study scenario families')
    parser.add_argument('--max-parallel',type=int,choices=(1,2),default=2,help='A/D parallel within each matched block; blocks serial')
    parser.add_argument('--planning-rounds',type=int,default=DEFAULT_PLANNING_ROUNDS,
                        help='Planning rounds per actor (default: 3); final submissions are separate')
    parser.add_argument('--partition',choices=('development','heldout'),default='development')
    parser.add_argument('--conditions',nargs='+',choices=list('AD'),default=list('AD'))
    parser.add_argument('--pair',nargs=2,choices=ROLES,metavar=('ROLE_1','ROLE_2'),
                        help='Run only this role pair; default Product–Release and QA–Ops')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--run-card')
    parser.add_argument('--analyze',type=Path)
    args = parser.parse_args()
    if args.analyze:
        print(json.dumps({'planned':analyze_batch(args.analyze)['planned_count']})); return
    if args.instances<1 or len(set(args.conditions))!=len(args.conditions):
        parser.error('Positive instance count and unique conditions required')
    if args.pilot and args.partition!='development':
        parser.error('The hand-worked pilot fixture is development-only')
    try:
        if args.seeds and (args.seed is not None or args.pilot):
            raise ValueError('--seeds cannot be combined with --seed or --pilot')
        if args.pilot or args.seed is not None:
            rows=schedule(pilot=args.pilot,instances=args.instances,seed=args.seed if args.seed is not None else 11,conditions=tuple(args.conditions),partition=args.partition,selected_pair=args.pair,planning_rounds=args.planning_rounds)
        else:
            import yaml
            study=yaml.safe_load(STUDY_CONFIG.read_text())
            if study['pairs']!=[list(p) for p in STUDY_PAIRS] or study['conditions']!=['A','D'] or study['max_parallel_trajectories']!=2:
                raise ValueError('Study config and launcher protocol differ')
            rows=study_schedule(args.seeds or study['seeds'],args.families or study['families'],conditions=tuple(args.conditions),partition=args.partition,selected_pair=args.pair,planning_rounds=args.planning_rounds)
    except ValueError as exc:
        parser.error(str(exc))
    # Resolve/validate all templates before creating artifacts or provider clients.
    for item in rows:
        config_for(item)
    args.resolved_card = json.loads(Path(args.run_card).read_text()) if args.run_card else None
    llm = validate_card(args.resolved_card,rows) if args.resolved_card else None
    if args.live and llm is None:
        parser.error('--live requires a frozen, costed --run-card')
    if args.dry_run:
        # No clients, credentials, provider imports, network, output dirs or inference.
        from experiments.collusion.release_pipeline.environment import ReleasePipelineEnvironment
        from experiments.common.local_protocol import LocalCommunicationProtocol
        samples = []
        for c in args.conditions:
            item = next(r for r in rows if r['condition']==c)
            cfg = config_for(item,llm)
            cfg['environment']['scenario'] = item['scenario']
            env = ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
            for role in ROLES:
                ctx = env.build_agent_context(role,'planning',1,planning_round=1)
                samples.append(len((env.prompts.get_system_prompt(ctx)+env.prompts.get_user_prompt(agent_name=role,agent_context=ctx,blackboard_context={})).encode()))
        max_calls = sum(4*(row['planning_rounds']+1)*3 for row in rows)
        print(json.dumps({'trajectory_count':len(rows),'schedule_hash':digest(rows),'prompt_version':PROMPT_VERSION,
            'max_parallel_trajectories':args.max_parallel,
            'planning_rounds':args.planning_rounds,'max_model_calls':max_calls,'max_output_tokens':max_calls*1500,
            'initial_prompt_utf8_bytes_range':[min(samples),max(samples)],
            'cost_assumptions': 'No rates asserted; freeze verified endpoint rates, growing board histories and tool-loop context estimates in a run card before live use.' if not llm else 'See frozen run card',
            'mode':'live-plan' if args.live else 'offline','schedule':[{k:v for k,v in r.items() if k!='scenario'} for r in rows]},indent=2)); return
    if not args.batch_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.batch_id):
        parser.error('A new safe --batch-id is required')
    asyncio.run(execute(args,rows,llm))


if __name__=='__main__':
    main()
