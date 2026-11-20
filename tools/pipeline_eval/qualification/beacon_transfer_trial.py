"""Bind measured StarLoc captures and calibrate only surveyed donor sites."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from leo.sky.propagation import parse_element_sets

from ..__main__ import ROOT, encoded, save_json
from ..scoring import validate_result
from ..variants import beacon_transfer as model
from . import bearing_transfer_trial as prior
from .armijo_finish_results import pack
from .fresh_scenes import _destination
from .physical_differences import consolidate, simultaneous

OUT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/beacon-transfer"
CPU, CAP = (18, 19), 40
ARCHIVE = "positions.jsonl.gz"
BIND = ("native_sha256", "catalogue_sha256", "sample_sha256", "donor_sha256", "input_sha256")

WORKER = """
import json
import sys
from time import perf_counter, process_time
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (640 << 20, 640 << 20))
from tools.pipeline_eval.variants import beacon_transfer as model
q = json.load(sys.stdin)
assert set(q) == {'observation', 'catalogue', 'location', 'priors'}
value = model.solve(**q)
json.dump(dict(results=value, cpu_s=process_time()-cpu, worker_wall_s=perf_counter()-wall,
               rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def source(raw):
    seal = prior.OUT / "prediction-lock.json"
    for p, sha in prior.read(seal)["files"].items():
        if prior.digest((prior.OUT / p).read_bytes()) != sha:
            raise ValueError("changed source archive or previous measured offers")
    previous = prior.read(prior.OUT / "blind-plan.json")
    scopes = prior.read(prior.OUT / "measurement-inventory.json")["captures"]
    lookup = {row["id"]: row for row in previous["cases"] if not row["author_id"]}
    study = prior.authority.STUDY
    receipt = prior.read(study / "field-receipt.json")
    gps = {
        r["id"]: r["latlon"] for r in json.loads(prior.authority._verified_truth(receipt))["cases"]
    }
    public = study / "public_field"
    captures = []
    for item in scopes:
        alias = item["id"]
        base = lookup[alias + "-containing"]
        ident = base["original_case_id"]
        query = json.loads(
            prior.authority._read(
                public / "queries" / f"{ident}.json", receipt["public_query_sha256"][ident]
            )
        )
        catalog = prior.authority._read(
            public / "orbits" / f"{query['catalog']}.tle", query["catalog"]
        ).decode("ascii")
        meta = json.loads(
            prior.authority._read(
                public / "observations" / f"{query['observation']}.json", query["observation"]
            )
        )
        if base["catalogue_sha256"] != query["catalog"]:
            raise ValueError("source TLE changed")
        m = prior.authority._read(raw / item["date"] / "tracked_tones.mat", item["native_sha256"])
        samples = loadmat(BytesIO(m), variable_names=["main_tone_dict", "id_dict"])
        native = [consolidate(x) for x in samples["main_tone_dict"].ravel()]
        labels = [str(x.item()) for x in samples["id_dict"].ravel()]
        _, copies = simultaneous(native)
        duplicates = {
            min(c["track_rows"], key=lambda i: (np.ptp(native[i][0]), -i))
            for c in copies
            if c["harmonic_like"]
        }
        arcs = [
            dict(arc=i, time=t.tolist(), frequency=f.tolist())
            for i, a in enumerate(native)
            if i not in duplicates and (r := model.sampled(*a)) is not None
            for t, f in [r]
        ]
        cat = parse_element_sets(catalog)
        by_name = dict(zip(cat.names, cat.satellite_numbers, strict=True))
        norads = [dict(arc=i, norad=by_name[a]) for i, a in enumerate(labels)]
        clock = {
            k: meta[k]
            for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
        }
        if clock["catalog_timestamp_ns"] > clock["cutoff_utc_ns"]:
            raise ValueError("future catalogue in measured donor/target")
        captures.append(
            dict(
                id=alias,
                site=item["site"],
                first=not item["repeated_site"],
                identity=norads,
                labels=labels,
                survey=gps[ident],
                original_case=ident,
                native_sha256=item["native_sha256"],
                catalogue_sha256=query["catalog"],
                start_utc_ns=clock["anchor_utc_ns"],
                end_utc_ns=clock["anchor_utc_ns"] + round(clock["duration_s"] * 1e9),
                catalogue=catalog,
                observation=dict(clock=clock, arcs=arcs),
                near=lookup[alias + "-near-missing"]["tile"],
                containing=base["tile"],
                duplicate_arcs=sorted(duplicates),
            )
        )
    return captures, seal, previous["scoring_truth_sha256"]


def calibrate(capture):
    start = perf_counter()
    obs, catalogue, place = (capture[k] for k in ("observation", "catalogue", "survey"))
    labelled, kept = model.donor_fit(obs, catalogue, place, capture["labels"])
    blind, anonymous = model.donor_fit(obs, catalogue, place)
    metrics = dict(
        id=capture["id"],
        site=capture["site"],
        start_utc_ns=capture["start_utc_ns"],
        end_utc_ns=capture["end_utc_ns"],
        identity=capture["identity"],
        native_sha256=capture["native_sha256"],
        catalogue_sha256=capture["catalogue_sha256"],
        label_profiles=labelled,
        anonymous_profiles=blind,
        author=kept,
        anonymous=anonymous,
        duplicate_arcs=capture["duplicate_arcs"],
        worker_elapsed_s=perf_counter() - start,
    )
    print("donor", capture["id"], len(kept), len(anonymous), flush=True)
    return metrics


def fit_banks(ledger, target):
    early = model.partition(ledger, target)
    all_other = model.partition(ledger, target, strict=False)
    cases = [(early, "author"), (early, "anonymous"), (all_other, "author")]
    priors, bindings = {}, {}
    for name, (eligible, branch) in zip(model.BANKS, cases, strict=True):
        priors[name] = model.graph({q["id"]: q[branch] for q in eligible})
        bindings[name] = [q["id"] for q in eligible]
    return priors, bindings


def jobs(captures, ledger):
    for c in captures:
        if not c["first"]:
            continue
        priors, donors = fit_banks(ledger, c)
        orig = c["containing"]["center"]
        az = int(prior.digest(f"beacon-transfer-far-20261120/{c['id']}".encode())[:2], 16) % 4
        far = dict(center=_destination(orig, 65, np.pi / 2 * az), width_km=25)
        for condition, tile in (
            ("containing", c["containing"]),
            ("near-missing", c["near"]),
            ("far-missing", far),
        ):
            request = encoded(
                dict(
                    observation=c["observation"],
                    catalogue=c["catalogue"],
                    location=tile["center"],
                    priors=priors,
                )
            )
            binding = dict(
                id=c["id"] + "-" + condition,
                recording=c["id"],
                group=c["site"],
                original_case=c["original_case"],
                start_utc_ns=c["start_utc_ns"],
                tile=tile,
                condition=condition,
                native_sha256=c["native_sha256"],
                catalogue_sha256=c["catalogue_sha256"],
                sample_sha256=prior.digest(encoded(c["observation"])),
                donor_sha256=prior.digest(encoded(priors)),
                input_sha256=prior.digest(request),
                donors=donors,
            )
            yield binding, request


def command(cpu):
    command = prior.command(cpu)
    path = Path(model.__file__)
    command[-4:-4] = ["--ro-bind", str(path), str(Path("/worker") / path.relative_to(ROOT))]
    command[-1] = WORKER
    return command


def attempt(cpu, q, packet):
    start = perf_counter()
    p = subprocess.run(command(cpu), input=packet, capture_output=True, timeout=CAP)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace")[-2000:])
    stats = json.loads(p.stdout)
    methods = stats.pop("results")
    print(
        q["id"],
        *(methods[k]["metrics"].get("nominal_matches") for k in model.BANKS),
        round(perf_counter() - start, 2),
        flush=True,
    )
    rows = []
    for method, v in methods.items():
        validate_result(v)
        rows.append(
            q
            | stats
            | dict(method="beacon_transfer_" + method, result=v, elapsed_s=perf_counter() - start)
        )
    return rows


def run(raw):
    captures, original, truth = source(raw)
    paths = [
        *prior.sources(),
        Path(model.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        original,
        Path(prior.__file__).with_name("physical_differences.py"),
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    ]
    hashes = {str(p.relative_to(ROOT)): prior.digest(p.read_bytes()) for p in paths}
    save_json(OUT / "source-lock.json", hashes)
    with ThreadPoolExecutor(2) as pool:
        ledger = list(pool.map(calibrate, captures))
    cases = list(jobs(captures, ledger))
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=[q for q, _ in cases], scoring_truth_sha256=truth, cpus=CPU, per_offer_cap_s=CAP
        ),
    )
    save_json(OUT / "donor-ledger.json", dict(captures=ledger))

    def batches(i):
        return [r for q, p in cases[i :: len(CPU)] for r in attempt(CPU[i], q, p)]

    with ThreadPoolExecutor(2) as pool:
        ready = [r for batch in pool.map(batches, range(2)) for r in batch]
    if any(prior.digest((ROOT / p).read_bytes()) != sha for p, sha in hashes.items()):
        raise ValueError("source changed before prediction seal")
    parts = ("source-lock.json", "blind-plan.json", "donor-ledger.json")
    files = {name: prior.digest((OUT / name).read_bytes()) for name in parts}
    files[ARCHIVE] = pack(OUT, ARCHIVE, ready)
    save_json(OUT / "prediction-lock.json", dict(files=files, calls=len(cases)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    run(parser.parse_args().raw)
