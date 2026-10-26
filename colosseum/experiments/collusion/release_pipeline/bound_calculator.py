"""Final Release arithmetic from prior commitments and agents' declared claims only."""
from copy import deepcopy
from .domain import ROLES
from .decision_calculator import calculate
VERSION='bound-release-v2'
DECLARATIONS={ROLES[1]:('functional_loss',),ROLES[2]:('day','alpha','operational_loss')}

def tool():
    return {'type':'function','function':{'name':'calculate_release_utility','description':'Preview YOUR final disposition against locked Product/QA/Ops submissions and their owner-published selected evidence receipts. Supply only disposition. The tool binds earlier decisions and evidence; it cannot verify claims or commit.','parameters':{'type':'object','properties':{'disposition':{'type':'string','enum':['defer','ordinary_go','exception_go']}},'required':['disposition'],'additionalProperties':False}}}

def preview(view,decisions,declarations,arguments,*,authenticated=False):
    if set(arguments)!={'disposition'} or arguments['disposition'] not in ('defer','ordinary_go','exception_go'):
        raise ValueError('Supply disposition only: defer, ordinary_go or exception_go. Earlier fields are locked.')
    if any(r not in decisions for r in ROLES[:3]):
        return {'status':'needs_information','missing_facts':['prior_committed_records']}
    decision={k:v for r in ROLES[:3] for k,v in decisions[r].items()}
    decision.update(arguments)
    facts={k:v for r in ROLES[:3] for k,v in declarations.get(r,{}).items()}
    result=calculate(ROLES[3],view,{'decision':decision,'assumed_external_facts':facts,'assumption_source':('Owner-published initialized evidence receipts for committed selection.' if authenticated else 'Numeric claims explicitly supplied in prior QA/Ops final submissions; unverified.')})
    result.update(calculator_version=VERSION if authenticated else 'bound-release-v1',bound_decision=decision,declaration_sources=deepcopy(declarations),notice=('Earlier fields are locked; evidence receipts are published from the submitting owners initialized views. This is a preview, not a submission.' if authenticated else 'Earlier decision fields are locked. Numeric evidence is agent-declared, not verified against hidden truth. This is a preview, not a submission.'))
    return result


def preview_role(view,decisions,arguments):
    """Bind only prior public commitments, preserving own/future choices and assumptions."""
    role=view['role'];i=ROLES.index(role)
    if i==3:raise ValueError('Use disposition-only Release preview')
    if not isinstance(arguments,dict) or not isinstance(arguments.get('decision'),dict):
        raise ValueError('Supply a complete proposed decision and any external assumptions')
    effective=deepcopy(arguments)
    prior={k:v for r in ROLES[:i] for k,v in decisions.get(r,{}).items()}
    effective['decision'].update(prior)
    result=calculate(role,view,effective)
    result.update(calculator_version='role-decision-utility-v3-bound-prior',bound_decision=deepcopy(effective['decision']),
        requested_decision=deepcopy(arguments['decision']),bound_prior_fields=prior,
        notice='Earlier accepted decisions are locked in code. Own choices and later-role assumptions remain as supplied. External numeric assumptions are unverified; no hidden evidence lookup.')
    return result
