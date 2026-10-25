"""Seed barrier, scientific-config preservation and native no-network integration."""
import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import yaml
import run_shared_seed_blocks as wrapper
from test_run_ae_once import BOOTSTRAP


class SeedBlockTests(unittest.TestCase):
    def fixtures(self, td):
        folder=td/'configs';folder.mkdir()
        originals={}
        for p in wrapper.CONFIGS.glob('*.yaml'):
            cfg=yaml.safe_load(p.read_text());cfg['experiment']['seeds']=[101,102]
            cfg['experiment']['output_dir']=str(td/'raw'/p.stem)
            dest=folder/p.name;dest.write_text(yaml.safe_dump(cfg,sort_keys=False));originals[dest]=dest.read_bytes()
        return wrapper.shared_plans(folder),originals

    def test_two_real_native_seed_blocks_never_overlap_or_change_originals(self):
        with tempfile.TemporaryDirectory(prefix='shared-seed-blocks-') as name:
            td=Path(name);plans,originals=self.fixtures(td)
            bootstrap=td/'offline_native.py';bootstrap.write_text(BOOTSTRAP)
            popen=subprocess.Popen;started=[];active=set();peak=[0]
            class Child:
                def __init__(self, process, key):self.process=process;self.key=key
                def wait(self):
                    result=self.process.wait();active.remove(self.key);return result
                def terminate(self):return self.process.terminate()
            def offline_popen(command,*args,**kwargs):
                if command[1:3]==['-m','experiments.collusion.run']:
                    cfg=yaml.safe_load(Path(command[command.index('--config')+1]).read_text())
                    seed=cfg['experiment']['seeds'][0]
                    if seed==102:
                        self.assertTrue((td/'batch/seed101/manifest.json').is_file())
                        parent=json.loads((td/'batch/manifest.json').read_text())
                        self.assertEqual(parent['seed_blocks'][0]['status'],'completed')
                        self.assertTrue(parent['seed_blocks'][0]['audited'])
                        self.assertTrue((td/'batch/analysis/results.json').is_file())
                        self.assertTrue(all(s==102 for s,_ in active))
                    key=(seed,cfg['experiment']['tag']);active.add(key);peak[0]=max(peak[0],len(active));started.append(seed)
                    command=[command[0],str(bootstrap)]+command[3:]
                    return Child(popen(command,*args,**kwargs),key)
                return popen(command,*args,**kwargs)
            with patch('run_ae_once.subprocess.Popen',offline_popen),patch.dict(os.environ,{'MPLCONFIGDIR':str(td/'mpl')}),redirect_stdout(io.StringIO()):
                manifest=wrapper.run_blocks(plans,td/'batch','offline-shared-blocks')
            self.assertEqual(manifest['status'],'completed')
            self.assertEqual(started,[101]*5+[102]*5)
            self.assertLessEqual(peak[0],5)
            self.assertFalse(active)
            result=json.loads((td/'batch/analysis/results.json').read_text());self.assertEqual(len(result['runs']),10)
            for p,data in originals.items():self.assertEqual(p.read_bytes(),data)
            for seed in (101,102):
                for p in (td/f'batch/seed-inputs/seed{seed}').glob('*.yaml'):
                    actual=yaml.safe_load(p.read_text());expected=copy.deepcopy(next(x['config'] for x in plans if x['path'].name==p.name))
                    expected['simulation']['seed']=seed;expected['experiment']['seeds']=[seed]
                    self.assertEqual(actual,expected)
            with self.assertRaises(FileExistsError):wrapper.run_blocks(plans,td/'batch','offline-shared-blocks')

    def test_failed_block_prevents_next_seed_and_retains_manifest(self):
        with tempfile.TemporaryDirectory() as name:
            td=Path(name);plans,_=self.fixtures(td);calls=[]
            def failed(plans,*args,**kwargs):calls.append(plans[0]['seeds']);raise RuntimeError('Simulated failure')
            with patch.object(wrapper,'launch',failed):
                with self.assertRaisesRegex(RuntimeError,'Simulated failure'):
                    wrapper.run_blocks(plans,td/'batch','offline-failure')
            self.assertEqual(calls,[[101]])
            manifest=json.loads((td/'batch/manifest.json').read_text())
            self.assertEqual(manifest['status'],'failed');self.assertEqual(manifest['seed_blocks'][1]['status'],'queued')
            self.assertTrue((td/'batch/configs').is_dir())

    def test_dry_run_has_no_writes_or_launch(self):
        output=io.StringIO()
        with patch.object(wrapper,'run_blocks',side_effect=AssertionError('Must not launch')),patch('sys.argv',['run_shared_seed_blocks.py','--dry-run']),redirect_stdout(output):
            wrapper.main()
        plan=json.loads(output.getvalue());self.assertFalse(plan['writes']);self.assertEqual(plan['model_calls'],0)
        self.assertEqual([x['seed'] for x in plan['waves']],[101,102,103,104,105])
        self.assertEqual(plan['max_parallel_trajectories'],5)

if __name__=='__main__':unittest.main()
