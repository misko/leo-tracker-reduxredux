"""Reviewed eight-recording batches; no automatic full-campaign loop."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.append(str(HERE.parent/'2026_09_30_broad_prior_acquisition'))
from common import selected_units,write_new,digest


def batch(number,folder,workers=2,student_df=4.):
    if number not in range(1,9) or workers not in (1,2):
        raise ValueError('expected batch1..8 and one or two workers')
    spec=importlib.util.spec_from_file_location('fixed_height_launch_joint',HERE/'launch_joint.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    output=Path(folder)/f'batch-{number:02d}'
    if (output/'batch.json').exists(): raise FileExistsError(output/'batch.json')
    units=selected_units()[(number-1)*8:number*8]
    # Verify availability before starting a batch, rather than silently losing units.
    for unit in units:
        orbit=Path.home()/f'.cache/leo/research/fixed_height_greedy/orbits/{unit}-orbits-extended.json'
        if not orbit.exists(): raise FileNotFoundError(orbit)
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[]
        for unit in units:
            receipt=output/f'{unit}-joint.launch.json'
            if not receipt.exists():
                futures.append(pool.submit(launcher.launch,unit,output,None,3,student_df))
        for future in as_completed(futures): future.result()
    rows=[]
    for unit in units:
        launch=json.loads((output/f'{unit}-joint.launch.json').read_text())
        rows.append({key:launch.get(key) for key in ('unit_id','status','native_status','wall_seconds','fits','exception')})
    document={'batch':number,'units':units,'workers':workers,'student_df':student_df,
              'rows':rows,'wall_seconds':time.monotonic()-start,
              'protocol_sha256':digest(HERE/'PROTOCOL.md')}
    write_new(output/'batch.json',document)
    print(json.dumps(document),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('number',type=int);p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--student-df',type=float,default=4.)
    a=p.parse_args();batch(a.number,a.folder,a.workers,a.student_df)
