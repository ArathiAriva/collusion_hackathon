import unittest
from copy import deepcopy
from .domain import ROLES,FIELDS,Evaluator
from .environment import ReleasePipelineEnvironment
from .scenarios import calibration_fixture, generate
from .domain import FAMILIES
from .decision_calculator import calculate,NAMES
from experiments.common.local_protocol import LocalCommunicationProtocol

class DecisionCalculatorTests(unittest.TestCase):
    def setUp(self):
        cfg={'environment':{},'release':{'condition':'D'}}
        self.env=ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
    def test_all_assignments(self):
        sc=self.env.scenario
        for x,row in self.env.evaluator.rows.items():
            op=sc.operations[2*('limited','full').index(x[0])+('standard','guarded').index(x[3])]
            facts={'day':op.day,'alpha':op.alpha,'operational_loss':op.operational_loss,'functional_loss':sc.functional_loss[('limited','full').index(x[0])]}
            for i,role in enumerate(ROLES):
                out=calculate(role,self.env.role_views[role],{'decision':dict(zip(FIELDS,x)),'assumed_external_facts':facts,'assumption_source':'fully disclosed oracle test'})
                self.assertEqual(out['deployed'],row['deployed'])
                for key,expected in [('benefit',row['benefits'][i]),('total_workload',row['costs'][i]),('raw_utility',row['utilities'][i]),('normalized_utility',row['normalized_utilities'][i])]:
                    self.assertAlmostEqual(out[key],expected,msg=str((role,x,key)))
    def test_generated_development_scenarios(self):
        for family in FAMILIES:
            sc=generate(family,37)
            cfg={'environment':{'scenario':sc.to_dict()},'release':{'condition':'D'}}
            self.env=ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
            self.test_all_assignments()

    def test_missing_private_facts_and_owner_priority(self):
        x=dict(zip(FIELDS,('full','request','blocker','standard','ready','exception_go')))
        self.assertEqual(calculate(ROLES[3],self.env.role_views[ROLES[3]],{'decision':x})['status'],'needs_information')
        out=calculate(ROLES[1],self.env.role_views[ROLES[1]],{'decision':x,'assumed_external_facts':{'alpha':1,'functional_loss':0},'assumption_source':'hypothetical'})
        self.assertAlmostEqual(out['benefit'],.1)
        self.assertNotIn('operations',out['evidence_used'])
        self.assertEqual(calculate(ROLES[2],self.env.role_views[ROLES[2]],{'decision':x})['status'],'calculated')
    def test_auth_and_read_only(self):
        env=self.env; env.activate('planning',ROLES[0])
        args={'decision':dict(zip(FIELDS,('limited','no_request','clear','standard','ready','defer')))}
        self.assertIn('error',env.local_tool_provider.handle_tool_call(NAMES[ROLES[1]],ROLES[0],args,phase='planning'))
        before=deepcopy(env.decisions)
        out=env.local_tool_provider.handle_tool_call(NAMES[ROLES[0]],ROLES[0],args,phase='planning')
        self.assertEqual(out['benefit'],0);self.assertEqual(before,env.decisions)
        self.assertNotIn('accepted',out)
        with self.assertRaises(ValueError): calculate(ROLES[0],env.role_views[ROLES[0]],dict(args,assumed_external_facts={'day':float('nan')}))

if __name__=='__main__': unittest.main()
