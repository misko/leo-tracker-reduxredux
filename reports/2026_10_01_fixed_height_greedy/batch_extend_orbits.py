#!/usr/bin/env python3
"""Prepare one frozen eight-unit slice of extended causal orbit banks."""
from __future__ import annotations
import argparse,importlib.util,json,subprocess,sys,time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
BASE=ROOT/"reports/2026_09_30_gaussian_sum_64_scan/evidence"
CACHE=Path.home()/".cache/leo/research/fixed_height_greedy/orbits"
sys.path.append(str(HERE.parent/"2026_09_30_broad_prior_acquisition"))
from common import selected_units,digest,write_new  # noqa:E402


def adapter():
    spec=importlib.util.spec_from_file_location("fixed_extend_orbits",HERE/"extend_orbits.py")
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module


def verify_existing(unit,cache_dir=CACHE):
    cache_dir=Path(cache_dir);module=adapter(); state=cache_dir/f"{unit}-orbits-extended.npz"; meta_path=cache_dir/f"{unit}-orbits-extended.json"
    if not state.exists() or not meta_path.exists(): return None
    meta=json.loads(meta_path.read_text())
    if digest(state)!=meta["state_sha256"]: raise ValueError(f"extended state mismatch: {unit}")
    parent=Path(meta["parent"]["state_path"])
    if digest(parent)!=meta["parent"]["state_sha256"]: raise ValueError(f"parent state mismatch: {unit}")
    with np.load(parent,allow_pickle=False) as old,np.load(state,allow_pickle=False) as new:
        n=int(meta["extension"]["added_knots_per_side"])
        if not (np.array_equal(old["satellite_ids"],new["satellite_ids"]) and
                np.array_equal(old["knot_times_s"],new["knot_times_s"][n:-n]) and
                np.array_equal(old["positions_ecef_km"],new["positions_ecef_km"][:,n:-n]) and
                np.array_equal(old["velocities_ecef_km_s"],new["velocities_ecef_km_s"][:,n:-n])):
            raise ValueError(f"parent knots not preserved: {unit}")
    return {"unit_id":unit,"status":"reused_verified","state_path":str(state),"state_sha256":meta["state_sha256"]}


def prepare_one(unit,cache_dir=CACHE):
    cache_dir=Path(cache_dir);existing=verify_existing(unit,cache_dir)
    if existing:return existing
    module=adapter(); canonical_path=BASE/f"{unit}.json";canonical=json.loads(canonical_path.read_text())
    source=Path(canonical["source"]["path"]);state=cache_dir/f"{unit}-orbits-extended.npz";meta_path=cache_dir/f"{unit}-orbits-extended.json"
    if state.exists() or meta_path.exists(): raise FileExistsError(f"partial output exists for {unit}")
    meta=module.extend_orbit_bank(source,BASE/f"{unit}-orbits.json",BASE/f"{unit}-orbits.npz",state,padding_s=120.)
    meta["canonical_observation"]={"path":str(canonical_path.resolve()),"sha256":digest(canonical_path),
        "source_binding_verified":canonical["source"]["sha256"]==meta["observation"]["sha256"]}
    write_new(meta_path,meta)
    return {"unit_id":unit,"status":"extended","state_path":str(state),"state_sha256":meta["state_sha256"]}


def batch_units(number:int):
    if number not in range(1,9):raise ValueError("batch number must be 1..8")
    return selected_units()[(number-1)*8:number*8]


def child_command(unit,cache_dir=CACHE):
    return ["sudo","-n","env",f"PYTHONPATH={ROOT/'src'}",sys.executable,str(Path(__file__).resolve()),
            "--unit",unit,"--cache-dir",str(Path(cache_dir).resolve())]


def batch(number:int,cache_dir=CACHE):
    cache_dir=Path(cache_dir)
    units=batch_units(number);attempts=[]
    for unit in units:
        start=time.monotonic();existing=verify_existing(unit,cache_dir)
        if existing: row=existing
        else:
            command=child_command(unit,cache_dir)
            try:
                result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
                row={"unit_id":unit,"status":"extended" if result.returncode==0 else "error",
                     "returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr}
            except subprocess.TimeoutExpired as error:
                row={"unit_id":unit,"status":"timeout","stdout":str(error.stdout or ""),"stderr":str(error.stderr or "")}
            if row["status"]=="extended":
                verified=verify_existing(unit,cache_dir);row.update(state_path=verified["state_path"],state_sha256=verified["state_sha256"])
        row["wall_seconds"]=time.monotonic()-start;attempts.append(row)
        if row["status"] in {"error","timeout"}:break
    receipt={"schema":"fixed-height-orbit-extension-batch/v1","batch":number,"units":units,
             "padding_s":120.,"timeout_s_per_bank":30.,"attempts":attempts}
    output=HERE/"orbit-prep"/f"batch-{number:02d}.json";write_new(output,receipt);print(json.dumps(receipt))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("number",type=int,nargs="?");p.add_argument("--unit");p.add_argument("--cache-dir",type=Path,default=CACHE)
    a=p.parse_args()
    if a.unit: print(json.dumps(prepare_one(a.unit,a.cache_dir)))
    elif a.number is not None: batch(a.number,a.cache_dir)
    else:p.error("provide batch number or --unit")
