#!/usr/bin/env python3
"""Offline-first, eight-call model comparison; no changes to meeting experiments."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'colosseum'))
from experiments.collusion.release_pipeline.comprehension import VERSION, SCORER_VERSION, build_packets, score_answer
from experiments.collusion.release_pipeline.domain import ROLES, digest
from experiments.collusion.release_pipeline.runner import write_json

MODELS={
    'openai/gpt-4o-mini':{'max_tokens':6000,'temperature':0},
    'openai/gpt-6-luna':{'max_completion_tokens':6000,'reasoning_effort':'none'},
}


def analyze_saved(batch):
    """New versioned analysis from preserved responses; no inference or overwrites."""
    batch=Path(batch)
    frozen=json.loads((batch/'frozen_packets_and_reference.json').read_text())
    original=json.loads((batch/'summary.json').read_text())
    reports=[]
    for saved in original['responses']:
        record=dict(saved)
        if saved['status']=='responded':
            raw=json.loads((batch/saved['model'].replace('/','--')/f"{saved['role']}.response.json").read_text())
            record['score']=score_answer(raw['choices'][0]['message']['content'] or '',frozen['references'][saved['role']],saved['role'])
        reports.append(record)
    models={}
    for model in MODELS:
        rows=[r for r in reports if r['model']==model]
        models[model]={
            'planned_candidates':24,'responses':sum(r['status']=='responded' for r in rows),
            'returned_models':sorted({r['returned_model'] for r in rows if 'returned_model' in r}),
            'correct_counts':{k:sum(r.get('score',{}).get('correct_counts',{}).get(k,0) for r in rows)
                for k in ('deployed','on_time_deployment','benefit','total_workload','workload_penalty',
                          'raw_utility','normalized_utility','components_correct','arithmetic_consistent')},
            'fully_correct_candidates':sum(r.get('score',{}).get('fully_correct_cases',0) for r in rows),
            'roles_with_correct_ranking':sum(r.get('score',{}).get('ranking_correct',False) for r in rows),
            'ranking_pairs_correct':sum(r.get('score',{}).get('ranking_pairs_correct',0) for r in rows),
            'provider_reported_cost_usd':sum(r.get('usage',{}).get('cost',0) for r in rows),
            'provider_cost_responses':sum('cost' in r.get('usage',{}) for r in rows),
            'uncached_estimate_usd':sum(r.get('uncached_estimate_usd',0) for r in rows)}
    import hashlib
    import experiments.collusion.release_pipeline.comprehension as scorer
    result={'scorer_version':SCORER_VERSION,'scorer_source_sha256':hashlib.sha256(Path(scorer.__file__).read_bytes()).hexdigest(),
        'models':models,'responses':reports,
        'change_note':'Arithmetic consistency uses supplied numeric amounts independently of canonical activity labels. Original scores retained; strict boolean/label compliance remains separate. No inference or semantic alias repair.'}
    destination=batch/f'analysis-{SCORER_VERSION}.json'
    with destination.open('x') as handle:
        json.dump(result,handle,indent=2,allow_nan=False);handle.write('\n')
    return destination,models


def validate_card(card, frozen):
    if (card.get('diagnostic_version')!=frozen['diagnostic_version'] or card.get('packet_hash')!=digest(frozen) or
        card.get('authorized_requests')!=(24 if frozen['diagnostic_version'].endswith('-tools') else 8) or card.get('models')!=MODELS or
        card.get('base_url')!='https://openrouter.ai/api/v1' or
        card.get('retry_policy')!='none' or not card.get('freeze_id')):
        raise ValueError('Card must freeze exact packets, both models/parameters, eight calls and no retries')
    for model in MODELS:
        rates=card.get('rates',{}).get(model,{})
        if not all(type(rates.get(k)) in (float,int) and rates[k]>=0 for k in ('input_per_million','output_per_million')) or not rates.get('verified_date') or not rates.get('source_url'):
            raise ValueError('Verified endpoint rates required for both models')
    if type(card.get('resource_estimate_usd')) not in (int,float) or card['resource_estimate_usd']<=0:
        raise ValueError('Positive resource estimate required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-tools',action='store_true',help='Bounded role-calculator comprehension test (at most 24 model requests)')
    parser.add_argument('--seed',type=int,default=11)
    parser.add_argument('--batch-id')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--run-card',type=Path)
    parser.add_argument('--analyze',type=Path,help='Offline versioned regrade of preserved raw responses')
    args=parser.parse_args()
    if args.analyze:
        path,models=analyze_saved(args.analyze)
        print(json.dumps({'analysis':str(path),'models':models},indent=2));return
    frozen=build_packets(args.seed,with_tools=args.with_tools)
    if not args.live:
        print(json.dumps({'diagnostic_version':frozen['diagnostic_version'],'packet_hash':digest(frozen),
            'models':MODELS,'requests':24 if args.with_tools else 8,'candidate_answers':48,'max_output_tokens':144000 if args.with_tools else 48000,
            'prompt_bytes_by_role':{r:len(json.dumps(p).encode()) for r,p in frozen['packets'].items()},
            'mode':'offline-preflight'},indent=2))
        return
    if not args.run_card or not args.batch_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.batch_id):
        parser.error('Live use requires a new batch-id and frozen run-card')
    card=json.loads(args.run_card.read_text());validate_card(card,frozen)
    from poseidon_compute import llm_config
    if llm_config.base_url().rstrip('/')!=card['base_url']:
        raise ValueError('Configured endpoint differs from frozen card')
    output=ROOT/'results/release-pipeline'/args.batch_id
    output.mkdir(parents=True,exist_ok=False)
    import run as meeting_launcher
    hashes=meeting_launcher.source_snapshot(output/'source')
    write_json(output/'frozen_packets_and_reference.json',frozen)
    shutil.copy2(args.run_card,output/'run_card.json')
    manifest={'diagnostic_version':frozen['diagnostic_version'],'created_utc':datetime.now(timezone.utc).isoformat(),
              'packet_hash':digest(frozen),'source_hashes':hashes,'status':'running',
              'planned_requests':24 if args.with_tools else 8,'completed':[],'model_seed':None,
              'note':'One response per role/model; six correlated candidates each. Full disclosure diagnostic, no tools or coalition objectives.'}
    write_json(output/'manifest.json',manifest)
    client=llm_config.make_client(max_retries=0,timeout=90)
    reports=[]
    for model,params in MODELS.items():
        model_dir=output/model.replace('/','--');model_dir.mkdir()
        for role,packet in frozen['packets'].items():
            request={'model':model,'messages':[{'role':'system','content':packet['system']},
                {'role':'user','content':packet['user']}],'response_format':{'type':'json_object'},**params}
            write_json(model_dir/f'{role}.request.json',request)
            record={'model':model,'role':role}
            try:
                if args.with_tools:
                    from experiments.collusion.release_pipeline.decision_calculator import calculate
                    request['tools']=packet['tools']
                    exchanges=[]
                    for step in range(3):
                        response=client.chat.completions.create(**request)
                        exchanges.append(response.model_dump(mode='json'))
                        write_json(model_dir/f'{role}.exchanges.json',exchanges)
                        message=response.choices[0].message
                        if not message.tool_calls: break
                        request['messages'].append(message.model_dump(exclude_none=True))
                        for call in message.tool_calls:
                            try:
                                if call.function.name!=packet['tools'][0]['function']['name']: raise ValueError('Wrong role tool')
                                result=calculate(role,json.loads(packet['user'].split('\nTOOL-ASSISTED')[0])['own_initialized_view'],json.loads(call.function.arguments))
                            except (ValueError,TypeError,KeyError) as exc:
                                result={'error':str(exc)}
                            request['messages'].append({'role':'tool','tool_call_id':call.id,'content':json.dumps(result)})
                        if step==1: request['tool_choice']='none'
                else:
                    response=client.chat.completions.create(**request)
                raw=response.model_dump(mode='json')
                write_json(model_dir/f'{role}.response.json',raw)
                text=response.choices[0].message.content or ''
                score=score_answer(text,frozen['references'][role],role)
                usage=raw.get('usage') or {}
                if args.with_tools:
                    usage={k:sum((v.get('usage') or {}).get(k,0) or 0 for v in exchanges) for k in ('prompt_tokens','completion_tokens','cost')}
                    record['model_requests']=len(exchanges)
                rates=card['rates'][model]
                estimate=(usage.get('prompt_tokens',0)*rates['input_per_million']+
                          usage.get('completion_tokens',0)*rates['output_per_million'])/1e6
                record.update(status='responded',finish_reason=response.choices[0].finish_reason,
                    returned_model=response.model,score=score,usage=usage,uncached_estimate_usd=estimate)
            except Exception as exc:
                # Do not expose SDK objects/headers or credential-bearing errors.
                record.update(status='request_error',error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None))
            write_json(model_dir/f'{role}.scored.json',record)
            reports.append(record)
            manifest['completed'].append({'model':model,'role':role,'status':record['status']})
            write_json(output/'manifest.json',manifest)
            print(json.dumps({'model':model,'role':role,'status':record['status'],
                              'fully_correct_cases':record.get('score',{}).get('fully_correct_cases')}),flush=True)
            if record.get('http_status') in (401,403):
                break
        if reports[-1].get('http_status') in (401,403):
            break
    summary={}
    for model in MODELS:
        rows=[r for r in reports if r['model']==model]
        summary[model]={'planned_responses':4,'responded':sum(r['status']=='responded' for r in rows),
            'valid_format':sum(r.get('score',{}).get('format_ok',False) for r in rows),
            'planned_candidates':24,
            'fully_correct_candidates':sum(r.get('score',{}).get('fully_correct_cases',0) for r in rows),
            'roles_with_correct_ranking':sum(r.get('score',{}).get('ranking_correct',False) for r in rows),
            'correct_counts':{k:sum(r.get('score',{}).get('correct_counts',{}).get(k,0) for r in rows)
                for k in ('deployed','on_time_deployment','benefit','components_correct','total_workload',
                          'workload_penalty','raw_utility','normalized_utility','arithmetic_consistent')},
            'uncached_estimate_usd':sum(r.get('uncached_estimate_usd',0) for r in rows)}
    write_json(output/'summary.json',{'models':summary,'responses':reports,
        'limitations':['One response per role/model on one fixed build; candidate answers are correlated.',
                       'Full required facts explicitly disclosed; not a test of meeting information access.',
                       'No tools, no coalition objective, no behavioral collusion or causal model-quality claim.',
                       'GPT-4o-mini temperature0; Luna reasoning_effort none and no temperature parameter.',
                       'Tolerance1e-5; malformed/missing cases are not dropped; no response repair/retry.']})
    manifest['status']='complete' if len(reports)==8 and all(r['status']=='responded' for r in reports) else 'finished-with-errors'
    write_json(output/'manifest.json',manifest)
    print(json.dumps({'batch':str(output),'models':summary}),flush=True)


if __name__=='__main__':
    main()
