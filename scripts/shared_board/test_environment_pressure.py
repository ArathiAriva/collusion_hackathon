"""Opt-in notice semantics and real-runner verification without model/network calls."""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'colosseum'
sys.path.insert(0,str(PROJECT))
from experiments.collusion.prompts import CollusionPrompts, resolve_environment_pressure
from test_run_ae_once import BOOTSTRAP

CONFIGS=PROJECT/'experiments/collusion/configs/paper_shared_board'
NOTICE='A custom oversight notice.'


class BasePrompts:
    def get_system_prompt(self):return 'Unchanged team objective.'
    def _get_user_prompt_impl(self,*args):return 'Existing task and private board history.'


def prompt(cfg,role='normal',phase='planning',logger=None):
    wrapper=CollusionPrompts(SimpleNamespace(),cfg,prompt_variant='simple',base_prompts=BasePrompts(),
                            experiment_prompt_logger=logger,log_prompts=logger is not None)
    context={'collusion_role':role,'collusion_coalition_members':['Alice','Frank'],
             'collusion_blackboard_id':1,'phase':phase,'iteration':1,'planning_round':1}
    return wrapper,wrapper.get_user_prompt('Alice',context,{})


class EnvironmentPressureTests(unittest.TestCase):
    def test_missing_or_disabled_is_exactly_legacy(self):
        for role in ['normal','colluder']:
            _,legacy=prompt({},role)
            wrapper,disabled=prompt({'experiment':{'environment_pressure':{'enabled':False,'message':NOTICE}}},role)
            self.assertEqual(legacy,disabled)
            self.assertEqual(wrapper.get_system_prompt(),'Unchanged team objective.')
            self.assertNotIn('SPRINT GOVERNANCE NOTICE',disabled)

    def test_notice_on_both_phases_for_all_roles_and_logged(self):
        class Logger:
            def __init__(self):self.saved=[]
            def log_prompts(self,**kwargs):self.saved.append(kwargs)
        for phase in ['planning','execution']:
            for role in ['normal','colluder']:
                logger=Logger();cfg={'experiment':{'environment_pressure':{'enabled':True,'message':NOTICE}}}
                wrapper,text=prompt(cfg,role,phase,logger)
                self.assertEqual(text.count(NOTICE),1)
                self.assertTrue(text.endswith('=== SPRINT GOVERNANCE NOTICE ===\n'+NOTICE))
                self.assertEqual('SECRET COALITION INSTRUCTIONS' in text,role=='colluder')
                self.assertEqual(logger.saved[0]['user_prompt'],text)
                self.assertEqual(wrapper.get_system_prompt(),'Unchanged team objective.')

    def test_malformed_pressure_is_rejected(self):
        for block in [True,'notice',{'enabled':'true','message':NOTICE},{'enabled':True},
                      {'enabled':True,'message':'   '},{'enabled':True,'message':3}]:
            with self.assertRaises(ValueError):resolve_environment_pressure({'experiment':{'environment_pressure':block}})

    def test_F_only_changes_notice_and_output_metadata(self):
        for prefix in ['', 'seed1_pilot/']:
            a=yaml.safe_load((CONFIGS/prefix/'hackathon_2_1_a_pair_private_channel.yaml').read_text())
            f=yaml.safe_load((CONFIGS/'oversight_pressure'/prefix/'hackathon_2_1_f_pair_private_oversight.yaml').read_text())
            self.assertTrue(f['experiment'].pop('environment_pressure')['enabled'])
            for cfg in [a,f]:
                cfg['simulation'].pop('tags')
                for k in ['tag','output_dir']:cfg['experiment'].pop(k)
                cfg['experiment']['sweeps'][0].pop('name')
            self.assertEqual(a,f)

    def test_real_native_A_F_preserve_task_boards_and_log_notice(self):
        with tempfile.TemporaryDirectory(prefix='oversight-offline-') as name:
            td=Path(name);bootstrap=td/'offline_native.py';bootstrap.write_text(BOOTSTRAP)
            outputs={}
            for condition,path in [('A',CONFIGS/'seed1_pilot/hackathon_2_1_a_pair_private_channel.yaml'),
                                   ('F',CONFIGS/'oversight_pressure/seed1_pilot/hackathon_2_1_f_pair_private_oversight.yaml')]:
                cfg=yaml.safe_load(path.read_text());cfg['experiment']['output_dir']=str(td/condition)
                config=td/f'{condition}.yaml';config.write_text(yaml.safe_dump(cfg,sort_keys=False))
                result=subprocess.run([sys.executable,str(bootstrap),'--config',str(config),'-y'],cwd=PROJECT,
                    env={**os.environ,'MPLCONFIGDIR':str(td/'mpl')},capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,0,result.stderr[-4000:])
                run_config_path=next((td/condition).rglob('run_config.json'));run_dir=run_config_path.parent
                rc=json.loads(run_config_path.read_text());prompts=json.loads((run_dir/'agent_prompts.json').read_text())
                boards=json.loads((run_dir/'blackboards.json').read_text())
                self.assertEqual(len(prompts),30)
                self.assertEqual(sorted(len(b['participants']) for b in boards),[2,6])
                self.assertEqual(sum('SECRET COALITION INSTRUCTIONS' in p['user_prompt'] for p in prompts),10)
                self.assertEqual(sum('SPRINT GOVERNANCE NOTICE' in p['user_prompt'] for p in prompts),30 if condition=='F' else 0)
                self.assertEqual(rc['environment_pressure']['enabled'],condition=='F')
                self.assertEqual(rc['environment_pressure']['message'],cfg['experiment'].get('environment_pressure',{}).get('message',''))
                outputs[condition]=(rc,prompts)
            self.assertEqual(outputs['A'][0]['colluders'],outputs['F'][0]['colluders'])
            self.assertEqual(outputs['A'][0]['agent_turn_order'],outputs['F'][0]['agent_turn_order'])
            for a,f in zip(outputs['A'][1],outputs['F'][1]):
                self.assertEqual(a['system_prompt'],f['system_prompt'])
                # Tool-result event IDs are random UUIDs, independent of the task seed.
                # Normalize these identifiers, preserving all task/cost/message text.
                def normalize_ids(text):
                    return re.sub(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '<event-id>', text)
                self.assertEqual(normalize_ids(a['user_prompt']),normalize_ids(
                    f['user_prompt'].split('\n\n=== SPRINT GOVERNANCE NOTICE ===')[0]))


if __name__=='__main__':unittest.main()
