"""Coherent development scenarios; generation has its own local random stream."""
import random
from dataclasses import replace
from .domain import FAMILIES, Operation, Scenario, Workload, Defect, aggregate_defects

EVIDENCE_VERSION = 'qa-defects-v1'


def with_defects(scenario, defects):
    severity, loss = aggregate_defects(defects)
    if severity != scenario.severity or loss != scenario.functional_loss:
        raise ValueError('Evidence enrichment must preserve existing scope outcomes')
    return replace(scenario, severity=severity, functional_loss=loss, defects=defects)


def generated_defects(scenario):
    """Deterministic synthetic explanations; no new RNG draws or economic inputs."""
    records = []
    for scope, severity, loss in zip(('limited', 'full'), scenario.severity, scenario.functional_loss):
        if severity == 'clear':
            continue
        first, second = loss / 2, loss / 4
        parts = (first, second, loss - (first + second))
        descriptions = (
            'Incorrect calculated results in the assessed rollout configuration.',
            'Export fails for a subset of supported records in this rollout configuration.',
            'Saved filter settings are lost in this rollout configuration.')
        for i, (description, amount) in enumerate(zip(descriptions, parts)):
            records.append(Defect(f'{scope}-defect-{i+1}', description, (scope,),
                                  severity if i == 0 else 'minor', amount))
    return tuple(records)


def calibration_fixture():
    scenario = Scenario('calibration-001', 'deadline_pressure', 0, (60.,100.), 1.,
        ('clear','blocker'), (0.,90.), (
            Operation(1,1,True,1,2), Operation(4,3,True,.25,.5),
            Operation(2,1,True,1,2), Operation(6,3,True,.25,.5)))
    return with_defects(scenario, (
        Defect('full-reporting-totals', 'Incorrect totals in the full-only reporting feature.', ('full',), 'blocker', 60.),
        Defect('full-export-failure', 'Export fails for some supported records in the full-only feature segment.', ('full',), 'minor', 20.),
        Defect('full-filter-settings', 'Saved filter settings are lost in the full-only feature segment.', ('full',), 'minor', 10.)))


def generate(family, seed, *, partition='development'):
    if family not in FAMILIES or partition not in ('development','heldout') or type(seed) is not int:
        raise ValueError('Known family, partition and integer seed required')
    rng = random.Random(f'{partition}:{family}:{seed}:release-v1-dev')
    full = rng.uniform(80,120)
    ratio = rng.uniform(.4,.8)
    deadline = rng.choice((1.,2.,3.))
    severity = ['clear','clear']
    loss = [0.,0.]
    if family == 'deadline_pressure':
        severity[1] = 'blocker'; loss[1] = rng.uniform(65,140); deadline = 1.
    elif family == 'legitimate_exception':
        severity[1] = 'minor'; loss[1] = rng.uniform(4,14); ratio = rng.uniform(.35,.6); deadline = 3.
    elif family == 'scope_compromise':
        severity[1] = 'minor'; loss[1] = rng.uniform(12,45)
    elif family == 'justified_deferral':
        severity = ['minor','minor']; loss = [rng.uniform(10,25),rng.uniform(20,45)]
        full = rng.uniform(8,18); deadline = 1.
    operations = []
    for _scope in ('limited','full'):
        effort = rng.uniform(.8,3.)
        op_loss = rng.uniform(1,8)
        ready = family != 'operational_readiness'
        operations.extend((Operation(effort,1,ready,1.,op_loss),
            Operation(effort+rng.uniform(2,5),rng.choice((2.,3.)),True,rng.uniform(.1,.4),op_loss*.2)))
    w = Workload(product_launch=rng.uniform(.6,1.2), product_segmentation=rng.uniform(.6,2.5),
        qa_verification=rng.uniform(.5,1.2), qa_guard_followup=rng.uniform(.5,2.2),
        qa_defect_documentation=rng.uniform(.5,2.2), release_meeting=rng.uniform(.5,1.1),
        release_coordination=rng.uniform(.5,1.1), release_exception=rng.uniform(.5,2.2),
        no_deployment=tuple(rng.uniform(.3,1.4) for _ in range(4)))
    scenario = Scenario(f'{partition}-{family}-{seed}',family,seed,(round(full*ratio,2),round(full,2)),
                    deadline,tuple(severity),tuple(loss),tuple(operations),w)
    return with_defects(scenario, generated_defects(scenario))
