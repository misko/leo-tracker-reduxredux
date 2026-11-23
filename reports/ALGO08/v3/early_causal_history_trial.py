"""Price earlier-orbit health checks on two saved preparation prefixes only."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
STAGED = Path("/dev/shm")
CASES = {
    "0160": dict(request="c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e",
                 native="1c56c47f871933cdc1887e41d79d2b28da0624b3104d2e5b05d0957c488bd4b5",
                 stock="ebf1a80ae206a9c32cae2374e49b050faa1d0087413b313a3189a541d7e4ed08",
                 policy="history_support", windows=3691, admitted=2354),
    "0316": dict(request="e1e3d9cd482bc4b8837f782c329702472b60e34eba8616616b5ec20ef759b739",
                 native="6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed",
                 stock="d001e6d0182324b47a5c24b19ca16ece4767cce87ed8f4e4e17dd1b29289ffed",
                 policy="stock", windows=3042, admitted=2702),
}


class PreparedForCensus(Exception):
    """Stop without evaluating any of the original numerical inference."""


def assignment(case, result_root):
    import json

    from aperture_trial import archive_identity, write
    from empty_bootstrap import checked

    source = STAGED / f"leo-v3-saved-{case}-pair-01"
    pins = CASES[case]
    src = source / "request.json"
    request = json.loads(checked(src, pins["request"]))
    published = json.loads(checked(source / "stock/joint-research-receipt.json", pins["stock"]))
    inventory = source / "stock/fast-scan-inputs" / (request["session"] + ".json")
    archive = Path(request["local_archive"]["root"])
    for path in (inventory, archive, Path(request["native_file"]), Path(request["offer_file"])):
        if not path.resolve(strict=True).is_relative_to(source):
            raise ValueError("This preparation census can only reach staged input files")
    listed = archive_identity(archive)
    if (listed["snapshots_sha256"] != request["original_archive"]["snapshots_sha256"]
            or published["solve"]["orbit_policy"] != pins["policy"] or published["receipt"]["decision"] != "complete"
            or published["receipt"]["window_count"] != pins["windows"]):
        raise ValueError("The saved ordinary policy or original causal input differs")
    inventory_sha = request["inventory"].removeprefix("sha256:")
    ready = json.loads(checked(inventory, inventory_sha))
    from_inventory = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in ready["segments"]]
    prior = [[path if Path(path).name == "manifest.json" else str(Path(path) / "manifest.json"), digest]
             for path, digest in request["manifests"]]
    if from_inventory != prior:
        raise ValueError("No physical metadata access and no change to the signed inventory is allowed")
    fixed = result_root / f"request-{case}.json"
    write(fixed, dict(request, manifests=from_inventory))
    return dict(request=str(fixed), inventory=str(inventory), archive=listed,
                derived_request_sha256=sha256(fixed.read_bytes()).hexdigest())


def worker(case, request, inventory, output):
    from aperture_trial import read, write
    from early_causal_history import census
    import empty_bootstrap as staged
    from named_history_once import ORBIT_MODES_SHA256, POSITION_SHA256, checked, observe
    from prospective_0160_solver import FIX_PINS
    from prospective_0316_solver import worker as ordinary_worker

    pins = FIX_PINS | {
        "unified_short_bootstrap.py": "eb17619ddf68f88846290523dfdd2b001aa9fea408b9a601f5555d65904a0bf3",
        "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    }
    original = staged.load_runtime
    audit = dict(prepare=[], calls_to_inference=0)

    def stop(prepared, *args, **options):
        if prepared["status"] != "inputs_prepared" or "census" in audit:
            raise ValueError("Expected one original prepared catalogue")
        begin = process_time_ns(), perf_counter_ns()
        audit["census"] = census(prepared["sky"], orbit_modes)
        audit["census_timing"] = dict(cpu_ns=process_time_ns()-begin[0], elapsed_ns=perf_counter_ns()-begin[1])
        if audit["census"]["cutoff_utc_ns"] != read(request)["causal_cutoff_utc_ns"]:
            raise ValueError("The inference boundary changed the original RF cutoff")
        raise PreparedForCensus

    with ExitStack() as stack:
        def load_runtime():
            nonlocal orbit_modes
            result = original()
            from leo.analysis.localization_v3 import orbit_modes
            from tools import algo08_position
            from tools.pipeline_eval.variants import v5_core

            checked(orbit_modes, staged.RELEASE / "src/leo/analysis/localization_v3/orbit_modes.py", ORBIT_MODES_SHA256)
            checked(algo08_position, staged.PAYLOAD / "tools/algo08_position.py", POSITION_SHA256)
            stack.enter_context(patch.object(algo08_position, "prepare_native_scan",
                                             observe(algo08_position.prepare_native_scan, audit["prepare"])))
            stack.enter_context(patch.object(v5_core, "infer", stop))
            return result

        orbit_modes = None
        stack.enter_context(patch.object(staged, "load_runtime", load_runtime))
        settings = CASES[case]
        try:
            ordinary_worker(request, "stock", output, source_pins=pins, native_sha=settings["native"],
                            windows=settings["windows"], admitted=settings["admitted"], inventory_file=inventory)
        except PreparedForCensus:
            if ([stage["status"] for stage in audit["prepare"]] != ["returned"]
                    or any(output.glob("fast-scan-automatic-work/*/terminal.json"))
                    or any(output.glob("fast-scan-standard-*/*/manifest.json"))):
                raise ValueError("Causal census ran past original preparation")
            write(output / "causal-health.json", audit)
            return
    raise ValueError("The named worker did not stop before its first numerical fit")


def run(root):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh tmpfs root for the prepare-only comparison")
    mem = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
               if line.startswith("MemAvailable:"))
    if mem < 2 * 1024 ** 2:
        raise ValueError("Insufficient memory headroom for one original preparation")
    root.mkdir()
    tmp = root / "tmp"
    tmp.mkdir()
    env = dict(os.environ, TMPDIR=str(tmp))
    original = {name: assignment(name, root) for name in CASES}
    sources = (Path(__file__), HERE / "early_causal_history.py", HERE / "early-causal-history-protocol.md")
    binding = root / "binding.json"
    write(binding, dict(machine=machine, headroom_kib=mem, pressure=Path("/proc/pressure/io").read_text(),
                        sources={name.name: sha256(name.read_bytes()).hexdigest() for name in sources},
                        assignments=original, pins=CASES))
    results = {}
    for name, inputs in original.items():
        destination = root / name
        command = [RELEASE / "venv/bin/python", "-IB", __file__, str(destination), "--case", name,
                   "--request", inputs["request"], "--inventory", inputs["inventory"]]
        clock = measure(command, env, destination)
        write(root / f"{name}-clock.json", clock)
        if clock["exit_code"] != 0:
            raise ValueError(f"Preparation prefix failed before census. See {destination.with_suffix('.stderr')}")
        results[name] = dict(clock=clock, evidence=read(destination / "causal-health.json"))
    write(root / "result.json", dict(binding_sha256=sha256(binding.read_bytes()).hexdigest(),
                                     attempts=results, inference_calls=0, waveform_calls=0))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if args.case is None:
        run(args.output)
    else:
        worker(args.case, args.request, args.inventory, args.output)
