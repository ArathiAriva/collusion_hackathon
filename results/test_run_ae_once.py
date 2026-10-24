"""Offline tests: real native runner and artifacts, mocked provider, network forbidden."""
import importlib.util
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

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ae_wrapper', HERE / 'run_ae_once.py')
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)

BOOTSTRAP = '''
import os, sys, json, socket
from unittest.mock import patch
sys.path.insert(0, os.getcwd())
from experiments.collusion import run
from llm_server.clients.together_client import TogetherClient

def client(*args, **kwargs):
    return TogetherClient(api_key='offline-placeholder', base_url='http://unused.invalid')

def response(self, input, params):
    tools = {x['function']['name']:x['function'] for x in params['tools']}
    if 'assign_task' in tools:
        name='assign_task'; arguments={'task_id':'skip'}
    else:
        name='post_message'
        arguments={'blackboard_id':tools[name]['parameters']['properties']['blackboard_id']['enum'][0],
                   'message':'Offline wrapper integration test.'}
    msg={'role':'assistant','content':None,'tool_calls':[{
        'id':'offline_tool_call','type':'function',
        'function':{'name':name,'arguments':json.dumps(arguments)}}]}
    return {'choices':[{'message':msg}], 'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}}, ''

with patch.object(run,'get_client_instance',client), \\
     patch.object(run,'get_model_name',lambda provider,cfg:cfg['openrouter']['model']), \\
     patch.object(TogetherClient,'generate_response',response), \\
     patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')), \\
     patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
    run.main()
'''


