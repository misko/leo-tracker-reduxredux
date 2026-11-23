"""Time the saved physical and geographic proof-cache pairs."""

from functools import partial
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from aperture_trial import RELEASE, read, write
from dense_full_short_raw import usage
from dense_geographic_trial import host
from full_short_physical import environment
from terminal_proof_reuse import projection

HERE = Path(__file__).resolve().parent
ORDERS = {"north-near": ("plain", "cached"), "physical": ("cached", "plain"), "north-far": ("plain", "cached")}


def inputs(case):
    if case == "physical":
        from short_stereo_trial import load_source, source_for

        recording, archive, region, pin, offer, _ = load_source(case)
        return source_for(case)[3], pin, recording, archive["root"], region, offer
    from local_future_omissions import assigned

    row = assigned(case)
    return row["packet"], row["native_sha256"], row["recording"], row["archive"]["root"], row["region"], row["offer"]


def worker(output, arm, saved, pin, recording, archive, region, geo, regional):
    import full_short_run
    from local_future_repair_trial import worker as publish

    audit = dict(requests=0, hits=0, scored_points=0, scorer_cpu_s=0., lookup_cpu_s=0.)
    projected = partial(projection, full_short_run.geographic_projection, audit, arm == "cached")
    with patch.object(full_short_run, "geographic_projection", projected):
        publish(saved, pin, output, recording, archive, region, geo, regional)
    write(output / "proof-reuse.json", audit)


def run(root):
    host()
    root.mkdir(exist_ok=False)
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    libs = read(HERE / "measurements/short-raw-diagnostic.json")["native_libraries"]
    for case, order in ORDERS.items():
        saved, pin, recording, archive, region, offer = inputs(case)
        for arm in order:
            output = root / f"{case}-{arm}"
            cmd = [python, "-BPs", __file__, "worker", output, arm, saved, pin, recording, archive, region,
                   libs["geographic"]["path"], libs["regional"]["path"]]
            start, before = perf_counter(), usage()
            job = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
            after = usage()
            write(root / f"{case}-{arm}-clock.json", dict(elapsed_s=perf_counter()-start, status=job.returncode,
                  stderr_tail=job.stderr[-2500:], offer=offer, native_sha256=pin, **{k: after[k]-before[k] for k in before}))
            if job.returncode:
                raise RuntimeError(job.stderr[-2500:])


def score(root):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    results = {}
    for case, order in ORDERS.items():
        pair = {}
        for arm in order:
            folder = root / f"{case}-{arm}"
            report = read(folder / "joint-research-receipt.json")
            receipt = report["receipt"]
            terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
            clock = read(root / f"{case}-{arm}-clock.json")
            rebuilt = artifacts(folder, receipt)
            if (terminal["native_sha256"] != clock["native_sha256"] or clock["offer"] != terminal["region"]
                    or clock["status"] or canonical_digest(terminal) != receipt["terminal_sha256"]
                    or canonical_digest(rebuilt) != canonical_digest(report["evidence"])):
                raise ValueError("Unbound terminal, changed offer, or scientific publication differs")
            numerical = dict(rebuilt)
            if receipt["decision"] == "complete":
                grid = FastStandardAnalysisStore(folder).position_grid(receipt["run_id"])
                if not grid["complete"]:
                    raise ValueError("Incomplete numerical grid")
                numerical["grid"] = canonical_digest({k: v for k, v in grid.items() if k != "elapsed_seconds"})
            pair[arm] = dict(clock=clock, cache=read(folder / "proof-reuse.json"), solve=report["solve"],
                             decision=receipt["decision"], terminal=receipt["terminal_sha256"], arms=terminal["arms"],
                             owners_sha256=canonical_digest(report["selected_rows"]), artifacts=rebuilt,
                             scientific_evidence_sha256=canonical_digest(numerical))
        science = ("decision", "terminal", "arms", "owners_sha256", "scientific_evidence_sha256")
        if any(pair["cached"][k] != pair["plain"][k] for k in science):
            raise ValueError("Cache changed scientific results")
        results[case] = pair
    return dict(cases=results, order=ORDERS, pins={p.name: sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), HERE / "terminal_proof_reuse.py", HERE / "terminal-proof-reuse-protocol.md")})


if __name__ == "__main__":
    mode, root, *args = sys.argv[1:]
    if mode == "run":
        run(Path(root))
    elif mode == "worker":
        worker(Path(root), *args)
    elif mode == "score":
        print(json.dumps(score(Path(root)), indent=2, allow_nan=False))
    else:
        raise ValueError(mode)
