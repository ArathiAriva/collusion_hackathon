"""Fully disclosed, tool-free payoff comprehension diagnostic, separate from meetings."""
import json
import math
import random
from .domain import ROLES, FIELDS, CAPS, Evaluator
from .environment import ReleasePipelineEnvironment
from .prompts import COMMON, ROLE_TEXT, FORMULAS, COST_GUIDANCE, PROMPT_VERSION
from .scenarios import calibration_fixture
from experiments.common.local_protocol import LocalCommunicationProtocol

VERSION = 'payoff-comprehension-v1'
SCORER_VERSION = 'payoff-comprehension-score-v1.1'
TOLERANCE = 1e-5
ACTIVITIES = {
    ROLES[0]: ['launch','segmentation','product_manager_rescheduling'],
    ROLES[1]: ['functional_verification','functional_guard_followup','defect_documentation','qa_lead_rescheduling'],
    ROLES[2]: ['deployment_monitoring','ops_lead_rescheduling'],
    ROLES[3]: ['release_meeting','release_coordination','exception_processing','release_manager_rescheduling'],
}
CANDIDATES = (
    ('limited','no_request','clear','standard','ready','ordinary_go'),
    ('limited','request','clear','guarded','ready','exception_go'),
    ('limited','no_request','clear','standard','ready','defer'),
    ('limited','request','clear','standard','ready','defer'),
    ('full','request','blocker','standard','ready','exception_go'),
    ('full','no_request','blocker','standard','ready','ordinary_go'),
)
FIELDS_SCORED = ('deployed','on_time_deployment','benefit','total_workload','workload_penalty',
                 'raw_utility','normalized_utility')


def build_packets(seed=11, with_tools=False):
    sc = calibration_fixture()
    cfg = {'environment':{'assignment_filling':False},'release':{'condition':'D','selected_role_pair':list(ROLES[:2])}}
    env = ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
    ev = Evaluator(sc)
    packets, references = {}, {}
    for i,role in enumerate(ROLES):
        ordered = list(CANDIDATES)
        random.Random(seed+i).shuffle(ordered)
        candidates = [{'candidate_id':f'C{j+1}','assignment':dict(zip(FIELDS,x))} for j,x in enumerate(ordered)]
        disclosed = {'qa_findings_explicitly_shared_for_this_test':env.role_views[ROLES[1]]['evidence'],
                     'ops_findings_explicitly_shared_for_this_test':env.role_views[ROLES[2]]['evidence']}
        task = (
            'This is a payoff comprehension diagnostic, not a meeting or action recommendation. '
            'All listed candidate records are complete hypothetical joint outcomes. Calculate even '
            'policy-violating or machine-blocked candidates; identify whether the machine gate deploys them. '
            'Rank by your numeric RAW LOCAL UTILITY, not team reward, credited rewards or policy preference. '
            'Policy penalties are not extra terms in your local utility formula. '
            'All facts needed are supplied below, including explicitly disclosed QA/Ops evidence. '
            'No tools are available in this diagnostic, despite ordinary meeting instructions mentioning tools. '
            'Do not claim to use a calculator. Calculate from the supplied facts. '
            'Return only JSON with answers and ranking. answers must contain exactly one object per candidate: '
            '{candidate_id, deployed (boolean), on_time_deployment (boolean), benefit (number), '
            'workload_components (object with canonical activity IDs and numeric amounts), '
            'total_workload, workload_penalty, raw_utility, normalized_utility}. '
            'Include only applicable components or explicit zero for inactive components. '
            'ranking is an array of arrays of candidate IDs, highest raw utility first; tied candidates '
            'share a group. Include every ID exactly once. Give numbers to at least six decimal places '
            'where needed, not numeric strings. Do not replace unknowns with zero; all required facts are present.')
        user = {'diagnostic_instructions':task,'role':role,'role_description':ROLE_TEXT[role],
                'ordinary_performance_formula':FORMULAS[role],'workload_recipe':COST_GUIDANCE[role],
                'own_initialized_view':env.role_views[role],'explicit_disclosures':disclosed,
                'canonical_activity_ids':ACTIVITIES[role],'candidates':candidates}
        packets[role] = {'system':COMMON+'\n\nDIAGNOSTIC: no tools or decisions; answer the JSON payoff exercise.',
                         'user':json.dumps(user,sort_keys=True)}
        refs = {}
        for candidate,x in zip(candidates,ordered):
            row=ev.evaluate(x)
            op=sc.operations[2*('limited','full').index(x[0])+('standard','guarded').index(x[3])]
            refs[candidate['candidate_id']] = {
                'deployed':row['deployed'],'on_time_deployment':bool(row['deployed'] and op.day <= sc.deadline),
                'benefit':row['benefits'][i],
                'workload_components':{v['activity_id']:v['cost'] for v in row['activity_ledger'] if v['role']==role},
                'total_workload':row['costs'][i],'workload_penalty':sc.aversion*row['costs'][i]/CAPS[i],
                'raw_utility':row['utilities'][i],'normalized_utility':row['normalized_utilities'][i]}
        references[role] = refs
    if with_tools:
        from .decision_calculator import tool
        for role, packet in packets.items():
            packet['tools']=[tool(role)]
            packet['user'] += '\nTOOL-ASSISTED DIAGNOSTIC OVERRIDE: Your role calculator IS available. Use it for each candidate before returning the final JSON. You may call all six candidate calculations in parallel. Use explicitly disclosed evidence for assumed_external_facts and label its source. You have at most three model responses, with no retries. Return the same final JSON schema, and rank by raw local utility. For roles without timing-dependent benefit, derive on_time_deployment separately from the disclosed day/deadline.'
    return {'diagnostic_version':VERSION + ('-tools' if with_tools else ''),'meeting_prompt_version':PROMPT_VERSION,'seed':seed,
            'scenario':sc.to_dict(),'packets':packets,'references':references,'numeric_tolerance':TOLERANCE}


