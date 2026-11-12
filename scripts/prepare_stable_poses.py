"""Prepare reusable source-hashed stable-pose options and packing-state evidence."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bom2kit.practical_geometry import stable_pose_options
from bom2kit.packing_states import audit_states


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    library=json.loads(args.library.read_bytes());started=perf_counter();poses={}
    (args.output/'state-audit.json').write_text(json.dumps(audit_states(library),indent=2),encoding='utf8')
    for index,item in enumerate(library['items'],1):
        poses[item['id']]=stable_pose_options(item,cache=args.cache)
        print(json.dumps({'done':index,'total':len(library['items']),'item':item['id'],
                          'poses':len(poses[item['id']]),'seconds':perf_counter()-started}),flush=True)
    (args.output/'stable-poses.json').write_text(json.dumps(poses),encoding='utf8')


if __name__=='__main__':main()
