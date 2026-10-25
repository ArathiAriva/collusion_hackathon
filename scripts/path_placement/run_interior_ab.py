"""Launch only the two matched interior-placement configs; no experiment overrides."""
import argparse
import json
import shutil
import re
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared_board'))
from run_ae_once import ROOT, PROJECT, digest, launch

DEFAULT_BATCH_ID = 'ab-interior-seeds101-105'


def plans():
    directory = PROJECT / 'experiments/collusion/configs/interior_placement'
    items = []
    for letter, name in [('A', 'hackathon_2_1_a_pair_private_channel.yaml'),
                         ('B', 'hackathon_2_1_b_pair_no_channel.yaml')]:
        path = directory / name
        cfg = yaml.safe_load(path.read_text())
        baseline = yaml.safe_load((directory.parent / name).read_text())
        assert cfg['communication_network']['path_order'] == 'swap_endpoints_inward'
        assert cfg['experiment']['seeds'] == [101, 102, 103, 104, 105]
        assert cfg['experiment']['max_concurrent_runs'] == 1
        # Refuse unintended scientific changes relative to the original A/B files.
        expected = json.loads(json.dumps(baseline))
        expected['communication_network']['path_order'] = 'swap_endpoints_inward'
        expected['experiment']['max_concurrent_runs'] = 1
        for obj in (expected,):
            obj['simulation']['tags'] = cfg['simulation']['tags']
            obj['experiment']['tag'] = cfg['experiment']['tag']
            obj['experiment']['output_dir'] = cfg['experiment']['output_dir']
            obj['experiment']['sweeps'][0]['name'] = cfg['experiment']['sweeps'][0]['name']
        assert expected == cfg, f'Unexpected scientific setting change: {letter}'
        items.append({'condition': letter, 'path': path.resolve(), 'config': cfg,
                      'config_sha256': digest(path), 'seeds': cfg['experiment']['seeds']})
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-id', default=DEFAULT_BATCH_ID)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.batch_id) or args.batch_id in ('.', '..'):
        parser.error('Invalid batch ID')
    items = plans()
    batch_id = args.batch_id
    batch = ROOT / 'results/ae-batches' / batch_id
    if args.dry_run:
        print(json.dumps({'batch_id': batch_id, 'conditions': ['A', 'B'],
                          'seeds': items[0]['seeds'], 'trajectories': 10,
                          'workers': 2, 'native_seed_concurrency': 1,
                          'config_sha256': {p['condition']: p['config_sha256'] for p in items},
                          'model_calls': 0, 'writes': False}, indent=2))
        return
    if batch.exists():
        raise FileExistsError(f'Refusing to reuse batch: {batch}')
    source = batch.with_name(batch_id + '-source')
    source.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__).resolve(), ROOT/'scripts/shared_board/run_ae_once.py',
             PROJECT/'experiments/collusion/run.py', PROJECT/'experiments/collusion/prompts.py',
             PROJECT/'experiments/collusion/metrics.py', PROJECT/'experiments/common/local_protocol.py',
             PROJECT/'experiments/common/channel_aware_agent.py', PROJECT/'uv.lock',
             PROJECT/'experiments/collusion/configs/interior_placement/README.md']
    hashes = {}
    for path in files:
        dest = source / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        hashes[str(path.relative_to(ROOT))] = digest(dest)
    (source/'sha256.json').write_text(json.dumps(hashes, indent=2)+'\n')
    launch(items, batch, batch_id, workers=2)


if __name__ == '__main__':
    main()
