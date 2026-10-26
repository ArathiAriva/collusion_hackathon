import json
from pathlib import Path
import tempfile
import unittest
import run
from check_payoff_checks import inspect
from experiments.collusion.release_pipeline.scenarios import calibration_fixture
from experiments.collusion.release_pipeline.domain import Evaluator,ROLES
from experiments.collusion.release_pipeline.environment import ReleasePipelineEnvironment
from experiments.collusion.release_pipeline.bound_calculator import preview
from experiments.common.local_protocol import LocalCommunicationProtocol

class ReceiptSelectionTests(unittest.TestCase):
    def test_earlier_matching_preview_is_valid_after_exploration(self):
        sc=calibration_fixture();cfg={'environment':{},'release':{'condition':'D'}}
        env=ReleasePipelineEnvironment(LocalCommunicationProtocol(config=cfg),cfg)
        decisions={ROLES[0]:{'scope':'limited','exception_request':'no_request'},ROLES[1]:{'quality':'clear'},ROLES[2]:{'mode':'standard','readiness':'ready'}}
        claims={ROLES[1]:{'functional_loss':0},ROLES[2]:{'day':1,'alpha':1,'operational_loss':2}}
        events=[]
        for disposition in ('ordinary_go','defer'):
            args={'disposition':disposition}
            events.append({'agent_name':ROLES[3],'tool_name':'calculate_release_utility','phase':'execution','arguments':args,'result':preview(env.role_views[ROLES[3]],decisions,claims,args)})
        events.append({'agent_name':ROLES[3],'tool_name':'submit_release_decision','phase':'execution','arguments':{'disposition':'ordinary_go'},'result':{'accepted':True}})
        row=Evaluator(sc).evaluate(('limited','no_request','clear','standard','ready','ordinary_go'));row['status']='complete'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for name,data in [('scenario.json',sc.to_dict()),('tool_events.json',events),('release_outcome.json',row)]: (p/name).write_text(json.dumps(data))
            r=inspect(p)['roles'][3]
            self.assertTrue(r['check_passed']);self.assertEqual(r['calculator_event'],'tool-1')

if __name__=='__main__':unittest.main()
