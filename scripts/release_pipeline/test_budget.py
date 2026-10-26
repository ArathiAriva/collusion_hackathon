import unittest
from types import SimpleNamespace
import run
from experiments.collusion.release_pipeline.budget_client import BudgetClient

class BudgetTests(unittest.TestCase):
    def test_notices_count_reset_and_do_not_change_tools(self):
        requests=[]
        class Client:
            def init_context(self,system,user):return [{'role':'system','content':system},{'role':'user','content':user}]
            def generate_response(self,*,input,params):
                requests.append((input[-1]['content'],params));return SimpleNamespace(),'response'
        c=BudgetClient(Client(),6);ctx=c.init_context('system','user');params={'tools':['unchanged']}
        for i in range(6):c.generate_response(input=ctx,params=params)
        self.assertIn('response 1 of 6; 5 further',requests[0][0])
        self.assertIn('response 6 of 6; 0 further',requests[-1][0])
        self.assertTrue(all(p is params for _,p in requests))
        with self.assertRaises(RuntimeError):c.generate_response(input=ctx,params=params)
        c.init_context('system','newturn');self.assertEqual(c.used,0)

if __name__=='__main__':unittest.main()
