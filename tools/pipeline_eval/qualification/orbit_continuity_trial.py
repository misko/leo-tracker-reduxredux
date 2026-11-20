"""Run and lock an early-trained causal forecast from native archives."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import orbit_continuity as model
from . import orbit_proposals_trial as prior
from .armijo_finish_results import pack

OUT = prior.old.OUT.parent.parent / "original-support/orbit-continuity"
world = prior.world
CPUS, CAP = (16, 17), 100
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

t, c = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (768 << 20, 768 << 20))
from tools.pipeline_eval.variants import orbit_continuity as m
q = json.load(sys.stdin)
assert set(q) == {'capture','shuffle'}
d = q['capture']
assert d['catalog_timestamp_ns'] <= d['cutoff_utc_ns']
cap = SimpleNamespace(**(d | {'catalog':d['catalog'].encode('ascii')}))
result = m.solve(cap, is_null=q['shuffle'])
json.dump(dict(result=result,cpu_s=process_time()-c,worker_s=perf_counter()-t,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),sys.stdout,allow_nan=False)
"""


def roster():
    original, cases, previous = prior.authority()
    root = world.prior.archive.REPORT
    archive = root / "prediction-lock.json"
    world.verify(root, world.read(archive)["files"])
    used = {q["recording"] for q in cases}
    eligible = [
        q
        for q in world.read(root / "plan.json")["cases"]
        if q["cohort"] == "roof" and q["recording"] not in used
    ]
    selected = min(
        eligible,
        key=lambda q: world.digest(
            f"orbit-continuity-early-lock-20261119/{q['recording']}".encode()
        ),
    )
    p = selected["packet"]
    fresh = dict(
        id=selected["id"],
        recording=selected["recording"],
        cohort="fresh",
        tile=p["offer"],
        native_sha256=p["native"]["sha256"],
        catalog_sha256=p["catalogue"]["sha256"],
        cutoff=p["cutoff"],
        collected=p["catalog_timestamp"],
        shuffle=False,
        original_request_sha256=world.digest(encoded(p)),
    )
    return cases + [fresh], previous, (original, archive)


def run():
    selected, pinned, authorities = roster()
    paths = [Path(m.__file__) for m in (model, model.inverse, model.forward)]
    paths.extend(
        ROOT / "tools/pipeline_eval/variants" / (n + ".py")
        for n in (
            "joint_pass",
            "pass_hypotheses",
            "absolute_doppler",
            "doppler_turns",
        )
    )
    paths.append(ROOT / "tools/pipeline_eval/scoring.py")
    frozen = {
        str(p.relative_to(ROOT)): world.digest(p.read_bytes())
        for p in (
            *authorities,
            *paths,
            Path(__file__),
            OUT / "PROTOCOL.md",
            prior.OUT / "source-lock.json",
        )
    }
    save_json(OUT / "source-lock.json", frozen)
    save_json(OUT / "blind-plan.json", dict(cases=selected, cpus=list(CPUS), cap_s=CAP))

    def lane(i):
        command = prior.old.previous.command(CPUS[i], WORKER, paths)
        results = []
        for q in selected[i::2]:
            start = perf_counter()
            cap = prior.old.load(q["recording"])
            if (
                cap.native_sha256,
                cap.catalog_sha256,
                cap.cutoff_utc_ns,
                cap.catalog_timestamp_ns,
            ) != tuple(q[k] for k in ("native_sha256", "catalog_sha256", "cutoff", "collected")):
                raise ValueError("changed authenticated receiver input")
            payload = encoded(
                dict(
                    capture=vars(cap) | {"catalog": cap.catalog.decode("ascii")},
                    shuffle=q["shuffle"],
                )
            )
            digest = world.digest(payload)
            if q["id"] in pinned and pinned[q["id"]]["input_sha256"] != digest:
                raise ValueError("the frozen native authority differs from the earlier receiver")
            try:
                p = subprocess.run(
                    command, input=payload, capture_output=True, check=True, timeout=CAP
                )
                entry = json.loads(p.stdout)
            except (OSError, ValueError, subprocess.SubprocessError) as err:
                reason = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
                entry = dict(
                    result=dict(
                        status="timed_out"
                        if isinstance(err, subprocess.TimeoutExpired)
                        else "failed",
                        reason=reason or str(err),
                        boundary=model.BOUNDARY,
                        metrics={},
                        arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
                    )
                )
            validate_result(entry["result"])
            elapsed = perf_counter() - start
            m = entry["result"]["metrics"]
            print(
                q["id"],
                entry["result"]["status"],
                m.get("early_links"),
                m.get("held_coherent_hits"),
                m.get("held_lead"),
                round(elapsed, 2),
                flush=True,
            )
            results.append(
                dict(
                    q,
                    method=model.METHOD,
                    input_sha256=digest,
                    cpu=CPUS[i],
                    native_elapsed_s=elapsed,
                    **entry,
                )
            )
        return results

    with ThreadPoolExecutor(2) as executor:
        rows = [r for group in executor.map(lane, range(2)) for r in group]
    if any(world.digest((ROOT / name).read_bytes()) != h for name, h in frozen.items()):
        raise ValueError("source changed during the frozen receiver run")
    files = {
        f: world.digest((OUT / f).read_bytes()) for f in ("source-lock.json", "blind-plan.json")
    }
    files["positions.jsonl.gz"] = pack(OUT, "positions.jsonl.gz", rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in selected], files=files))


if __name__ == "__main__":
    run()
