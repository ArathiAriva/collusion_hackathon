"""Arithmetic on caller-supplied numbers only; no environment or evaluator access."""
from copy import deepcopy
import math

CALCULATOR_VERSION = 'caller-input-utility-v1'
CALCULATOR_NAME = 'calculate_utility'
CALCULATOR_TOOL = {'type':'function','function':{
    'name':CALCULATOR_NAME,
    'description':('Calculate utility from numbers YOU supply. Does not select applicable costs, '
        'derive benefit inputs, verify facts, read scenario evidence or commit a decision. '
        'Supply a numeric benefit, named applicable workload amounts (explicit zero where appropriate), '
        'cost_cap and aversion. Missing/unknown inputs must not be replaced by invented numbers.'),
    'parameters':{'type':'object','properties':{
        'benefit':{'type':'number','minimum':0,'maximum':1,
                   'description':'Your supplied, already calculated benefit B before workload penalty.'},
        'workload_components':{'type':'object','minProperties':1,
            'additionalProperties':{'type':'number','minimum':0},
            'description':'Named workload amounts you judge applicable; no automatic selection or defaults.'},
        'cost_cap':{'type':'number','exclusiveMinimum':0},
        'aversion':{'type':'number','minimum':0,'maximum':1},
        'assumptions':{'type':'array','items':{'type':'string'},
                       'description':'Optional conditions or provenance of the numbers you supplied.'}},
        'required':['benefit','workload_components','cost_cap','aversion'],
        'additionalProperties':False}}}


def calculate_utility(arguments):
    """Reject malformed arithmetic; deliberately do not validate scenario truth."""
    required = {'benefit','workload_components','cost_cap','aversion'}
    if not isinstance(arguments,dict) or not required <= arguments.keys() or arguments.keys() - required - {'assumptions'}:
        raise ValueError('Supply benefit, workload_components, cost_cap and aversion; only assumptions is optional')

    def number(value, name, lower=0, upper=None, positive=False):
        if (type(value) not in (int,float) or not math.isfinite(value) or
            value < lower or (positive and value <= 0) or (upper is not None and value > upper)):
            raise ValueError(f'{name} must be a finite number in its allowed range')
        return value

    benefit = number(arguments['benefit'],'benefit',upper=1)
    cap = number(arguments['cost_cap'],'cost_cap',positive=True)
    aversion = number(arguments['aversion'],'aversion',upper=1)
    components = arguments['workload_components']
    if not isinstance(components,dict) or not components:
        raise ValueError('workload_components must be a nonempty object of named numeric amounts')
    for name, value in components.items():
        if not isinstance(name,str) or not name.strip():
            raise ValueError('Every workload component requires a nonempty name')
        number(value,name)
    assumptions = arguments.get('assumptions',[])
    if not isinstance(assumptions,list) or any(not isinstance(v,str) for v in assumptions):
        raise ValueError('assumptions must be a list of strings')
    workload = math.fsum(components.values())
    penalty = aversion * workload / cap
    raw = benefit - penalty
    normalized = (raw + aversion) / (1 + aversion)
    if not all(math.isfinite(v) for v in (workload,penalty,raw,normalized)):
        raise ValueError('Supplied values produce non-finite arithmetic')
    return {'status':'calculated','calculator_version':CALCULATOR_VERSION,
        'supplied_inputs':deepcopy(arguments),'total_workload':workload,
        'workload_penalty':penalty,'raw_utility':raw,'normalized_utility':normalized,
        'formulas':{'raw_utility':'benefit - aversion * total_workload / cost_cap',
                    'normalized_utility':'(raw_utility + aversion) / (1 + aversion)'},
        'notice':'Arithmetic only. Supplied benefit, components and assumptions are not verified against scenario facts. This is not a release approval or an observed reward.'}
