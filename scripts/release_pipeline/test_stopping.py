import json
import tempfile
import unittest
from pathlib import Path
import run

class StoppingTests(unittest.TestCase):
    def test_repeat_across_trajectories_and_small_rounding(self):
        with tempfile.TemporaryDirectory() as td:
            completed=[]
            for i in range(2):
                name=f'run{i}';p=Path(td)/'runs'/name;p.mkdir(parents=True)
                role={'submitted':True,'successful_final_checks':1,'own_fields_match':True,'prior_fields_match':True,'candidate_utility':.6,'oracle_candidate_utility':.5}
                (p/'payoff_checks.json').write_text(json.dumps({'roles':[role]}))
                completed.append({'run_id':name,'status':'complete'})
                result=run.repeating_issues(td,completed)
                self.assertEqual(bool(result),i==1)
            self.assertEqual(result,{'material_payoff_input_error':['run0','run1']})
            for name in ('run0','run1'):
                role['candidate_utility']=.50001
                (Path(td)/'runs'/name/'payoff_checks.json').write_text(json.dumps({'roles':[role]}))
            self.assertFalse(run.repeating_issues(td,completed))
            for record in completed:record['status']='incomplete'
            self.assertIn('missing_submission_or_run_failure',run.repeating_issues(td,completed))
