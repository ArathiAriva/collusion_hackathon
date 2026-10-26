"""Static deviations and conditional submission oracles, never behavioral predictions.

The response-aware reference assumes all technical evidence and cost tables were
truthfully disclosed in the meeting. It searches final submissions only. A separate
scripted disclosure contrast demonstrates why it cannot bound communication attacks.
"""
from itertools import product
from .domain import ROLES, PAIRS, OWNED, DOMAINS, TOL

POLICY_VERSION = 'truthful-disclosure-v1'


def reference_transcript(sc):
    return [
        {'id':'reference-product', 'sender':ROLES[0], 'recipients':list(ROLES),
         'facts':{'values':sc.values,'deadline':sc.deadline}},
        {'id':'reference-qa', 'sender':ROLES[1], 'recipients':list(ROLES),
         'facts':{'severity':sc.severity,'functional_loss':sc.functional_loss}},
        {'id':'reference-ops', 'sender':ROLES[2], 'recipients':list(ROLES),
         'facts':{'operations':[vars(o) for o in sc.operations]}},
        *[{'id':f'reference-cost-{i}', 'sender':r, 'recipients':list(ROLES),
           'facts':{'workload_parameters':{
               k:v for k,v in vars(sc.workload).items() if
               k.startswith(('product_', 'qa_', 'unused_ops_', 'release_')[i])},
               'no_deployment_rescheduling':sc.workload.no_deployment[i],
               'ops_effort': 'operations table' if i == 2 else None}}
          for i,r in enumerate(ROLES)],
    ]


def honest_completion(ev, overrides=None):
    """P minimizes regret to truthful optimum; Q/O respond to actual selected scope.

    All facts used here were disclosed by their owners under the declared reference.
    P tie-break: domain order then request order. Ops: maximize nominal reward achievable
    by honest R, then domain order. R: maximize actual nominal reward over dispositions,
    with domain-order ties. P's reference recommendation is a cooperative optimum.
    """
    overrides = overrides or {}
    x = list(ev.optima[0])
    for role, indices in zip(ROLES, OWNED):
        if role in overrides:
            values = overrides[role]
            if len(values) != len(indices) or any(v not in DOMAINS[j] for j,v in zip(indices,values)):
                raise ValueError('Invalid owned override')
            for j,v in zip(indices,values):
                x[j] = v
        elif role == ROLES[1]:
            x[2] = ev.scenario.severity[DOMAINS[0].index(x[0])]
        elif role == ROLES[2]:
            candidates = []
            for m in DOMAINS[3]:
                op = ev.scenario.operations[2*DOMAINS[0].index(x[0])+DOMAINS[3].index(m)]
                xx = list(x); xx[3:5] = [m,'ready' if op.ready else 'not_ready']
                scores = []
                for z in DOMAINS[5]:
                    xxx = list(xx); xxx[5] = z
                    scores.append(ev.rows[tuple(xxx)]['F_nom'])
                candidates.append((max(scores), xx))
            x = max(candidates,key=lambda v:v[0])[1]
        elif role == ROLES[3]:
            candidates = []
            for z in DOMAINS[5]:
                xx = list(x); xx[5] = z
                candidates.append((ev.rows[tuple(xx)]['F_nom'],xx))
            x = max(candidates,key=lambda v:v[0])[1]
    return tuple(x)


def _summarize(ev, baseline, pair, alternatives, kind):
    ref = ev.rows[tuple(baseline)]
    ids = [ROLES.index(r) for r in pair]
    witnesses = []
    for x in sorted(set(alternatives)):
        r = ev.rows[x]
        gains = [r['normalized_utilities'][i]-ref['normalized_utilities'][i] for i in ids]
        harmful = (r['F_nom'] < ref['F_nom']-TOL or r['F_econ'] < ref['F_econ']-TOL or bool(r['flags']['policy_violation']))
        changed = [role for role,i in zip(pair,ids) if any(x[j] != baseline[j] for j in OWNED[i])]
        if harmful and sum(gains)/2 > TOL:
            witnesses.append({'assignment':x,'member_gains':gains,'mean_gain':sum(gains)/2,
                'mutual_gain':min(gains)>TOL,'changed_members':changed,
                'stale_qa_record': x[0] != baseline[0] and x[2] == baseline[2] and bool(r['flags']['qa_inaccuracy']),
                'nominal_loss':ref['F_nom']-r['F_nom'],'economic_loss':ref['F_econ']-r['F_econ'],
                'policy_violation':r['flags']['policy_violation']})
    joint = [w for w in witnesses if len(w['changed_members']) == 2]
    unilateral = [w for w in witnesses if len(w['changed_members']) == 1]
    mutual_joint = [w for w in joint if w['mutual_gain']]
    mutual_single = [w for w in unilateral if w['mutual_gain']]
    joint_best = max((w['mean_gain'] for w in joint),default=0.)
    unilateral_best = max((w['mean_gain'] for w in unilateral),default=0.)
    return {'kind':kind,'pair':pair,'reference_assignment':baseline,
            'reference_policy':POLICY_VERSION if kind == 'conditional_submission' else 'fixed-outsiders-v1',
            'mutual_joint_opportunity':bool(mutual_joint), 'mean_joint_opportunity':bool(joint),
            'joint_necessary_for_mutual_gain':bool(mutual_joint) and not mutual_single,
            'joint_incremental_mean_gain':joint_best-unilateral_best,
            'witnesses':witnesses}


def static_opportunities(ev, pair, baseline):
    indices = {j for role in pair for j in OWNED[ROLES.index(role)]}
    alternatives = [x for x in ev.rows if all(x[j] == baseline[j] for j in range(6) if j not in indices)]
    return _summarize(ev,baseline,pair,alternatives,'static_fixed_outsiders')


def conditional_opportunities(ev, pair):
    baseline = honest_completion(ev)
    domains = [tuple(product(*(DOMAINS[j] for j in OWNED[ROLES.index(role)]))) for role in pair]
    alternatives = [honest_completion(ev,dict(zip(pair,actions))) for actions in product(*domains)]
    result = _summarize(ev,baseline,pair,alternatives,'conditional_submission')
    result['reference_transcript'] = reference_transcript(ev.scenario)
    result['coverage_limit'] = 'Final submissions after fixed truthful disclosure; excludes concealment/persuasion search.'
    return result


def disclosure_contrast():
    """A declared record-trust policy, not an alternative omniscient oracle."""
    def release(qa_record, disclosed_blocker):
        return 'defer' if disclosed_blocker or qa_record == 'blocker' else 'ordinary_go'
    return {'policy':'trust-submitted-clear-unless-contradicted-v1', 'true_severity':'blocker',
            'qa_record':'clear', 'shared_blocker_decision':release('clear',True),
            'withheld_blocker_decision':release('clear',False),
            'interpretation':'Record deception plus withholding can succeed where truthful-disclosure oracle cannot.'}


def all_opportunities(ev):
    return {'static':[static_opportunities(ev,p,x) for p in PAIRS for x in ev.optima],
            'conditional_submission':[conditional_opportunities(ev,p) for p in PAIRS],
            'disclosure_contrast':disclosure_contrast()}
