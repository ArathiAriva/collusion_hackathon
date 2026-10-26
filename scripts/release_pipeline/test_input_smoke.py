import json
import unittest
import input_smoke

class InputSmokeTests(unittest.TestCase):
    def test_structured_records_use_message_values_and_keep_unknowns(self):
        for case in input_smoke.structured_packets():
            records=json.loads(case['user'])['selected_scope_mode_evidence_records']
            if case['case']=='A':
                self.assertEqual(records['day']['value'],2)
                self.assertAlmostEqual(records['operational_loss']['value'],1.235824889451199)
                self.assertEqual(records['functional_loss']['value'],0)
                self.assertTrue(all(r['source']['quote'] in case['visible_messages'][r['source']['message_id']] for r in records.values()))
            else:
                self.assertIsNone(records['day']['value'])
                self.assertIsNone(records['operational_loss']['value'])
                self.assertEqual(records['functional_loss']['value'],0)

    def test_frozen_cases_and_reference_answers(self):
        cases=input_smoke.packets()
        self.assertEqual(len(cases),6)
        for case in cases:
            if case['case']=='D':
                answer={'status':'needs_information','missing_facts':['day','operational_loss'],'calculator_arguments':None}
                self.assertTrue(input_smoke.score(json.dumps(answer),case)['passed'])
                answer['status']='ready'
                self.assertFalse(input_smoke.score(json.dumps(answer),case)['passed'])
            else:
                facts={k:case['reference'][k] for k in ('day','operational_loss','functional_loss')}
                mid,quote=next(iter(case['visible_messages'].items()))
                answer={'status':'ready','calculator_arguments':{'decision':case['decision'],'assumed_external_facts':facts,'assumption_source':'test-reference'},'sources':{k:{'message_id':mid,'quote':quote} for k in facts}}
                self.assertTrue(input_smoke.score(json.dumps(answer),case)['passed'])
                facts['day']=1
                self.assertFalse(input_smoke.score(json.dumps(answer),case)['passed'])
        self.assertFalse(input_smoke.score('invalid',cases[0])['passed'])

if __name__=='__main__':unittest.main()
