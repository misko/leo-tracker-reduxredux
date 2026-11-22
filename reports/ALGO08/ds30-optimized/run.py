"""Replay both receivers from sealed DS30 I/Q to regional compact v5 positions."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import traceback
from unittest.mock import patch
from panels import PANEL_SIZES, select_panel

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_scan as deployed

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parents[1] / "2026_11_21_ds30_full"
DATA = Path("/srv/bulk/leo-dev/ds30-full-20261121")
RELEASE = Path("/opt/leo-algo08/081ab0265a9d37dbc2d3fb5b62a64d02970b67ed")
ASSETS = RELEASE / "assets"
PINS = {"deployed": "98d094c9541d22a94396df9ce00778c20030fcf88ac52257bd975b304b916cb5",
        "optimized": "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809"}
KNOWN_FAILURE = "ValueError: cavity nomination failed: ValueError('nonempty observation mask matching full design required')"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path, expected=None):
    data = path.read_bytes()
    if expected and hashlib.sha256(data).hexdigest()!=expected.removeprefix("sha256:"):
        raise ValueError(f"Input digest differs at {path}")
    return json.loads(data)


def write(path, value):
    with tempfile.NamedTemporaryFile(mode="w",dir=path.parent,delete=False) as f:
        json.dump(value,f,allow_nan=False,sort_keys=True)
        f.write("\n")
    os.replace(f.name,path)


def measure(case, inventory, identity, region, mode, binary):
    # Both arms use the installed detector adapter, causal history, acquisition, and solver.
    def receiver(kind,edge,**kwargs):
        return detector(kind,edge,binary=binary,pilot=kwargs["pilot"])
    detector=deployed.detector
    start,cpu=time.perf_counter(),time.process_time()
    with patch.object(deployed,"detector",receiver), patch.dict(deployed.PINS,{"cancellation-factors.so":PINS[mode]}):
        native=deployed.acquire(case["session_id"],identity,inventory,ASSETS)
    mid,mid_cpu=time.perf_counter(),time.process_time()
    try:
        result,packet,policy=deployed.solve(native,TleArchiveReader(DATA/"snapshot/inputs"/case["id"]/"tle"),
                                             ASSETS,region)
    except ValueError as exc:
        reason=f"ValueError: {exc}"
        if case["id"]!="DS30-0340" or reason!=KNOWN_FAILURE:
            raise
        result=dict(status="unavailable",reason=reason,arms={a:dict(latlon=None) for a in ("c0","fitted_c")})
        packet,policy=None,None
    end,end_cpu=time.perf_counter(),time.process_time()
    src=native["source"]
    assert src["raw_recording_authority_digest"]==case["raw_authority"]
    assert native["provenance"]["window_count"]==case["recording"]["window_count"]
    assert len(src["probes"])==2*case["valid_visits"]
    assert (packet is not None)==(result["status"]=="ok")
    return dict(case=case["id"],mode=mode,status=result["status"],reason=result.get("reason"),
                arms=result["arms"],policy=policy,region=region.document(),windows=inventory["window_count"],
                eligible_visits=case["valid_visits"],raw_authority=case["raw_authority"],
                factor_digest=canonical_digest(src["probes"]),detector=PINS[mode],cpu=os.sched_getcpu() if hasattr(os,"sched_getcpu") else min(os.sched_getaffinity(0)),
                owners={a:v["owner_sha256"] for a,v in packet["arms"].items()} if packet else {},
                acquisition_wall_s=mid-start,solve_wall_s=end-mid,total_wall_s=end-start,
                acquisition_cpu_s=mid_cpu-cpu,solve_cpu_s=end_cpu-mid_cpu,total_cpu_s=end_cpu-cpu)


def batch(jobs, cpu, binary, output):
    os.sched_setaffinity(0,{cpu})
    region=Algo08Region.parse(read(RELEASE/"station/region.json"))
    for lock,order in jobs:
        key=lock["case"]
        dest=output/key
        dest.mkdir(exist_ok=True)
        with (dest/"owner.lock").open("a") as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            try:
                existing=[read(dest/(m+".json")) for m in order if (dest/(m+".json")).is_file()]
                if len(existing)==len(order):
                    continue
                pair_cpu=existing[0]["cpu"] if existing else cpu
                os.sched_setaffinity(0,{pair_cpu})
                case=read(DATA/"bindings"/(key+".json"), lock["input_binding_sha256"])["case"]
                assert case["id"]==key and case["raw_authority"]==lock["raw_authority"]
                native=read(Path("/srv/bulk")/case["native"]["path"],case["native"]["sha256"])
                identity=native["source"]["input_manifest_sha256"]
                del native
                entries=[]
                for seg in case["recording"]["segments"]:
                    p=Path("/srv/bulk")/seg["path"]
                    if not p.is_file():
                        p=Path("/srv/bulk/leo/fast-scan-recordings").joinpath(*p.parts[-3:])
                    entries.append(dict(path=str(p.parent),manifest_digest="sha256:"+seg["sha256"]))
                inventory=dict(segments=entries,window_count=case["recording"]["window_count"])
                for index,mode in enumerate(order):
                    path=dest/(mode+".json")
                    if path.exists():
                        saved=read(path)
                        assert saved["detector"]==PINS[mode] and saved["raw_authority"]==case["raw_authority"]
                        continue
                    lib=binary if mode=="optimized" else ASSETS/"cancellation-factors.so"
                    result=measure(case,inventory,identity,region,mode,lib)
                    result.update(order=index,input_binding_sha256=lock["input_binding_sha256"],release=RELEASE.name)
                    write(path,result)
                    print(key,mode,result["status"],round(result["total_wall_s"],1),flush=True)
                if (dest/"failure.txt").exists():
                    (dest/"failure.txt").unlink()
            except Exception:
                (dest/"failure.txt").write_text(traceback.format_exc())
                print(key,"replay error",traceback.format_exc(),flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--panel",choices=PANEL_SIZES,default="smoke",
                        help="Use a nested prefix of the frozen DS30 order. Default: four recordings.")
    parser.add_argument("--cpus",default=str(min(os.sched_getaffinity(0))),
                        help="Comma-separated CPU IDs. Default: one worker on one core.")
    parser.add_argument("--only",nargs="+")
    return parser.parse_args(argv)


def main():
    args=parse_args()
    cpus=[int(x) for x in args.cpus.split(",")]
    assert socket.gethostname().split(".")[0]=="gauss" and len(set(cpus))==len(cpus) and set(cpus)<=os.sched_getaffinity(0)
    assert Path(deployed.__file__).resolve().is_relative_to(RELEASE)
    assert sha(args.binary)==PINS["optimized"] and sha(ASSETS/"cancellation-factors.so")==PINS["deployed"]
    for k,v in deployed.PINS.items():
        assert sha(ASSETS/k)==v
    roster=select_panel(read(FROZEN/"prediction-lock.json")["predictions"],args.panel)
    args.output.mkdir(parents=True,exist_ok=True)
    jobs=[(r,("deployed","optimized") if i%2 else ("optimized","deployed")) for i,r in enumerate(roster)
          if not args.only or r["case"] in args.only]
    assert not args.only or len(jobs)==len(set(args.only))
    jobs=[j for j in jobs if not all((args.output/j[0]["case"]/(m+".json")).is_file() for m in PINS)]
    if not jobs:
        print(f"All selected {args.panel} pairs are already saved.")
        return
    cpus=cpus[:len(jobs)]
    # A recording keeps its CPU for both passes. Batches cost similar total time under the frozen shuffle.
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        pending=[pool.submit(batch,jobs[i::len(cpus)],c,args.binary,args.output) for i,c in enumerate(cpus)]
        for task in as_completed(pending):
            task.result()
    failures=[r["case"] for r,_ in jobs if not all((args.output/r["case"]/(m+".json")).is_file() for m in PINS)]
    if failures:
        raise RuntimeError(f"Missing replay results for {failures}")


if __name__=="__main__":
    main()
