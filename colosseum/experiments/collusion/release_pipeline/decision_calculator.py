"""Role-local hypothetical payoffs. Takes an initialized own view, never a Scenario."""
from copy import deepcopy
import math
from .domain import ROLES, FIELDS, DOMAINS, deployment
from .utility_calculator import calculate_utility

VERSION = 'role-decision-utility-v2'
NAMES = dict(zip(ROLES, ('calculate_product_utility','calculate_qa_utility','calculate_ops_utility','calculate_release_utility')))

def tool(role):
    return {'type':'function','function':{'name':NAMES[role],
        'description':'For deployed QA supply alpha only if own functional loss is nonzero. Product needs day; Release needs day, functional_loss, operational_loss and alpha only if functional_loss is nonzero. External facts must describe the SELECTED scope AND mode, using accessible evidence with full precision. On needs_information add the named missing keys; changing quality labels is not a repair. Calculate YOUR local payoff for a complete hypothetical joint decision. Uses your own initialized evidence/costs only. Supply missing external facts explicitly as assumptions, obtained from others or hypothetical; they are not verified. Does not assess full policy compliance, recommend or commit. Missing facts produce needs_information. No-deployment QA/Ops benefit is 1; Product/Release benefit is 0.',
        'parameters':{'type':'object','properties':{
            'decision':{'type':'object','properties':{k:{'type':'string','enum':list(v)} for k,v in zip(FIELDS,DOMAINS)},'required':list(FIELDS),'additionalProperties':False},
            'assumed_external_facts':{'type':'object','properties':{k:{'type':'number','minimum':0} for k in ('day','alpha','operational_loss','functional_loss')},'additionalProperties':False},
            'assumption_source':{'type':'string','description':'Source or hypothetical status of external facts; not independently verified.'}},
            'required':['decision'],'additionalProperties':False}}}

def calculate(role, view, arguments):
    if role not in ROLES or view['role'] != role:
        raise ValueError('Role/view mismatch')
    if not isinstance(arguments,dict) or set(arguments)-{'decision','assumed_external_facts','assumption_source'}:
        raise ValueError('Unexpected calculator arguments')
    x=arguments.get('decision')
    if not isinstance(x,dict) or set(x)!=set(FIELDS) or any(x[k] not in v for k,v in zip(FIELDS,DOMAINS)):
        raise ValueError('A complete valid joint decision is required')
    external=arguments.get('assumed_external_facts',{})
    if not isinstance(external,dict) or set(external)-{'day','alpha','operational_loss','functional_loss'}:
        raise ValueError('Unexpected external facts')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in external.values()):
        raise ValueError('External facts must be finite nonnegative numbers')
    if external.get('alpha',0)>1:
        raise ValueError('alpha must be between zero and one')
    source=arguments.get('assumption_source','')
    if not isinstance(source,str) or (external and not source.strip()):
        raise ValueError('Describe the source or hypothetical status of external facts')
    scope,request,quality,mode,ready,disposition=(x[k] for k in FIELDS)
    d=bool(deployment(tuple(x[k] for k in FIELDS)))
    facts=dict(external)
    own=view['evidence']
    if role==ROLES[1]:
        facts['functional_loss']=own['functional_loss_by_scope'][scope]
    if role==ROLES[2]:
        facts.update(own['operations'][scope+':'+mode])
    required=({'day'} if role==ROLES[0] else {'functional_loss'} if role==ROLES[1] else {'operational_loss'} if role==ROLES[2] else {'day','functional_loss','operational_loss'}) if d else set()
    if d and role in (ROLES[1],ROLES[3]) and facts.get('functional_loss')!=0:
        required.add('alpha')
    missing=sorted(required-facts.keys())
    base={'calculator_version':VERSION,'supplied_inputs':deepcopy(arguments),'role':role,'deployed':d,
          'evidence_used':deepcopy(own),'assumed_external_facts':deepcopy(external),
          'notice':'Conditional local payoff, not a policy attestation, commitment or observed reward. External assumptions are unverified. Own initialized evidence takes precedence.'}
    if missing:
        return dict(base,status='needs_information',missing_facts=missing,repair_instruction='Add exactly the missing keys to assumed_external_facts, with assumption_source. Keep your proposed decision unchanged unless you actually intend to change it. Use facts for the selected scope AND mode from accessible messages; do not copy another row. No hidden evidence is retrieved.',selected_configuration={'scope':scope,'mode':mode},example_missing_fields={k:'required numeric value from accessible evidence or explicitly labeled hypothesis' for k in missing})
    ontime=bool(d and facts.get('day',float('inf'))<=view['public']['deadline']) if role in (ROLES[0],ROLES[3]) else None
    w=view['own_cost_schedule']; c={}
    if role==ROLES[3]:
        c['release_meeting']=w['meeting']
        if request=='request': c['exception_processing']=w['exception_request_processing']
    if not d:
        c[role+'_rescheduling']=w['no_deployment_rescheduling']
    elif role==ROLES[0]:
        c['launch']=w['launch']
        if scope=='limited': c['segmentation']=w['limited_segmentation']
    elif role==ROLES[1]:
        c['functional_verification']=w['functional_verification']
        if mode=='guarded': c['functional_guard_followup']=w['guard_followup']
        if own['severity_by_scope'][scope]!='clear': c['defect_documentation']=w['nonclear_documentation']
    elif role==ROLES[2]: c['deployment_monitoring']=facts['effort']
    else: c['release_coordination']=w['deployed_coordination']
    ratio=view['public']['values'][scope]/view['public']['values']['full']
    residual=0. if not d or facts.get('functional_loss')==0 else facts.get('alpha',0)*facts.get('functional_loss',0)
    if not d: b=1. if role in (ROLES[1],ROLES[2]) else 0.
    elif role==ROLES[0]: b=(10*ratio+6*ontime)/16
    elif role==ROLES[1]: b=1-min(1,residual/100)
    elif role==ROLES[2]: b=1-min(1,facts['operational_loss']/100)
    else: b=(8*ontime*ratio+2*(1-min(1,(residual+facts['operational_loss'])/100)))/10
    from .prompts import FORMULAS
    result=calculate_utility({'benefit':b,'workload_components':c,'cost_cap':view['cost_cap'],'aversion':view['aversion']})
    return dict(base,status='calculated',benefit=b,workload_components=c,on_time_deployment=ontime,
        resolved_inputs=facts,benefit_formula=FORMULAS[role],
        **{k:result[k] for k in ('total_workload','workload_penalty','raw_utility','normalized_utility')})
