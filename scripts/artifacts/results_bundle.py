#!/usr/bin/env python3
"""Verify and unpack the checked-in result archives without inference or credentials."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'artifacts/results/catalog.json'


def unpack(catalog, destination, selected=None):
    catalog = Path(catalog)
    data = json.loads(catalog.read_text())
    destination = Path(destination).resolve()
    chosen = [b for b in data['bundles'] if selected is None or b['id'] in selected]
    if selected and set(selected) != {b['id'] for b in chosen}:
        raise ValueError('Unknown bundle selection')
    # Validate every archive and output path before extracting any files.
    for bundle in chosen:
        archive = catalog.parent / bundle['archive']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != bundle['sha256']:
            raise ValueError(f'Archive checksum mismatch: {archive.name}')
        expected = {f['path']: f for f in bundle['files']}
        with tarfile.open(archive, 'r:gz') as tar:
            members = tar.getmembers()
            if len(members) != len(expected) or {m.name for m in members} != set(expected):
                raise ValueError('Archive inventory mismatch')
            for member in members:
                parts = PurePosixPath(member.name)
                if parts.is_absolute() or '..' in parts.parts or not member.isfile():
                    raise ValueError('Unsafe archive member')
                target = destination.joinpath(*parts.parts)
                if not target.resolve().is_relative_to(destination):
                    raise ValueError('Archive destination escapes output root')
                if target.exists():
                    raise FileExistsError(f'Use a fresh destination: {target}')
                payload = tar.extractfile(member).read()
                record = expected[member.name]
                if len(payload) != record['bytes'] or hashlib.sha256(payload).hexdigest() != record['sha256']:
                    raise ValueError(f'Member checksum mismatch: {member.name}')
    for bundle in chosen:
        with tarfile.open(catalog.parent / bundle['archive'], 'r:gz') as tar:
            for member in tar.getmembers():
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(tar.extractfile(member).read())
    return {b['id']: len(b['files']) for b in chosen}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True,
                        help='Fresh directory; paths inside match the repository layout')
    parser.add_argument('--bundles', nargs='+', choices=['release', 'jira', 'figures'])
    args = parser.parse_args()
    print(json.dumps(unpack(CATALOG, args.destination, args.bundles), indent=2))


if __name__ == '__main__':
    main()
