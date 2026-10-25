"""Offline launch-plan checks for the historical path-placement experiment."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import run_interior_ab as runner


class InteriorLauncherTests(unittest.TestCase):
    def test_matched_plan_keeps_original_files_unchanged(self):
        folder = runner.PROJECT / 'experiments/collusion/configs/interior_placement'
        before = {p: p.read_bytes() for p in folder.glob('*.yaml')}
        plans = runner.plans()
        self.assertEqual([p['condition'] for p in plans], ['A', 'B'])
        self.assertTrue(all(p['seeds'] == [101, 102, 103, 104, 105] for p in plans))
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_dry_run_does_not_launch_or_write(self):
        output = io.StringIO()
        with patch('sys.argv', ['run_interior_ab.py', '--dry-run']), \
             patch.object(runner, 'launch', side_effect=AssertionError('No inference')), \
             patch.object(runner.shutil, 'copyfile', side_effect=AssertionError('No writes')), \
             redirect_stdout(output):
            runner.main()
        plan = json.loads(output.getvalue())
        self.assertEqual(plan['trajectories'], 10)
        self.assertEqual(plan['workers'], 2)
        self.assertEqual(plan['native_seed_concurrency'], 1)
        self.assertFalse(plan['writes'])
        self.assertEqual(plan['model_calls'], 0)


if __name__ == '__main__':
    unittest.main()