class WrapperTests(unittest.TestCase):
    def fixtures(self, td):
        directory = td / 'configs'
        directory.mkdir()
        originals = {}
        for p in (wrapper.PROJECT / 'experiments/collusion/configs').glob('hackathon_2_1_*.yaml'):
            originals[p] = p.read_bytes()
            cfg = yaml.safe_load(p.read_text())
            cfg['experiment']['seeds'] = [101, 102, 103, 104, 105]
            cfg['experiment']['output_dir'] = str(td / 'raw' / p.stem)
            (directory / p.name).write_text(yaml.safe_dump(cfg, sort_keys=False))
        return directory, originals

    def test_real_native_five_seed_batch_with_mock_provider(self):
        with tempfile.TemporaryDirectory(prefix='ae-wrapper-integration-') as name:
            td = Path(name)
            directory, originals = self.fixtures(td)
            fixture_bytes = {p.resolve():p.read_bytes() for p in directory.iterdir()}
            pilot = wrapper.ROOT / 'results/ae-single-seed-run-manifest.json'
            pilot_bytes = pilot.read_bytes()
            runtime = {p:p.read_bytes() for p in [wrapper.PROJECT / 'experiments/collusion/run.py',
                                                 wrapper.PROJECT / 'experiments/collusion/prompts.py']}
            bootstrap = td / 'offline_native.py'
            bootstrap.write_text(BOOTSTRAP)
            plans = wrapper.load_plan(directory)
            self.assertTrue(all(p['seeds'] == [101,102,103,104,105] for p in plans))
            popen = subprocess.Popen
            intercepted = []

            def offline_popen(command, *args, **kwargs):
                if command[1:3] == ['-m','experiments.collusion.run']:
                    intercepted.append(command)
                    command = [command[0], str(bootstrap)] + command[3:]
                return popen(command, *args, **kwargs)

            with patch.object(wrapper.subprocess, 'Popen', offline_popen), \
                 patch.dict(os.environ, {'MPLCONFIGDIR':str(td/'matplotlib')}):
                manifest = wrapper.launch(plans, td/'batch', 'offline-five-seeds', workers=2)
            self.assertEqual(len(intercepted), 5)
            self.assertEqual(manifest['status'], 'completed')
            self.assertEqual(manifest['expected_trajectories'], 25)
            self.assertTrue(manifest['matched_instances_verified'])
            self.assertEqual(sum(len(r['trajectories']) for r in manifest['conditions']), 25)
            self.assertEqual(json.loads((td/'batch/manifest.json').read_text()), manifest)
            for record, plan in zip(manifest['conditions'], plans):
                self.assertEqual(Path(record['config_snapshot']).read_bytes(), fixture_bytes[plan['path']])
                self.assertEqual(record['status'], 'completed')
                self.assertEqual([x['seed'] for x in record['trajectories']], [101,102,103,104,105])
                self.assertEqual(record['command'][-3:], ['--max-concurrent-runs','1','-y'])
                self.assertEqual(Path(record['output']).parent, Path(record['output_base']))
                for item in record['trajectories']:
                    d = Path(item['run_dir'])
                    self.assertIn(f"seed{item['seed']}", d.name)
                    final = json.loads((d/'final_summary.json').read_text())
                    self.assertEqual(len(final['assignment']), 6)
                    self.assertEqual(final['random_fallback_fills'], 0)
            for p, data in {**originals, **fixture_bytes, **runtime, pilot:pilot_bytes}.items():
                self.assertEqual(p.read_bytes(), data, str(p))
            with self.assertRaises(FileExistsError):
                wrapper.launch(plans, td/'batch', 'offline-five-seeds')

    def test_dry_run_reports_all_seeds_without_launching_or_writing(self):
        with tempfile.TemporaryDirectory() as name:
            td = Path(name)
            directory, _ = self.fixtures(td)
            output = io.StringIO()
            argv = ['run_ae_once.py', '--config-dir', str(directory),
                    '--results-dir', str(td/'dry-results'), '--dry-run']
            with patch.object(wrapper.sys, 'argv', argv), \
                 patch.object(wrapper, 'launch', side_effect=AssertionError('Must not launch')), \
                 redirect_stdout(output):
                wrapper.main()
            plan = json.loads(output.getvalue())
            self.assertEqual(plan['expected_trajectories'], 25)
            self.assertFalse((td/'dry-results').exists())

    def test_reject_mismatched_and_duplicate_seeds_before_launch(self):
        with tempfile.TemporaryDirectory() as name:
            directory, _ = self.fixtures(Path(name))
            p = sorted(directory.iterdir())[0]
            cfg = yaml.safe_load(p.read_text())
            cfg['experiment']['seeds'] = [101]
            p.write_text(yaml.safe_dump(cfg))
            with self.assertRaisesRegex(ValueError, 'matched seeds'):
                wrapper.load_plan(directory)
            cfg['experiment']['seeds'] = [101,101]
            p.write_text(yaml.safe_dump(cfg))
            with self.assertRaisesRegex(ValueError, 'duplicate seeds'):
                wrapper.load_plan(directory)

    def test_failed_children_preserve_failure_manifest_and_do_not_retry(self):
        with tempfile.TemporaryDirectory() as name:
            td = Path(name)
            directory, _ = self.fixtures(td)
            plans = wrapper.load_plan(directory)
            calls = []

            class FailedChild:
                def __init__(self, command, **kwargs):
                    calls.append(command)
                    kwargs['stdout'].write('Simulated native failure; artifacts retained.\n')
                def wait(self):
                    return 7

            with patch.object(wrapper.subprocess, 'Popen', FailedChild), \
                 patch.object(wrapper.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,'test','')):
                with self.assertRaisesRegex(RuntimeError, 'Batch incomplete'):
                    wrapper.launch(plans, td/'batch', 'failed-offline-batch')
            self.assertEqual(len(calls), 5)
            manifest = json.loads((td/'batch/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertTrue(all(r['status']=='failed' for r in manifest['conditions']))
            self.assertTrue(all(Path(r['console']).is_file() for r in manifest['conditions']))
            self.assertFalse(manifest['matched_instances_verified'])

    def test_reject_shared_output_roots_before_launch(self):
        with tempfile.TemporaryDirectory() as name:
            directory, _ = self.fixtures(Path(name))
            first, second = sorted(directory.iterdir())[:2]
            cfg = yaml.safe_load(second.read_text())
            cfg['experiment']['output_dir'] = yaml.safe_load(first.read_text())['experiment']['output_dir']
            second.write_text(yaml.safe_dump(cfg))
            with self.assertRaisesRegex(ValueError, 'distinct output roots'):
                wrapper.load_plan(directory)


if __name__ == '__main__':
    unittest.main()
