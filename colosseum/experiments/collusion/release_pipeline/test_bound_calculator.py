import unittest
from .bound_calculator import preview,tool
from .domain import ROLES
from .environment import ReleasePipelineEnvironment
from experiments.common.local_protocol import LocalCommunicationProtocol

class BoundTests(unittest.TestCase):
    def setUp(self):
        cfg={'environment':{},'release':{'condition':'A','selected_role_pair':[ROLES[0],ROLES[3]]}}
        self.env=ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
        self.decisions={ROLES[0]:{'scope':'limited','exception_request':'no_request'},ROLES[1]:{'quality':'clear'},ROLES[2]:{'mode':'guarded','readiness':'ready'}}
        self.claims={ROLES[1]:{'functional_loss':0},ROLES[2]:{'day':3,'alpha':.25,'operational_loss':.5}}
    def test_binding_and_claims_not_hidden_truth(self):
        p=preview(self.env.role_views[ROLES[3]],self.decisions,self.claims,{'disposition':'ordinary_go'})
        self.assertEqual(p['status'],'calculated');self.assertEqual(p['bound_decision']['mode'],'guarded')
        self.assertAlmostEqual(p['raw_utility'],.13233333333333333)
        self.claims[ROLES[2]]['day']=1
        q=preview(self.env.role_views[ROLES[3]],self.decisions,self.claims,{'disposition':'ordinary_go'})
        self.assertGreater(q['raw_utility'],p['raw_utility']) # Supplied claims, not oracle day3.
        with self.assertRaises(ValueError):preview(self.env.role_views[ROLES[3]],self.decisions,self.claims,{'disposition':'ordinary_go','scope':'full'})
        self.assertEqual(tool()['function']['parameters']['required'],['disposition'])
    def test_missing_claims_not_zero_and_submission_extraction(self):
        p=preview(self.env.role_views[ROLES[3]],self.decisions,{}, {'disposition':'ordinary_go'})
        self.assertEqual(p['status'],'needs_information');self.assertIn('day',p['missing_facts'])
        env=self.env
        records=[self.decisions[ROLES[0]],dict(self.decisions[ROLES[1]],**self.claims[ROLES[1]]),dict(self.decisions[ROLES[2]],**self.claims[ROLES[2]])]
        from .environment import TOOL_NAMES
        for role,args in zip(ROLES,records):
            env.activate('execution',role)
            r=env.local_tool_provider.handle_tool_call(TOOL_NAMES[ROLES.index(role)],role,args,phase='execution')
            self.assertTrue(r['accepted'])
        env.activate('execution',ROLES[3])
        r=env.local_tool_provider.handle_tool_call('calculate_release_utility',ROLES[3],{'disposition':'ordinary_go'},phase='execution')
        self.assertEqual(r['status'],'calculated');self.assertEqual(len(env.decisions),3)
        self.assertEqual(env.declared_evidence[ROLES[2]],self.claims[ROLES[2]])
        self.assertNotIn('day',env.decisions[ROLES[2]])

if __name__=='__main__':unittest.main()
