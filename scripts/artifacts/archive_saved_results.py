#!/usr/bin/env python3
"""Package saved scientific outputs; excludes credentials, caches and document previews."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (args.output / 'catalog.json').exists():
        parser.error('Choose a new directory; existing published catalog will not be overwritten')
    groups = {key: [] for key in ('release', 'jira', 'figures')}
    roots = ['results', 'colosseum/experiments/collusion/outputs',
             'docs/experiments/figures', 'docs/experiments/release_design_audit']
    for root in roots:
        for path in sorted((ROOT / root).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            rel = path.relative_to(ROOT)
            if 'doc-previews' in rel.parts or path.name == '.DS_Store':
                continue
            if path.is_symlink() or path.name in ('compute.env', '.env'):
                raise ValueError(f'Excluded sensitive or linked file: {rel}')
            if root == 'docs/experiments/release_design_audit' and path.name != 'results.json':
                continue
            if 'figures' in rel.parts:
                group = 'figures'
            elif 'release-pipeline' in rel.parts or root.endswith('release_design_audit'):
                group = 'release'
            else:
                group = 'jira'
            groups[group].append(path)
    args.output.mkdir(parents=True, exist_ok=True)
    bundles = []
    for name, paths in groups.items():
        archive = args.output / (name + '-20261026.tar.gz')
        records = []
        with archive.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0, filename='') as zipped:
            with tarfile.open(fileobj=zipped, mode='w') as tar:
                for path in sorted(set(paths)):
                    payload = path.read_bytes()
                    if (re.search(rb'sk-or-v1-[A-Za-z0-9]{20,}', payload)
                            or re.search(rb'Bearer\s+[A-Za-z0-9._-]{25,}', payload)
                            or re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', payload)):
                        raise ValueError(f'Credential pattern in {path.relative_to(ROOT)}')
                    rel = path.relative_to(ROOT).as_posix()
                    info = tarfile.TarInfo(rel)
                    info.size = len(payload)
                    info.mode = 0o644
                    tar.addfile(info, io.BytesIO(payload))
                    records.append({'path': rel, 'bytes': len(payload),
                                    'sha256': hashlib.sha256(payload).hexdigest()})
        bundles.append({'id': name, 'archive': archive.name,
                        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                        'bytes': archive.stat().st_size, 'files': records})
    (args.output / 'catalog.json').write_text(json.dumps({
        'snapshot_date': '2026-10-26',
        'description': 'Saved development and report artifacts; status/version labels remain authoritative.',
        'excluded': ['credentials', 'Python caches', 'OS metadata', 'document layout previews'],
        'bundles': bundles}, indent=2) + '\n')
    print(json.dumps({b['id']: {'files': len(b['files']), 'compressed_bytes': b['bytes']}
                      for b in bundles}, indent=2))


if __name__ == '__main__':
    main()
