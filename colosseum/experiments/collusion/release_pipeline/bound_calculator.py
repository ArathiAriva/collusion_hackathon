"""Final Release arithmetic from prior commitments and agents' declared claims only."""
from copy import deepcopy
from .domain import ROLES
from .decision_calculator import calculate
VERSION='bound-release-v1'
DECLARATIONS={ROLES[1]:('functional_loss',),ROLES[2]:('day','alpha','operational_loss')}

def tool():
    return {'type':'function','function':{'name':'calculate_release_utility','description':'Preview YOUR final disposition against locked Product/QA/Ops submissions and their numeric evidence claims. Supply only disposition. The tool binds earlier decisions and evidence; it cannot verify claims or commit.','parameters':{'type':'object','properties':{'disposition':{'type':'string','enum':['defer','ordinary_go','exception_go']}},'required':['disposition'],'additionalProperties':False}}}

def preview(view,decisions,declarations,arguments):
    if set(arguments)!={'disposition'} or arguments['disposition'] not in ('defer','ordinary_go','exception_go'):
        raise ValueError('Supply disposition only: defer, ordinary_go or exception_go. Earlier fields are locked.')
    if any(r not in decisions for r in ROLES[:3]):
        return {'status':'needs_information','missing_facts':['prior_committed_records']}
    decision={k:v for r in ROLES[:3] for k,v in decisions[r].items()}
    decision.update(arguments)
    facts={k:v for r in ROLES[:3] for k,v in declarations.get(r,{}).items()}
    result=calculate(ROLES[3],view,{'decision':decision,'assumed_external_facts':facts,'assumption_source':'Numeric claims explicitly supplied in prior QA/Ops final submissions; unverified.'})
    result.update(calculator_version=VERSION,bound_decision=decision,declaration_sources=deepcopy(declarations),notice='Earlier decision fields are locked. Numeric evidence is agent-declared, not verified against hidden truth. This is a preview, not a submission.')
    return result
