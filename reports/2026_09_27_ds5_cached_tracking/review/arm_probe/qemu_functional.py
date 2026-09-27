#!/usr/bin/env python3
"""Bounded emulated NEON correctness check. Its timings are never evidence."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BUNDLE=Path("/tmp/leo-arm-probe-bundle-20260927-1")
SYSROOT=Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot")
METHODS=("packed_builtin_fp64","packed_fftw_fp64","aligned_v5_fftw_fp32")


def sha_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def scientific(value):
    if isinstance(value,dict): return {k:scientific(v) for k,v in value.items() if "cpu_ms" not in k and "wall_ms" not in k and k!="index"}
    if isinstance(value,list): return [scientific(v) for v in value]
    return value


def signature(row):
    return [scientific(rep["receivers"]) for rep in row["repetitions"]]


def compare(base,candidate,rate):
    findings=[]
    for rep,(br,cr) in enumerate(zip(base["repetitions"],candidate["repetitions"])):
        for rx,(b,c) in enumerate(zip(br["receivers"],cr["receivers"])):
            bd,cd=b["result"],c["result"]
            same_order=bd["rank"]["order"]==cd["rank"]["order"]
            same_window=bd["confirmation_window_mask"]==cd["confirmation_window_mask"]
            bp,cp=bd["confirmations"][0],cd["confirmations"][0]
            same_count=bp["candidate_count"]==cp["candidate_count"]
            timing_us=None; cfo_hz=None; same_fractional=None
            if bp["candidate_count"] and cp["candidate_count"]:
                bc,cc=bp["candidates"][0],cp["candidates"][0]
                period=rate/750.0
                delta=(cc["epoch"]+cc["fractional_offset_samples"])-(bc["epoch"]+bc["fractional_offset_samples"])
                delta=(delta+period/2)%period-period/2
                timing_us=abs(delta)/rate*1e6
                cfo_hz=abs(cc["tracking_cfo_hz"]-bc["tracking_cfo_hz"])
                same_fractional=cc["fractional_complete"]==bc["fractional_complete"]
            passed=same_order and same_window and same_count and (timing_us is None or timing_us<=2) and (cfo_hz is None or cfo_hz<=8000) and (same_fractional is not False)
            findings.append({"repetition":rep,"receiver":rx,"same_rank_order":same_order,
                "same_confirmation_window":same_window,"same_candidate_count":same_count,
                "circular_timing_error_us":timing_us,"tracking_cfo_error_hz":cfo_hz,
                "same_fractional_complete":same_fractional,"passed":passed})
    return findings


def main():
    manifest=json.loads((BUNDLE/"manifest.json").read_text())
    cases=[next(c for c in manifest["cases"] if c["split"]=="dev"),
           next(c for c in manifest["cases"] if c["split"]=="control" and "pilot" in c["case_id"])]
    receipt={"schema":"org.leo.research.arm-stateless-qemu-functional/v1",
             "timing_valid":False,"environment":"qemu-arm user emulation, not target hardware","cases":[]}
    for case in cases:
        template=manifest["templates"][case["template_key"]]; rows={}; hashes={}
        for method in METHODS:
            command=["qemu-arm","-L",str(SYSROOT),str(HERE/method),str(BUNDLE/case["raw_file"]),
                     str(BUNDLE/template["exact"]),str(BUNDLE/template["control"]),str(case["rate_hz"]),case["edge"],case["case_id"]]
            output=subprocess.run(command,check=True,capture_output=True,timeout=90).stdout
            hashes[method]=sha_bytes(output); rows[method]=json.loads(output)
            if not all(x==signature(rows[method])[0] for x in signature(rows[method])):
                raise ValueError(f"nondeterministic science under emulation: {method}")
        fp64=compare(rows["packed_builtin_fp64"],rows["packed_fftw_fp64"],case["rate_hz"])
        fp32=compare(rows["packed_builtin_fp64"],rows["aligned_v5_fftw_fp32"],case["rate_hz"])
        if not all(x["passed"] for x in fp64+fp32): raise ValueError("emulated scientific rail failed")
        receipt["cases"].append({"case_id":case["case_id"],"output_sha256":hashes,
                                  "fp64_fftw_vs_builtin":fp64,"aligned_fp32_vs_builtin":fp32})
    path=HERE/"qemu.functional.json"; path.write_text(json.dumps(receipt,indent=2)+"\n")
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=="__main__": main()
