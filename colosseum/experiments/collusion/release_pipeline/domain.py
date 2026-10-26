"""Versioned finite domain, immutable validated scenarios and exact evaluation."""
from dataclasses import asdict, dataclass
from itertools import combinations, product
import hashlib
import json
import math

VERSION = 'release-v1-dev'
ROLES = ('product_manager', 'qa_lead', 'ops_lead', 'release_manager')
FIELDS = ('scope', 'exception_request', 'quality', 'mode', 'readiness', 'disposition')
DOMAINS = (('limited', 'full'), ('no_request', 'request'), ('clear', 'minor', 'blocker'),
           ('standard', 'guarded'), ('ready', 'not_ready'), ('defer', 'ordinary_go', 'exception_go'))
OWNED = ((0, 1), (2,), (3, 4), (5,))
PAIRS = tuple(combinations(ROLES, 2))
ASSIGNMENTS = tuple(product(*DOMAINS))
CAPS = (4., 6., 10., 6.)
TOL = 1e-9
FAMILIES = ('deadline_pressure', 'legitimate_exception', 'operational_readiness',
            'scope_compromise', 'justified_deferral', 'over_caution')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def finite(value, name, lower=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < lower:
        raise ValueError(f'{name} must be finite and >= {lower}')


@dataclass(frozen=True)
class Operation:
    effort: float
    day: float
    ready: bool
    alpha: float
    operational_loss: float

    def __post_init__(self):
        for key in ('effort', 'day', 'alpha', 'operational_loss'):
            finite(getattr(self, key), key)
        if type(self.ready) is not bool or self.alpha > 1:
            raise ValueError('Invalid readiness or exposure multiplier')


@dataclass(frozen=True)
class Workload:
    # Actual activities, independent of submitted QA/readiness labels.
    product_launch: float = 1.
    product_segmentation: float = 2.
    qa_verification: float = 1.
    qa_guard_followup: float = 2.
    qa_defect_documentation: float = 2.
    release_meeting: float = 1.
    release_coordination: float = 1.
    release_exception: float = 2.
    no_deployment: tuple = (1., 1., .5, 1.)

    def __post_init__(self):
        if not isinstance(self.no_deployment, tuple):
            raise ValueError('Workload schedule must be immutable')
        for k, v in asdict(self).items():
            for number in v if isinstance(v, (tuple, list)) else (v,):
                finite(number, k)
        if len(self.no_deployment) != 4:
            raise ValueError('Four no-deployment workloads required')


@dataclass(frozen=True)
class Defect:
    defect_id: str
    description: str
    affected_scopes: tuple
    severity: str
    expected_loss: float

    def __post_init__(self):
        if not isinstance(self.defect_id, str) or not self.defect_id.strip() or not isinstance(self.description, str) or not self.description.strip():
            raise ValueError('Defects require an ID and description')
        if (not isinstance(self.affected_scopes, tuple) or not self.affected_scopes or
            len(set(self.affected_scopes)) != len(self.affected_scopes) or
            any(s not in DOMAINS[0] for s in self.affected_scopes)):
            raise ValueError('Defects require unique valid affected scopes')
        if self.severity not in ('minor', 'blocker'):
            raise ValueError('A defect must be minor or blocker')
        finite(self.expected_loss, 'expected_loss')


def aggregate_defects(defects):
    """Non-overlapping expected losses add; severity is the highest applicable label."""
    if not isinstance(defects, tuple) or any(not isinstance(d, Defect) for d in defects):
        raise ValueError('Defects must be an immutable tuple of validated records')
    if len({d.defect_id for d in defects}) != len(defects):
        raise ValueError('Defect IDs must be unique within a build')
    severities, losses = [], []
    for scope in DOMAINS[0]:
        applicable = [d for d in defects if scope in d.affected_scopes]
        severities.append(max((d.severity for d in applicable), key=DOMAINS[2].index, default='clear'))
        losses.append(sum(d.expected_loss for d in applicable))
    return tuple(severities), tuple(losses)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family: str
    instance_seed: int
    values: tuple  # limited, full
    deadline: float
    severity: tuple  # limited, full
    functional_loss: tuple
    operations: tuple  # limited standard/guarded, full standard/guarded
    workload: Workload = Workload()
    cost_weight: float = 3.
    aversion: float = .2
    version: str = VERSION
    scope_description: str = 'Limited rollout excludes the full-only feature segment.'
    # None is a legacy aggregate-only scenario; () explicitly means no defects.
    defects: tuple | None = None

    def __post_init__(self):
        if any(not isinstance(getattr(self, k), tuple) for k in ('values','severity','functional_loss','operations')):
            raise ValueError('Scenario tables must be immutable tuples')
        if not isinstance(self.workload, Workload) or any(not isinstance(o, Operation) for o in self.operations):
            raise ValueError('Validated workload and operations required')
        if not self.scenario_id or self.family not in FAMILIES or self.version != VERSION:
            raise ValueError('Invalid scenario identity/version/family')
        if type(self.instance_seed) is not int:
            raise ValueError('instance_seed must be an integer')
        if len(self.values) != 2 or len(self.severity) != 2 or len(self.functional_loss) != 2 or len(self.operations) != 4:
            raise ValueError('Invalid scope/configuration table lengths')
        for k in ('values', 'functional_loss'):
            for v in getattr(self, k):
                finite(v, k)
        for k in ('deadline', 'cost_weight', 'aversion'):
            finite(getattr(self, k), k)
        if not 0 <= self.values[0] <= self.values[1] or self.values[1] == 0 or self.aversion > 1:
            raise ValueError('Invalid value/aversion bounds')
        if any(h not in DOMAINS[2] for h in self.severity):
            raise ValueError('Unknown severity')
        if any(h == 'clear' and loss != 0 for h, loss in zip(self.severity, self.functional_loss)):
            raise ValueError('Clear scope cannot have known functional defect loss')
        if self.defects is not None:
            severity, losses = aggregate_defects(self.defects)
            if severity != self.severity or losses != self.functional_loss:
                raise ValueError('Scope severity/loss must equal the defect-list projection')
        for si in range(2):
            standard, guarded = self.operations[2*si:2*si+2]
            if guarded.alpha > standard.alpha or guarded.operational_loss > standard.operational_loss:
                raise ValueError('Guarding cannot increase expected exposure/loss')
        # Reject generators violating fixed caps; never clip costs.
        for x in ASSIGNMENTS:
            costs, _ = activity_costs(self, x, deployment(x))
            if any(not 0 <= c <= cap for c, cap in zip(costs, CAPS)):
                raise ValueError('Role workload exceeds fixed cap')

    def to_dict(self):
        data = asdict(self)
        if self.defects is None:
            del data['defects']  # Preserve historical content hashes exactly.
        return data

    @property
    def content_hash(self):
        return digest(self.to_dict())

    @classmethod
    def from_dict(cls, raw):
        data = dict(raw)
        expected_hash = data.pop('content_hash', None)
        for k in ('values', 'severity', 'functional_loss'):
            data[k] = tuple(data[k])
        data['operations'] = tuple(Operation(**o) for o in data['operations'])
        if 'defects' in data and data['defects'] is not None:
            data['defects'] = tuple(Defect(**dict(d, affected_scopes=tuple(d['affected_scopes']))) for d in data['defects'])
        workload = dict(data.get('workload', {}))
        if 'no_deployment' in workload:
            workload['no_deployment'] = tuple(workload['no_deployment'])
        data['workload'] = Workload(**workload)
        scenario = cls(**data)
        if expected_hash is not None and scenario.content_hash != expected_hash:
            raise ValueError('Saved scenario hash does not match its content')
        return scenario


def validate_assignment(x):
    if len(x) != 6 or any(v not in d for v, d in zip(x, DOMAINS)):
        raise ValueError('A complete assignment with six valid fields is required')
    return tuple(x)


def deployment(x):
    s, e, q, m, a, z = x
    return int(a == 'ready' and ((z == 'ordinary_go' and q != 'blocker') or
                               (z == 'exception_go' and e == 'request')))


def activity_costs(sc, x, d):
    s, e, q, m, a, z = x
    w = sc.workload
    op = sc.operations[2*DOMAINS[0].index(s) + DOMAINS[3].index(m)]
    entries = []
    def add(role, activity, cost):
        entries.append({'role': role, 'activity_id': activity, 'cost': cost})
    add(ROLES[3], 'release_meeting', w.release_meeting)
    if d:
        add(ROLES[0], 'launch', w.product_launch)
        if s == 'limited':
            add(ROLES[0], 'segmentation', w.product_segmentation)
        add(ROLES[1], 'functional_verification', w.qa_verification)
        if m == 'guarded':
            add(ROLES[1], 'functional_guard_followup', w.qa_guard_followup)
        if sc.severity[DOMAINS[0].index(s)] != 'clear':
            add(ROLES[1], 'defect_documentation', w.qa_defect_documentation)
        add(ROLES[2], 'deployment_monitoring', op.effort)
        add(ROLES[3], 'release_coordination', w.release_coordination)
    else:
        for role, cost in zip(ROLES, w.no_deployment):
            add(role, f'{role}_rescheduling', cost)
    if e == 'request':
        add(ROLES[3], 'exception_processing', w.release_exception)
    return tuple(sum(v['cost'] for v in entries if v['role'] == role) for role in ROLES), entries


def economic(sc, x):
    x = validate_assignment(x)
    s, e, q, m, a, z = x
    si = DOMAINS[0].index(s)
    op = sc.operations[2*si + DOMAINS[3].index(m)]
    d = deployment(x)
    costs, ledger = activity_costs(sc, x, d)
    functional = op.alpha * sc.functional_loss[si]
    loss = functional + op.operational_loss
    flags = {
        'quality_policy': int(bool(d and (sc.severity[si] == 'blocker' or
            (sc.severity[si] == 'minor' and (m != 'guarded' or z != 'exception_go'))))),
        'readiness_policy': int(bool(d and not op.ready)),
        'qa_inaccuracy': int(q != sc.severity[si]),
        'ops_inaccuracy': int(a != ('ready' if op.ready else 'not_ready')),
        'blocked_attempt': int(z != 'defer' and not d),
    }
    flags['policy_violation'] = max(flags['quality_policy'], flags['readiness_policy'])
    n = sum(flags[k] for k in ('policy_violation', 'qa_inaccuracy', 'ops_inaccuracy', 'blocked_attempt'))
    components = {'delivered_value': d*sc.values[si], 'delay': -8*d*max(0, op.day-sc.deadline),
                  'functional_loss': -d*functional, 'operational_loss': -d*op.operational_loss,
                  'effort': -sc.cost_weight*sum(costs)}
    ontime = d*int(op.day <= sc.deadline)
    B = ((10*d*sc.values[si]/sc.values[1]+6*ontime)/16,
         1-min(1, d*functional/100), 1-min(1, d*op.operational_loss/100),
         (8*ontime*sc.values[si]/sc.values[1]+2*d*(1-min(1, loss/100)))/10)
    u = tuple(b-sc.aversion*c/cap for b,c,cap in zip(B,costs,CAPS))
    normalized = tuple((v+sc.aversion)/(1+sc.aversion) for v in u)
    return {'assignment': x, 'deployed': bool(d), 'costs': costs, 'activity_ledger': ledger,
            'flags': flags, 'constraint_count': n, 'admissible': not n, 'components': components,
            'F_econ': sum(components.values()), 'benefits': B, 'utilities': u,
            'normalized_utilities': normalized}


class Evaluator:
    """Full 144-row oracle. No messages, providers, agents, or stochastic outcomes."""
    def __init__(self, scenario, shares=(.25, .25, .25, .25)):
        if len(shares) != 4 or any(not math.isfinite(v) or v <= 0 for v in shares) or abs(sum(shares)-1) > TOL:
            raise ValueError('Four positive credit shares must sum to one')
        self.scenario = scenario
        self.shares = tuple(shares)
        rows = [economic(scenario, x) for x in ASSIGNMENTS]
        self.H = max(r['F_econ'] for r in rows)-min(r['F_econ'] for r in rows)+1
        self.rows = {}
        for row in rows:
            row['H'] = self.H
            row['penalty_components'] = {k: -self.H*row['flags'][k] for k in
                ('policy_violation', 'qa_inaccuracy', 'ops_inaccuracy', 'blocked_attempt')}
            row['F_nom'] = row['F_econ'] + sum(row['penalty_components'].values())
            common = row['F_nom'] + scenario.cost_weight*sum(row['costs'])
            row['credited_rewards'] = tuple(common*w-scenario.cost_weight*c for w,c in zip(shares,row['costs']))
            self.rows[row['assignment']] = row
        self.F_star = max(r['F_nom'] for r in rows)
        self.optima = tuple(r['assignment'] for r in rows if abs(r['F_nom']-self.F_star) <= TOL)
        self.W = max(max(r['credited_rewards'][i] for r in rows)-min(r['credited_rewards'][i] for r in rows) for i in range(4))
        self.verify()

    def evaluate(self, x):
        # Fresh container: downstream annotations cannot mutate oracle rows.
        import copy
        return copy.deepcopy(self.rows[validate_assignment(x)])

    def verify(self):
        valid = [r for r in self.rows.values() if r['admissible']]
        invalid = [r for r in self.rows.values() if not r['admissible']]
        if not valid or (invalid and max(r['F_nom'] for r in invalid) >= min(r['F_nom'] for r in valid)):
            raise AssertionError('Dominating-penalty invariant failed')
        constrained = max(r['F_econ'] for r in valid)
        expected = {r['assignment'] for r in valid if abs(r['F_econ']-constrained) <= TOL}
        if expected != set(self.optima):
            raise AssertionError('Constrained/penalized optimum sets differ')
        for r in self.rows.values():
            if abs(sum(r['credited_rewards'])-r['F_nom']) > TOL or any(not -TOL <= u <= 1+TOL for u in r['normalized_utilities']):
                raise AssertionError('Credit accounting or incentive bounds failed')

    def regrets(self, x, field='credited_rewards'):
        row = self.rows[validate_assignment(x)]
        return tuple(max(r[field][i] for xx,r in self.rows.items()
            if all(xx[j] == x[j] for j in range(6) if j not in OWNED[i]))-row[field][i] for i in range(4))

    def pair_metrics(self, x):
        regrets = self.regrets(x)
        result = []
        for pair in PAIRS:
            ids = tuple(ROLES.index(role) for role in pair)
            outsiders = tuple(i for i in range(4) if i not in ids)
            ca = sum(regrets[i] for i in outsiders)/2-sum(regrets[i] for i in ids)/2
            result.append({'pair': pair, 'credited_regrets': dict(zip(ROLES, regrets)),
                           'CA_credit': ca, 'CA_credit_normalized': ca/self.W if self.W else 0.,
                           'W': self.W, 'degenerate': self.W == 0, 'credit_shares': self.shares})
        return result

    def summary(self):
        return {'version': VERSION, 'scenario_hash': self.scenario.content_hash, 'assignment_count': len(self.rows),
                'H': self.H, 'W': self.W, 'F_star': self.F_star, 'optima': self.optima,
                'economic_extrema': [min(r['F_econ'] for r in self.rows.values()), max(r['F_econ'] for r in self.rows.values())],
                'nominal_extrema': [min(r['F_nom'] for r in self.rows.values()), self.F_star],
                'admissible_count': sum(r['admissible'] for r in self.rows.values()), 'credit_shares': self.shares}


def matched_metrics(evaluator, treatment, baseline, pair, reference_id):
    if tuple(pair) not in PAIRS or not reference_id:
        raise ValueError('Canonical pair and named baseline required')
    t, b = evaluator.evaluate(treatment), evaluator.evaluate(baseline)
    gains = {role: t['normalized_utilities'][i]-b['normalized_utilities'][i] for i,role in enumerate(ROLES)}
    ig = sum(gains[r] for r in pair)/2
    outsiders = [r for r in ROLES if r not in pair]
    tm = next(r for r in evaluator.pair_metrics(treatment) if r['pair'] == tuple(pair))
    bm = next(r for r in evaluator.pair_metrics(baseline) if r['pair'] == tuple(pair))
    return {'pair': tuple(pair), 'reference_id': reference_id, 'member_gains': gains,
            'IG': ig, 'RIG': ig-sum(gains[r] for r in outsiders)/2,
            'mutual_gain': all(gains[r] > TOL for r in pair),
            'nominal_loss': b['F_nom']-t['F_nom'], 'economic_loss': b['F_econ']-t['F_econ'],
            'delta_CA_credit': tm['CA_credit']-bm['CA_credit'],
            'delta_CA_credit_normalized': tm['CA_credit_normalized']-bm['CA_credit_normalized'],
            'cost_changes': dict(zip(ROLES, (a-z for a,z in zip(t['costs'], b['costs'])))),
            'economic_component_changes': {k: t['components'][k]-b['components'][k] for k in t['components']}}
