#!/usr/bin/env python3
"""Run a prepared bundle in a counterbalanced process schedule."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
METHODS = ("packed_builtin_fp64", "packed_fftw_fp64", "aligned_v5_fftw_fp32")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("bundle",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--runner",nargs="*",default=[],help="optional prefix, e.g. qemu-arm -L SYSROOT")
    args=parser.parse_args()
    manifest_path=args.bundle/"manifest.json"
    manifest=json.loads(manifest_path.read_text())
    build=json.loads((HERE/"build.receipt.json").read_text())
    expected_binaries={row["method"]:row["binary_sha256"] for row in build["builds"]}
    for method in METHODS:
        if sha(HERE/method)!=expected_binaries[method]:
            raise ValueError(f"binary fails frozen build receipt: {method}")
    rows=[]; schedule=[]
    for index,case in enumerate(manifest["cases"]):
        order=METHODS[index%3:]+METHODS[:index%3]
        template=manifest["templates"][case["template_key"]]
        protected={
            args.bundle/case["raw_file"]:case["raw_file_sha256"],
            args.bundle/template["exact"]:template["exact_sha256"],
            args.bundle/template["control"]:template["control_sha256"],
        }
        for path,expected in protected.items():
            if sha(path)!=expected: raise ValueError(f"bundle hash mismatch: {path}")
        for position,method in enumerate(order):
            command=[*args.runner,str(HERE/method),str(args.bundle/case["raw_file"]),
                     str(args.bundle/template["exact"]),str(args.bundle/template["control"]),
                     str(case["rate_hz"]),case["edge"],case["case_id"]]
            completed=subprocess.run(command,check=True,text=True,capture_output=True)
            row=json.loads(completed.stdout)
            if row["method"]!=method or row["case_id"]!=case["case_id"]:
                raise ValueError("probe returned the wrong method or case")
            rows.append(row); schedule.append({"case_id":case["case_id"],"position":position,"method":method})
        for path,expected in protected.items():
            if sha(path)!=expected: raise ValueError(f"bundle changed during run: {path}")
    result={"schema":"org.leo.research.arm-stateless-probe-suite/v1",
            "scope":"stateless saved-IQ component benchmark; not whole causal pipeline",
            "manifest_sha256":sha(manifest_path),"build_receipt_sha256":sha(HERE/"build.receipt.json"),
            "schedule":schedule,"rows":rows}
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(sha(args.output))


if __name__=="__main__": main()
