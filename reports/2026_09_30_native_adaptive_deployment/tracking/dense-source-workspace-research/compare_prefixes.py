#!/usr/bin/env python3
"""Compare source-view and dense-workspace public outputs at all DS9 prefixes."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("fixture",type=Path)
    parser.add_argument("view",type=Path)
    parser.add_argument("candidate",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("scratch",type=Path)
    parser.add_argument("--wall-limit",type=float,default=180.0)
    args=parser.parse_args()
    lines=args.fixture.read_text().splitlines()
    rows=sorted((line.split("\t") for line in lines[1:]),
        key=lambda row:(int(row[8]),row[0]))
    first,last=int(rows[0][8]),int(rows[-1][8])
    cutoff=first
    results=[]
    started=time.monotonic()
    args.scratch.parent.mkdir(parents=True,exist_ok=True)
    while cutoff<last:
        cutoff=min(cutoff+5_000_000_000,last)
        selected=[row for row in rows if int(row[8])<=cutoff]
        args.scratch.write_text(lines[0]+"\n"+
            "\n".join("\t".join(row) for row in selected)+"\n")
        outputs=[]
        elapsed=[]
        for binary in (args.view,args.candidate):
            remaining=args.wall_limit-(time.monotonic()-started)
            if remaining<=0: raise TimeoutError("prefix comparison wall limit expired")
            begin=time.monotonic()
            outputs.append(subprocess.run([binary,args.scratch],check=True,
                capture_output=True,timeout=min(30,remaining)).stdout)
            elapsed.append(time.monotonic()-begin)
        if outputs[0]!=outputs[1]:
            raise AssertionError(f"serialized output mismatch at {cutoff}")
        results.append({"cutoff_ns":cutoff,"candidates":len(selected),
            "output_sha256":hashlib.sha256(outputs[0]).hexdigest(),
            "view_seconds":elapsed[0],"candidate_seconds":elapsed[1]})
    args.output.write_text(json.dumps({
        "schema":"leo-dense-source-workspace-prefix-parity/v1",
        "input_sha256":hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        "comparison":"byte-identical complete public CLI output",
        "prefixes":results,"elapsed_seconds":time.monotonic()-started},indent=2)+"\n")
    print(f"PASS: {len(results)} causal prefixes exact")


if __name__=="__main__": main()
