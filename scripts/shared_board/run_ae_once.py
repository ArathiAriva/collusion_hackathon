"""Launch the configured seeds in A–E without changing experiment parameters.

Use the Colosseum venv. --dry-run prints the plan without writing or calling models.
Raw artifacts retain Colosseum's layout inside a unique per-launch namespace.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'colosseum'
sys.path.insert(0, str(PROJECT))
from experiments.common.run_utils import normalize_seeds


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def load_plan(config_dir):
    """Support the matched A–E study; reject extra sweep axes rather than guessing."""
    paths = sorted(config_dir.glob('hackathon_2_1_*.yaml'))
    if len(paths) != 5:
        raise ValueError('Expected exactly five A–E configuration files')
    plans = []
    signatures = []
    for path, letter in zip(paths, 'ABCDE'):
        if path.stem.split('_')[3].upper() != letter:
            raise ValueError('Expected exactly one config for each of A, B, C, D, E')
        cfg = yaml.safe_load(path.read_text())
        exp = cfg['experiment']
        if len(cfg['llm_models']) != 1 or len(exp['sweeps']) != 1:
            raise ValueError('A–E wrapper requires one model and one sweep per condition')
        sweep = exp['sweeps'][0]
        for axis in ('topologies', 'num_agents', 'colluder_counts', 'secret_channel_enabled', 'prompt_variants'):
            if len(sweep[axis]) != 1:
                raise ValueError(f'{letter}: multiple values in {axis} are not supported')
        if 'environments' in sweep or 'environments' in exp:
            raise ValueError('Environment sweeps are not supported by this matched-study wrapper')
        seeds = normalize_seeds(sweep.get('seeds')) or normalize_seeds(exp.get('seeds'))
        seeds = seeds or normalize_seeds(cfg['simulation'].get('seed')) or [1]
        limit = exp.get('runs_per_setting')
        if limit is not None:
            if int(limit) <= 0:
                raise ValueError('runs_per_setting must be positive')
            seeds = seeds[:int(limit)]
        if len(set(seeds)) != len(seeds):
            raise ValueError(f'{letter}: duplicate seeds would collide in native output directories')
        if not exp.get('output_dir'):
            raise ValueError(f'{letter}: output_dir must be explicit')
        if exp.get('log_prompts') is False:
            raise ValueError(f'{letter}: prompt logging must remain enabled for transcript artifacts')
        signatures.append({
            'seeds': seeds, 'environment': cfg['environment'], 'models': cfg['llm_models'],
            'simulation': {k: v for k, v in cfg['simulation'].items() if k not in ('tags', 'seed')},
            'num_agents': sweep['num_agents'], 'colluder_counts': sweep['colluder_counts'],
            'selection': exp['collusion'].get('colluder_selection'),
            'agent_order': exp['collusion'].get('agent_order'),
            'planning_rounds_override': exp.get('planning_rounds'),
            'conversation_steps_override': exp.get('max_conversation_steps'),
        })
        plans.append({'condition': letter, 'path': path.resolve(), 'config': cfg,
                      'config_sha256': digest(path), 'seeds': seeds})
    if any(s != signatures[0] for s in signatures):
        raise ValueError('A–E must have matched seeds, model, task settings, team size and budgets')
    output_roots = []
    for plan in plans:
        path = Path(plan['config']['experiment']['output_dir'])
        output_roots.append((path if path.is_absolute() else PROJECT / path).resolve())
    if len(set(output_roots)) != len(output_roots):
        raise ValueError('A–E need distinct output roots to prevent concurrent native file collisions')
    return plans


def command_for(snapshot, output_base):
    # Scheduling only: avoid concurrent native seed threads sharing process-global RNGs.
    # Each condition runs in its own process; all scientific settings come from YAML.
    return [sys.executable, '-m', 'experiments.collusion.run', '--config', str(snapshot),
            '--out-dir', str(output_base), '--max-concurrent-runs', '1', '-y']


def validate_output(output_base, plan):
    batches = [p.parent for p in output_base.glob('*/config.json')]
    if len(batches) != 1:
        raise ValueError(f'Expected one native timestamped batch below {output_base}')
    batch = batches[0]
    saved = json.loads((batch / 'config.json').read_text())
    if saved != plan['config']:
        raise ValueError('Native saved configuration differs from the frozen input YAML')
    progress = json.loads((batch / 'progress.json').read_text())
    n = len(plan['seeds'])
    if (progress.get('status'), progress.get('total_runs'), progress.get('completed_runs'), progress.get('failed_runs')) != ('completed', n, n, 0):
        raise ValueError(f'Native run incomplete or failed: {progress}')
    run_paths = list(batch.glob('runs/**/run_config.json'))
    if len(run_paths) != n:
        raise ValueError('Wrong number of seed-specific native run directories')
    trajectories = []
    required = ('metrics.json', 'final_summary.json', 'agent_turns.json', 'tool_events.json',
                'agent_prompts.json', 'blackboards.json', 'agent_trajectories.json')
    for path in run_paths:
        rc = json.loads(path.read_text())
        for name in required:
            if not (path.parent / name).is_file():
                raise ValueError(f'Missing artifact: {path.parent / name}')
        final = json.loads((path.parent / 'final_summary.json').read_text())
        if final['status'] != 'complete':
            raise ValueError(f'Trajectory not complete: {path.parent}')
        if rc['sweep'] != plan['config']['experiment']['sweeps'][0]['name']:
            raise ValueError('Unexpected sweep in saved trajectory')
        trajectories.append({'condition': plan['condition'], 'seed': rc['seed'],
                             'run_id': rc['run_id'], 'run_dir': str(path.parent),
                             'final_status': final['status']})
    if sorted(t['seed'] for t in trajectories) != sorted(plan['seeds']):
        raise ValueError('Missing, duplicate or unexpected seeds in native outputs')
    summary = json.loads((batch / 'summary.json').read_text())
    if len(summary) != n or sorted(s['seed'] for s in summary) != sorted(plan['seeds']):
        raise ValueError('Native summary does not contain the expected seeds')
    for name in ('summary.csv', 'summary.jsonl', 'experiment.log'):
        if not (batch / name).is_file():
            raise ValueError(f'Missing native batch artifact: {name}')
    return str(batch), sorted(trajectories, key=lambda t: t['seed'])


def validate_matched_instances(records):
    """Compare actual generated instances per seed, after all children have exited."""
    from experiments.collusion.compute_jira_optimal import _reconstruct_instance
    signatures = {}
    for record in records:
        for item in record['trajectories']:
            d = Path(item['run_dir'])
            rc = json.loads((d / 'run_config.json').read_text())
            instance = _reconstruct_instance(d)
            signature = {'names': instance.agent_names, 'tasks': instance.tasks,
                         'costs': instance.costs, 'turn_order': rc['agent_turn_order']}
            previous = signatures.setdefault(item['seed'], signature)
            if previous != signature:
                raise ValueError(f"Generated instance/turn order mismatch for seed {item['seed']}")


def launch(plans, batch_dir, batch_id, workers=2):
    # Exclusive creation prevents overwriting any previous launch, including pilots.
    batch_dir.mkdir(parents=True, exist_ok=False)
    (batch_dir / 'configs').mkdir()
    lock = threading.Lock()
    process_lock = threading.Lock()
    stopped = threading.Event()
    active = {}
    records = []
    for p in plans:
        snapshot = batch_dir / 'configs' / p['path'].name
        snapshot.write_bytes(p['path'].read_bytes())
        if digest(snapshot) != p['config_sha256']:
            raise ValueError('Input YAML changed after preflight; refusing to launch')
        output_root = Path(p['config']['experiment']['output_dir'])
        if not output_root.is_absolute():
            output_root = PROJECT / output_root
        output_base = output_root / batch_id
        if output_base.exists():
            raise FileExistsError(f'Refusing to reuse native output namespace: {output_base}')
        records.append({'condition': p['condition'], 'status': 'queued', 'seeds': p['seeds'],
                        'source_config': str(p['path']), 'config_snapshot': str(snapshot),
                        'config_sha256': p['config_sha256'], 'output_base': str(output_base),
                        'console': str(batch_dir / f"console-{p['condition']}.log"),
                        'command': command_for(snapshot, output_base), 'trajectories': []})
    runtime_sources = ['colosseum/experiments/collusion/run.py',
                       'colosseum/experiments/collusion/prompts.py',
                       'colosseum/experiments/collusion/metrics.py',
                       'colosseum/experiments/common/local_protocol.py',
                       'colosseum/experiments/common/channel_aware_agent.py', 'colosseum/uv.lock']
    provenance = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True)
    manifest = {'schema_version': 1, 'batch_id': batch_id, 'created_at_utc': now(),
                'status': 'running', 'expected_trajectories': sum(len(p['seeds']) for p in plans),
                'condition_workers': workers, 'native_seed_concurrency': 1,
                'git_commit': provenance.stdout.strip() if provenance.returncode == 0 else None,
                'git_dirty': bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
                'wrapper_sha256': digest(Path(__file__)),
                'runtime_source_sha256': {name: digest(ROOT / name) for name in runtime_sources},
                'conditions': records, 'matched_instances_verified': False}
    manifest_path = batch_dir / 'manifest.json'

    def update(record=None, **changes):
        with lock:
            (record if record is not None else manifest).update(changes)
            atomic_json(manifest_path, manifest)

    update()

    def execute(plan, record):
        try:
            with Path(record['console']).open('x') as console:
                with process_lock:
                    if stopped.is_set():
                        update(record, status='cancelled')
                        return
                    # Saved prompt timestamps are interpreted in this zone by the auditor.
                    process = subprocess.Popen(record['command'], cwd=PROJECT, stdout=console,
                                               stderr=subprocess.STDOUT, env={**os.environ, 'TZ': 'America/Toronto'})
                    active[record['condition']] = process
                update(record, status='running', started_at_utc=now())
                returncode = process.wait()
                with process_lock:
                    active.pop(record['condition'], None)
            if returncode:
                raise RuntimeError(f'Native runner exited {returncode}; see {record["console"]}')
            output, trajectories = validate_output(Path(record['output_base']), plan)
            update(record, status='completed', output=output, trajectories=trajectories, finished_at_utc=now())
            print(f"COMPLETED {record['condition']}: {len(trajectories)} trajectories -> {output}", flush=True)
        except Exception as exc:
            update(record, status='interrupted' if stopped.is_set() else 'failed',
                   error=str(exc), finished_at_utc=now())

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(execute, p, r) for p, r in zip(plans, records)]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    except KeyboardInterrupt:
        stopped.set()
        with process_lock:
            for process in active.values():
                process.terminate()
        update(status='interrupted', finished_at_utc=now())
        raise
    finally:
        executor.shutdown(wait=True)
    if any(r['status'] != 'completed' for r in records):
        update(status='failed', finished_at_utc=now())
        raise RuntimeError(f'Batch incomplete; partial artifacts retained. Inspect {manifest_path}')
    try:
        validate_matched_instances(records)
    except Exception as exc:
        update(status='validation_failed', error=str(exc), finished_at_utc=now())
        raise
    update(status='completed', matched_instances_verified=True, finished_at_utc=now())
    print(f"ALL_FIVE_COMPLETED: {manifest['expected_trajectories']} trajectories; {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=PROJECT / 'experiments/collusion/configs/paper_shared_board')
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results/ae-batches')
    parser.add_argument('--batch-id', default=None)
    parser.add_argument('--workers', type=int, choices=range(1, 6), default=2)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    plans = load_plan(args.config_dir.resolve())
    batch_id = args.batch_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', batch_id) or batch_id in ('.', '..'):
        parser.error('batch-id must be a simple directory name')
    batch_dir = args.results_dir.resolve() / batch_id
    if args.dry_run:
        print(json.dumps({'dry_run': True, 'writes_files': False, 'model_calls': 0,
                          'batch_dir': str(batch_dir), 'condition_workers': args.workers,
                          'native_seed_concurrency': 1,
                          'expected_trajectories': sum(len(p['seeds']) for p in plans),
                          'conditions': [{'condition': p['condition'], 'config': str(p['path']),
                                          'sha256': p['config_sha256'], 'seeds': p['seeds']} for p in plans]}, indent=2))
        return
    launch(plans, batch_dir, batch_id, args.workers)


if __name__ == '__main__':
    main()
