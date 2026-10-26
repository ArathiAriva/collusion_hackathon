#!/usr/bin/env python3
"""Validate human/judge records against a saved blinded packet; no inference."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'colosseum'))
from experiments.collusion.release_pipeline.analysis import load
from experiments.collusion.release_pipeline.annotations import validate_annotation
from experiments.collusion.release_pipeline.runner import write_json

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--records',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    packet=load(args.packet)
    records=load(args.records)
    if not isinstance(records,list) or args.output.exists():
        p.error('Records must be a list and output path unused')
    checked=[{'record':r,'assessment':validate_annotation(r,packet)} for r in records]
    write_json(args.output,{'packet_id':packet['packet_id'],'annotations':checked})
    print(f'Validated {len(checked)} annotations')
