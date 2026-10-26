"""Offline rescoring, visibility audits, matched contrasts and scenario-cluster CIs."""
from pathlib import Path
import json
import random
from statistics import mean
from .annotations import blinded_packet
from .domain import Evaluator, PAIRS, ROLES, Scenario, digest, matched_metrics
from .prompts import PROMPT_VERSION, TURN_MARKER, phase_instructions


def load(path):
    return json.loads(Path(path).read_text())


def audit_run(path):
    path = Path(path)
    sc = Scenario.from_dict(load(path/'scenario.json'))
    ev = Evaluator(sc)
    config = load(path/'config.json')
    outcome = load(path/'release_outcome.json')
    boards = load(path/'blackboards.json')
    prompts = load(path/'agent_prompts.json')
    events = load(path/'tool_events.json')
    role_views = load(path/'role_views.json')
    protocol = load(path/'meeting_protocol.json')
    from .runner import speaking_schedule
    rounds = config['simulation'].get('max_planning_rounds',4)
    if protocol['schedule'] != speaking_schedule(config['release']['speaking_seed'],rounds):
        raise ValueError('Saved speaking schedule differs from configured planning rounds/seed')
    condition = config['release']['condition']
    pair = config['release']['selected_role_pair']
    if len(boards) != (2 if condition in ('A','C') else 1) or set(boards[0]['participants']) != set(ROLES):
        raise ValueError('Unexpected board contract')
    if len(boards)==2 and set(boards[1]['participants']) != set(pair):
        raise ValueError('Wrong private board membership')
    message_membership = {e['id']:set(b['participants']) for b in boards for e in b['events']}
    for p in prompts:
        if any(p['role'] not in message_membership[e] for e in p['visible_message_ids']):
            raise ValueError('Private message leaked into a prompt')
        expected = condition in ('A','B') and p['role'] in pair
        if ('Additional experimental objective with ' in p['user']) != expected:
            raise ValueError('Incorrect objective injection')
        if p['context']['evidence'] != role_views[p['role']]['evidence']:
            raise ValueError('Incorrect private evidence projection')
        history_text = p['user'].split('\nAccessible board histories:\n',1)[1]
        histories, end = json.JSONDecoder().raw_decode(history_text)
        suffix = history_text[end:]
        if p.get('prompt_version') in (PROMPT_VERSION, 'release-prompts-v2', 'release-prompts-v3', 'release-prompts-v4', 'release-prompts-v5', 'release-prompts-v6', 'release-prompts-v7'):
            instructions = phase_instructions(p['role'], p['phase'],prompt_version=p['prompt_version'])
            if (suffix != TURN_MARKER + instructions or not p['user'].startswith(instructions)
                    or not p['system'].endswith(TURN_MARKER + instructions)):
                raise ValueError('Current phase instructions missing or modified')
        elif p.get('prompt_version') is not None or suffix.strip():
            raise ValueError('Unknown prompt version or unexpected prompt suffix')
        allowed = {str(b['id']) for b in boards if p['role'] in b['participants']}
        if set(histories) != allowed:
            raise ValueError('Unexpected board histories in composed prompt')
        if 'timestamp' in p:
            expected_ids = {e['id'] for b in boards if p['role'] in b['participants']
                            for e in b['events'] if e['ts'] <= p['timestamp']}
            if set(p['visible_message_ids']) != expected_ids:
                raise ValueError('Message exposure timeline differs')
        if p['phase']=='planning' and p['context'].get('prior_committed_records'):
            raise ValueError('Final records appeared in planning')
    for event in events:
        from .decision_calculator import NAMES, calculate
        if event['tool_name'] in NAMES.values() and event['result'].get('status') in ('calculated','needs_information'):
            role=event['agent_name']
            if event['result'].get('calculator_version')=='role-decision-utility-v1':
                from .decision_calculator_v1 import calculate as legacy_calculate
                expected=legacy_calculate(role,role_views[role],event['arguments'])
            else:
                expected=calculate(role,role_views[role],event['arguments'])
            if event['tool_name'] != NAMES[role] or digest(expected) != digest(event['result']):
                raise ValueError('Role calculator result or ownership differs')
        if event['tool_name']=='calculate_utility' and event['result'].get('status')=='calculated':
            from .utility_calculator import calculate_utility
            if event['phase'] not in ('planning','execution') or event['agent_name'] not in ROLES:
                raise ValueError('Calculator used outside an active agent phase')
            if digest(calculate_utility(event['arguments'])) != digest(event['result']):
                raise ValueError('Calculator result differs from caller-supplied arithmetic')
        if event['tool_name']=='post_message' and 'error' not in event['result']:
            board_id = event['arguments'].get('blackboard_id')
            if event['phase'] != 'planning' or event['agent_name'] not in boards[board_id]['participants']:
                raise ValueError('Unauthorized post accepted')
        if event['tool_name'].startswith('submit_') and event['result'].get('accepted') and event['phase']!='execution':
            raise ValueError('Submission accepted during wrong phase')
    for role in ROLES:
        pp = [p for p in prompts if p['phase']=='planning' and p['role']==role]
        if outcome['status']=='complete' and (len(pp)!=rounds or [p.get('round') for p in pp] != list(range(1,rounds+1))):
            raise ValueError('Unequal meeting turns')
    if outcome['status']=='complete':
        recomputed = ev.evaluate(tuple(outcome['assignment']))
        for field in recomputed:
            if digest(recomputed[field]) != digest(outcome[field]):
                raise ValueError(f'Offline rescore differs: {field}')
        if digest(ev.pair_metrics(outcome['assignment'])) != digest(outcome['pair_metrics']):
            raise ValueError('Pair metrics differ')
    packet = blinded_packet(role_views,prompts,boards,events,outcome)
    return {'status':'passed','condition':condition,'scenario_hash':sc.content_hash,
            'matched_hash':protocol['matching_hash'],'prompt_count':len(prompts),
            'board_count':len(boards),'packet':packet}


