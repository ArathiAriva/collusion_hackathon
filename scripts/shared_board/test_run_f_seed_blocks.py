"""Verify F seed barriers/config preservation/fail-stop without inference."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml
import run_f_seed_blocks as runner


class FSeedBlockTests(unittest.TestCase):
    def baseline(self, directory):
        batch=directory/'baseline'
        (batch/'analysis').mkdir(parents=True)
        (batch/'configs').mkdir()
        a=runner.PROJECT/'experiments/collusion/configs/paper_shared_board/hackathon_2_1_a_pair_private_channel.yaml'
        (batch/'configs'/a.name).write_bytes(a.read_bytes())
        path=batch/'analysis/results.json'
        path.write_text(json.dumps(dict(status='completed',runs=[dict(condition='A',seed=s) for s in range(101,106)])))
        return path

    def test_audit_barrier_and_seed_only_copies(self):
        cfg=yaml.safe_load(runner.CONFIG.read_text());events=[]
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)/'batch'
            baseline=self.baseline(Path(t))
            def launch(plans,child,batch_id,workers):
                self.assertEqual(workers,1);self.assertEqual(len(plans),1)
                seed=plans[0]['seeds'][0];events.append(('launch',seed))
                expected=copy.deepcopy(cfg);expected['simulation']['seed']=seed;expected['experiment']['seeds']=[seed]
                self.assertEqual(plans[0]['config'],expected)
                self.assertEqual(yaml.safe_load(plans[0]['path'].read_text()),expected)
                return {'conditions':[{'seed':seed}]}
            def audit(record,single,old):
                seed=record['seed'];events.append(('audit',seed));self.assertEqual(old['seed'],seed)
                return dict(seed=seed,reference_pair_regret_gap=0,joint_reward=0),[]
            with patch.object(runner,'launch',side_effect=launch),patch.object(runner,'audit_f',side_effect=audit),patch.object(runner,'export'):
                m=runner.run_blocks(runner.CONFIG,directory,'offline-F',baseline)
            self.assertEqual(m['status'],'completed')
            self.assertTrue(all(b['audited'] for b in m['seed_blocks']))
            self.assertEqual(events,[(action,seed) for seed in range(101,106) for action in ['launch','audit']])
        self.assertEqual(yaml.safe_load(runner.CONFIG.read_text()),cfg)

    def test_failed_audit_stops_before_next_seed(self):
        calls=[]
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)/'batch'
            baseline=self.baseline(Path(t))
            def launch(plans,*args,**kwargs):calls.append(plans[0]['seeds'][0]);return {'conditions':[{}]}
            with patch.object(runner,'launch',side_effect=launch),patch.object(runner,'audit_f',side_effect=ValueError('Audit rejected')),patch.object(runner,'export'):
                with self.assertRaisesRegex(ValueError,'Audit rejected'):
                    runner.run_blocks(runner.CONFIG,directory,'offline-failure',baseline)
            manifest=runner.read(directory/'manifest.json')
            self.assertEqual(calls,[101]);self.assertEqual(manifest['status'],'failed')
            self.assertEqual(manifest['seed_blocks'][1]['status'],'queued')


if __name__=='__main__':unittest.main()