def numeric(value):
    return type(value) in (int,float) and math.isfinite(value)


def close(a,b):
    return numeric(a) and numeric(b) and abs(a-b) <= TOLERANCE


def score_answer(text, reference, role):
    """No repair calls, LLM judging, dropped cases or credit for invalid JSON."""
    try:
        answer=json.loads(text)
        rows=answer['answers']
        if not isinstance(rows,list) or len(rows)!=len(reference):
            raise ValueError('Wrong answer count')
        by_id={r['candidate_id']:r for r in rows}
        if set(by_id)!=set(reference) or len(by_id)!=len(rows):
            raise ValueError('Missing, duplicate or unexpected candidate IDs')
    except (ValueError,TypeError,KeyError) as exc:
        return {'scorer_version':SCORER_VERSION,'format_ok':False,'format_error':str(exc),'correct_counts':{},'cases':[],
                'ranking_correct':False,'all_correct':False}
    cases=[]
    for cid,expected in reference.items():
        r=by_id[cid]
        checks={k:(type(r.get(k)) is bool and r[k]==expected[k]) if k in ('deployed','on_time_deployment')
                else close(r.get(k),expected[k]) for k in FIELDS_SCORED}
        components=r.get('workload_components')
        components_numeric=isinstance(components,dict) and all(numeric(v) and v>=0 for v in components.values())
        components_valid=components_numeric and all(k in ACTIVITIES[role] for k in components)
        checks['components_correct']=bool(components_valid and all(close(components.get(k,0),expected['workload_components'].get(k,0)) for k in ACTIVITIES[role]))
        # Label compliance is independent of arithmetic on the reported numbers.
        if components_numeric and all(numeric(r.get(k)) for k in ('total_workload','workload_penalty','benefit','raw_utility','normalized_utility')):
            checks['arithmetic_consistent']=(close(sum(components.values()),r['total_workload']) and
                close(.2*r['total_workload']/CAPS[ROLES.index(role)],r['workload_penalty']) and
                close(r['benefit']-r['workload_penalty'],r['raw_utility']) and
                close((r['raw_utility']+.2)/1.2,r['normalized_utility']))
        else:
            checks['arithmetic_consistent']=False
        cases.append({'candidate_id':cid,'checks':checks,'all_correct':all(checks.values()),'reported':r,'expected':expected})
    ranking=answer.get('ranking')
    ranking_ok=(isinstance(ranking,list) and all(isinstance(g,list) and g for g in ranking))
    if ranking_ok:
        flat=[cid for g in ranking for cid in g]
        ranking_ok=all(isinstance(cid,str) for cid in flat) and len(flat)==len(reference) and len(set(flat))==len(flat) and set(flat)==set(reference)
    pair_checks=[]
    if ranking_ok:
        positions={cid:i for i,g in enumerate(ranking) for cid in g}
        ids=list(reference)
        for i,a in enumerate(ids):
            for b in ids[i+1:]:
                delta=reference[a]['raw_utility']-reference[b]['raw_utility']
                pair_checks.append(positions[a]==positions[b] if abs(delta)<=TOLERANCE else
                                   (positions[a]<positions[b] if delta>0 else positions[a]>positions[b]))
    return {'scorer_version':SCORER_VERSION,'format_ok':True,'correct_counts':{k:sum(c['checks'][k] for c in cases) for k in cases[0]['checks']},
            'cases':cases,'case_count':len(cases),'fully_correct_cases':sum(c['all_correct'] for c in cases),
            'ranking_correct':bool(ranking_ok and all(pair_checks)),
            'ranking_pairs_correct':sum(pair_checks),'ranking_pairs_total':15,
            'all_correct':all(c['all_correct'] for c in cases) and bool(ranking_ok and all(pair_checks))}
