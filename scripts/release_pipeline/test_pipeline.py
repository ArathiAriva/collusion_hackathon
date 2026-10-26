"""Launcher matching, namespace, preflight and frozen-resource contracts."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run


class PipelineTests(unittest.TestCase):
    def test_pair_filter_preserves_exact_full_schedule_rows(self):
        full=[r for pair in run.PAIRS for r in run.schedule(pilot=True,seed=10,conditions=('A',),selected_pair=pair)]
        chosen=run.schedule(pilot=True,seed=10,conditions=('A',),selected_pair=('release_manager','ops_lead'))
        self.assertEqual(chosen,[r for r in full if r['pair']==['ops_lead','release_manager']])
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0]['run_id'],'s000-p5-A')
        for pair in (('ops_lead','ops_lead'),('ops_lead','unknown'),('ops_lead',)):
            with self.assertRaises(ValueError):
                run.schedule(selected_pair=pair)

    def test_one_condition_one_pair_dry_run_has_one_trajectory(self):
        output=io.StringIO()
        def forbidden(*a,**k):
            raise AssertionError('Unexpected network call')
        with patch.object(socket.socket,'connect',forbidden),patch.object(sys,'argv',[
            'run.py','--pilot','--conditions','A','--seed','10',
            '--pair','ops_lead','release_manager','--dry-run']),contextlib.redirect_stdout(output):
            run.main()
        result=json.loads(output.getvalue())
        self.assertEqual(result['trajectory_count'],1)
        self.assertEqual(result['max_model_calls'],48)
        self.assertEqual(result['planning_rounds'],3)
        self.assertEqual(result['schedule'][0]['run_id'],'s000-p5-A')

    def test_balanced_frozen_schedule_and_partition_isolation(self):
        rows=run.schedule(instances=2)
        self.assertEqual(len(rows),48)
        self.assertEqual(len({r['run_id'] for r in rows}),len(rows))
        for block in {r['block_id'] for r in rows}:
            rr=[r for r in rows if r['block_id']==block]
            self.assertEqual({r['condition'] for r in rr},set('AD'))
            self.assertEqual(len({run.digest(r['scenario']) for r in rr}),1)
            self.assertEqual(len({r['speaking_seed'] for r in rr}),1)
            self.assertEqual(len({tuple(r['pair']) for r in rr}),1)
            for r in rr:
                cfg=run.config_for(r)
                self.assertEqual(cfg['release']['condition'],r['condition'])
                self.assertEqual(cfg['simulation']['max_planning_rounds'],3)
        heldout=run.schedule(instances=2,partition='heldout')
        self.assertFalse({r['scenario_id'] for r in rows}&{r['scenario_id'] for r in heldout})
        self.assertNotEqual(rows[0]['scenario'],heldout[0]['scenario'])

    def test_dry_run_is_offline_and_writes_nothing(self):
        def forbidden(*a,**k):
            raise AssertionError('Unexpected network call')
        with tempfile.TemporaryDirectory() as td,patch.object(socket.socket,'connect',forbidden):
            output=io.StringIO()
            with patch.object(sys,'argv',['run.py','--dry-run','--pilot','--output-root',td]),contextlib.redirect_stdout(output):
                run.main()
            result=json.loads(output.getvalue())
            self.assertEqual(result['trajectory_count'],4)
            self.assertEqual(result['max_model_calls'],192)
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_live_card_missing_and_invalid_are_rejected(self):
        rows=run.schedule(pilot=True)
        with self.assertRaises(ValueError):
            run.validate_card({},rows)
        card={'llm':{'provider':'openrouter','openrouter':{'model':'openai/gpt-4o-mini','base_url':'https://openrouter.ai/api/v1',
            'params':{'temperature':.7,'max_tokens':1500}}},
            'freeze_id':'test-only-no-live-dispatch','schedule_hash':run.digest(rows),'prompt_version':run.PROMPT_VERSION,
            'authorized_trajectories':4,'rates':{'input_per_million':.15,'output_per_million':.6,
                'source_url':'https://example.invalid/test-fixture','verified_date':'test-fixture'},
            'retry_policy':'no-automatic-trajectory-retry','stopping_rule':'run-frozen-schedule','resource_estimate_usd':1}
        self.assertEqual(run.validate_card(card,rows),card['llm'])
        with self.assertRaises(ValueError):
            run.validate_card(card,run.schedule(pilot=True,planning_rounds=4))
        for key,value in [('schedule_hash','wrong'),('authorized_trajectories',2),('resource_estimate_usd',float('nan')),('prompt_version','release-prompts-v1')]:
            bad=dict(card,**{key:value})
            with self.assertRaises(ValueError):
                run.validate_card(bad,rows)
        with self.assertRaises(ValueError):
            run.validate_card(dict(card,api_key='do-not-save-secrets'),rows)
        legacy = dict(card)
        legacy.pop('prompt_version')
        with self.assertRaises(ValueError):
            run.validate_card(legacy,rows)

    def test_native_batch_and_rescore_preserve_source_and_namespace(self):
        import asyncio
        from types import SimpleNamespace
        from experiments.collusion.release_pipeline.analysis import analyze_batch
        def forbidden(*a,**k):
            raise AssertionError('Unexpected network call')
        rows=run.schedule(pilot=True,conditions=('A','D'))[:2]
        with tempfile.TemporaryDirectory() as td,patch.object(socket.socket,'connect',forbidden),contextlib.redirect_stdout(io.StringIO()):
            args=SimpleNamespace(output_root=td,batch_id='new',live=False,run_card=None)
            asyncio.run(run.execute(args,rows,None))
            batch=Path(td)/'new'
            manifest=json.loads((batch/'manifest.json').read_text())
            self.assertEqual(manifest['status'],'complete')
            self.assertEqual(manifest['prompt_version'],run.PROMPT_VERSION)
            self.assertFalse(any('compute.env' in p for p in manifest['source_hashes']))
            self.assertTrue((batch/'source/scripts/release_pipeline/run.py').exists())
            analysis=analyze_batch(batch)
            self.assertEqual(analysis['completed_count'],2)
            self.assertEqual(len(analysis['contrasts']),1)
            self.assertEqual(analysis['contrasts'][0]['IG'],0)
            self.assertTrue((batch/'all_pair_metrics.csv').exists())
            with self.assertRaises(FileExistsError):
                asyncio.run(run.execute(args,rows,None))

    def test_default_study_is_twenty_deadline_pressure_trajectories(self):
        output=io.StringIO()
        with patch.object(sys,'argv',['run.py','--dry-run']),contextlib.redirect_stdout(output):
            run.main()
        plan=json.loads(output.getvalue())
        self.assertEqual(plan['trajectory_count'],20)
        self.assertEqual(plan['max_parallel_trajectories'],2)
        self.assertEqual(plan['max_model_calls'],960)
        self.assertEqual({r['experiment_seed'] for r in plan['schedule']},{201,202,203,204,205})
        self.assertTrue(all('deadline_pressure' in r['scenario_id'] for r in plan['schedule']))

    def test_study_seeds_and_real_parallel_overlap(self):
        import asyncio
        import threading
        from types import SimpleNamespace
        seeds=[201,202,203,204,205]
        rows=run.study_schedule(seeds,run.FAMILIES)
        self.assertEqual(len(rows),120)
        self.assertEqual(len({r['run_id'] for r in rows}),120)
        self.assertEqual({r['experiment_seed'] for r in rows},set(seeds))
        for block in {r['block_id'] for r in rows}:
            rr=[r for r in rows if r['block_id']==block]
            self.assertEqual({r['condition'] for r in rr},{'A','D'})
            self.assertEqual(len({run.digest(r['scenario']) for r in rr}),1)
            self.assertEqual(len({r['speaking_seed'] for r in rr}),1)
        native=run.run_episode
        barrier=threading.Barrier(2,timeout=10)
        lock=threading.Lock(); active=0; peak=0
        async def instrumented(*args,**kwargs):
            nonlocal active,peak
            with lock: active+=1;peak=max(peak,active)
            try:
                barrier.wait()
                return await native(*args,**kwargs)
            finally:
                with lock: active-=1
        with tempfile.TemporaryDirectory() as td,patch.object(run,'run_episode',instrumented),contextlib.redirect_stdout(io.StringIO()):
            args=SimpleNamespace(output_root=td,batch_id='parallel',live=False,run_card=None,max_parallel=2)
            asyncio.run(run.execute(args,run.schedule(pilot=True),None))
            self.assertEqual(peak,2)
            manifest=json.loads((Path(td)/'parallel/manifest.json').read_text())
            self.assertEqual(len(manifest['completed']),4)
            self.assertEqual(manifest['status'],'complete')
        for bad in ([201,201],[]):
            with self.assertRaises(ValueError): run.study_schedule(bad,run.FAMILIES)

    def test_live_endpoint_and_model_cannot_drift_from_card(self):
        from poseidon_compute import llm_config
        from experiments.common import providers
        llm={'provider':'openrouter','openrouter':{'base_url':'https://openrouter.ai/api/v1','model':'frozen/model'}}
        with patch.object(llm_config,'base_url',return_value='https://different.invalid/v1'):
            with self.assertRaises(ValueError):
                run.validate_live_endpoint(llm)
        with patch.object(llm_config,'base_url',return_value=llm['openrouter']['base_url']),patch.object(providers,'get_model_name',return_value='other/model'):
            with self.assertRaises(ValueError):
                run.validate_live_endpoint(llm)

    def test_planning_round_override_is_frozen_and_validated(self):
        three=run.schedule(pilot=True,seed=11,conditions=('A',),planning_rounds=3)
        four=run.schedule(pilot=True,seed=11,conditions=('A',),planning_rounds=4)
        self.assertNotEqual(run.digest(three),run.digest(four))
        for a,b in zip(three,four):
            self.assertEqual({k:v for k,v in a.items() if k!='planning_rounds'},
                             {k:v for k,v in b.items() if k!='planning_rounds'})
            self.assertEqual(run.config_for(a)['simulation']['max_planning_rounds'],3)
            self.assertEqual(run.config_for(b)['simulation']['max_planning_rounds'],4)
        for invalid in (0,-1,True,1.5):
            with self.assertRaises(ValueError):
                run.schedule(planning_rounds=invalid)


if __name__=='__main__':
    unittest.main()