def cluster_interval(rows, metric, *, draws=2000, seed=20261025):
    """Resample scenario clusters; all within-scenario dependent rows remain together."""
    groups = {}
    for row in rows:
        if row.get(metric) is not None:
            groups.setdefault(row['scenario_id'],[]).append(row[metric])
    if not groups:
        return None
    # Equal scenario weight even if a scenario has more complete pair observations.
    values = [mean(v) for v in groups.values()]
    rng = random.Random(seed)
    boot = sorted(mean(rng.choices(values,k=len(values))) for _ in range(draws))
    return {'mean':mean(values),'lower_95':boot[int(.025*draws)],'upper_95':boot[min(draws-1,int(.975*draws))],
            'scenario_count':len(values),'row_count':sum(map(len,groups.values())),
            'method':'equal-weight scenario-cluster percentile bootstrap','draws':draws,'seed':seed}


def analyze_batch(batch):
    from .runner import write_json
    batch = Path(batch)
    manifest = load(batch/'manifest.json')
    byblock = {}
    audits = []
    pair_rows = []
    for item in manifest['schedule']:
        run = batch/'runs'/item['run_id']
        if not (run/'release_outcome.json').exists():
            audits.append({'run_id':item['run_id'],'status':'missing'})
            continue
        audit = audit_run(run)
        packet = audit.pop('packet')
        write_json(run/'annotation_packet.json',packet)
        audits.append(dict(audit,run_id=item['run_id']))
        byblock.setdefault(item['block_id'],{})[item['condition']] = (item,run,audit)
        outcome = load(run/'release_outcome.json')
        if outcome['status']=='complete':
            sc = Scenario.from_dict(load(run/'scenario.json'))
            sensitivities = []
            for shares in ((.25,.25,.25,.25),(.4,.2,.2,.2),(.2,.3,.3,.2)):
                ev = Evaluator(sc,shares)
                for metric in ev.pair_metrics(outcome['assignment']):
                    row = {'run_id':item['run_id'],'scenario_id':item['scenario_id'],
                        'condition':item['condition'],'pair':'+'.join(metric['pair']),
                        'designated':list(metric['pair'])==item['pair'],
                        'credit_shares':str(shares),'CA_credit':metric['CA_credit'],
                        'CA_credit_normalized':metric['CA_credit_normalized'],
                        'F_nom':outcome['F_nom'],'F_econ':outcome['F_econ']}
                    sensitivities.append(row)
                    if shares==(.25,.25,.25,.25):
                        pair_rows.append(row)
            write_json(run/'credit_sensitivity.json',sensitivities)
    contrasts = []
    for block_id,block in byblock.items():
        hashes = {v[2]['matched_hash'] for v in block.values()}
        if len(hashes)!=1:
            raise ValueError(f'Matched inputs differ in {block_id}')
        for treatment,base in (('A','D'),('B','D'),('C','D'),('A','B'),('A','C')):
            if treatment not in block or base not in block:
                continue
            ti,tr,_ = block[treatment]
            bi,br,_ = block[base]
            t,b = load(tr/'release_outcome.json'),load(br/'release_outcome.json')
            if t['status']!='complete' or b['status']!='complete':
                contrasts.append({'block_id':block_id,'scenario_id':ti['scenario_id'],
                    'contrast':treatment+'-'+base,'status':'incomplete','pair':ti['pair']})
                continue
            ev = Evaluator(Scenario.from_dict(load(tr/'scenario.json')))
            values = matched_metrics(ev,t['assignment'],b['assignment'],ti['pair'],bi['run_id'])
            contrasts.append(dict(values,block_id=block_id,scenario_id=ti['scenario_id'],
                contrast=treatment+'-'+base,status='complete'))
    summaries = {c:{metric:cluster_interval([r for r in contrasts if r['contrast']==c],metric)
        for metric in ('IG','RIG','economic_loss','nominal_loss','delta_CA_credit_normalized')}
        for c in ('A-D','B-D','C-D','A-B','A-C')}
    # Secondary factorial interaction retains matched block dependence.
    interactions = []
    lookup = {(r['block_id'],r['contrast']):r for r in contrasts if r['status']=='complete'}
    for block in byblock:
        if (block,'A-B') in lookup and (block,'C-D') in lookup:
            a,c = lookup[(block,'A-B')],lookup[(block,'C-D')]
            interactions.append({'scenario_id':a['scenario_id'],'block_id':block,
                **{m:a[m]-c[m] for m in ('IG','economic_loss','delta_CA_credit_normalized')}})
    result = {'audits':audits,'contrasts':contrasts,'summaries':summaries,
              'interactions':interactions,'interaction_summary':{m:cluster_interval(interactions,m) for m in ('IG','economic_loss','delta_CA_credit_normalized')},
              'planned_count':len(manifest['schedule']),'completed_count':sum(load(batch/'runs'/i['run_id']/'release_outcome.json')['status']=='complete'
                 for i in manifest['schedule'] if (batch/'runs'/i['run_id']/'release_outcome.json').exists()),
              'interpretation':'Offline mocks verify interfaces and arithmetic; they are not observed LLM coordination or powered treatment findings.' if manifest['mode']=='offline' else 'Exploratory paired estimates; scenario-cluster dependence retained.'}
    write_json(batch/'analysis.json',result)
    import csv
    if pair_rows:
        with (batch/'all_pair_metrics.csv').open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(pair_rows[0]))
            writer.writeheader(); writer.writerows(pair_rows)
    return result
