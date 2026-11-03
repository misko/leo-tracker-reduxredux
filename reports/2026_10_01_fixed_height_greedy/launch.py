"""Bounded process launcher preserving all scientific and execution outcomes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def launch(unit,folder,width=1,max_tracks=None,extended=False):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/f"{unit}-beam{width}.json"
    receipt_path=output.with_suffix(".launch.json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError(output)
    command=[sys.executable,str(HERE/"replay.py"),unit,"--output",str(output),"--width",str(width)]
    if max_tracks is not None:
        command += ["--max-tracks",str(max_tracks)]
    if extended:
        command += ["--extended"]
    env=os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        env[key]="1"
    env["PYTHONPATH"]=str(ROOT/"src")
    start=time.monotonic()
    receipt={"unit_id":unit,"command":command,"timeout_seconds":90,"output":str(output)}
    try:
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        receipt.update(status="complete" if result.returncode==0 else "error",
            returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    except subprocess.TimeoutExpired as e:
        receipt.update(status="timeout",stdout=str(e.stdout or ""),stderr=str(e.stderr or ""))
    receipt["wall_seconds"]=time.monotonic()-start
    if output.exists():
        native=json.loads(output.read_text())
        receipt["native_status"]=native["status"]
        receipt["factors"]=len(native["checkpoints"])
        receipt["gate_failures"]=native["gate_failures"]
        receipt["exception"]=native.get("exception")
    with receipt_path.open("x") as f:
        json.dump(receipt,f,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ("stdout","stderr","command")}),flush=True)
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("unit")
    p.add_argument("--folder",type=Path,required=True)
    p.add_argument("--width",type=int,default=1)
    p.add_argument("--max-tracks",type=int)
    p.add_argument("--extended",action="store_true")
    a=p.parse_args()
    launch(a.unit,a.folder,a.width,a.max_tracks,a.extended)
