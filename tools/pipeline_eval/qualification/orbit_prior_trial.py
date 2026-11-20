"""Compare equal and historic phase widths on a sealed fixed-owner mask."""

import argparse
import gzip
import json
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from sgp4.alpha5 import from_alpha5

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..corpus import _selection
from ..scoring import distance_km
from ..variants import orbit_prior, robust_em, robust_orbit_fit
from ..variants.v5_lean import SOURCE
from . import owner_factor as earlier
from . import owner_factor_archive as archive
from . import owner_factor_models as model
from .fresh_scenes import _sandbox
from .full_v5_check import BULK, _load_case
from .robust_em_trials import load

REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/orbit-prior"
CONFIRMATION = ("DS26-0243", "DS26-0287", "DS26-0237", "DS26-0299")
EXCLUDED = set(earlier.CASES) | {
    "DS26-0138",
    "DS26-0154",
    "DS26-0120",
    "DS26-0012",
    "DS26-0261",
    "DS26-0259",
    "DS26-0162",
    "DS26-0060",
}
CPU = (14, 15)
NS = orbit_prior.NS
FIELD_NAMES = {
    "id",
    "rx",
    "channel",
    "rf_hz",
    "time_s",
    "folded_hz",
    "component",
    "v5_owner",
    "v5_lift",
    "role",
}
TLE = re.compile(rb"(?m)^1 ([A-Z0-9 ]{5})[^\r\n]*\r?\n(2 \1[^\r\n]*)")
SNAPSHOT = re.compile(r"([0-9]+)-([a-f0-9]{64})\.tle")
WORKER = """
import json, sys
from tools.pipeline_eval.qualification import orbit_prior_fixed as trial
from tools.pipeline_eval.qualification import owner_factor_models as model
request = json.load(sys.stdin)
result = model.blind(request) if sys.argv[1] == 'blind' else trial.refit(**request)
json.dump(result, sys.stdout, allow_nan=False)
"""


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def roster():
    candidates = set(_selection("ds26-common127")[0]) - set(_selection("roof16")[0]) - EXCLUDED
    ordered = sorted(
        candidates, key=lambda ident: digest(f"orbit-prior-confirmation-v1/{ident}".encode())
    )
    eligible = [
        ident
        for ident in ordered
        if all(_load_case(ident).get(k) for k in ("catalog", "request", "graph", "native"))
    ]
    if tuple(eligible[:4]) != CONFIRMATION:
        raise ValueError("independent hash-selected roster changed")
    return [(ident, "matched-tile") for ident in (*earlier.CASES, *CONFIRMATION)] + [
        ("DS26-0036", "wrong-region")
    ]


def elements(raw, collected, wanted):
    for match in TLE.finditer(raw):
        norad = from_alpha5(match[1].decode("ascii"))
        if norad in wanted:
            lines = (
                raw[match.start() : match.start(2)].rstrip().decode("ascii"),
                match[2].decode("ascii"),
            )
            yield norad, orbit_prior.from_lines(lines, collected)


def load_history(case, packet, wanted):
    wall, cpu = perf_counter(), process_time()
    source = _load_case(case)
    request_raw = (BULK / source["request"]["path"]).read_bytes()
    if digest(request_raw) != source["request"]["sha256"]:
        raise ValueError("request binding differs from the original capture")
    request = json.loads(request_raw)
    observation = packet["observation"]
    cutoff, anchor = (observation[k] for k in ("cutoff_utc_ns", "anchor_utc_ns"))
    collected = observation["catalog_timestamp_ns"]
    newest = packet["catalogue"].encode("ascii")
    catalog_digest = digest(newest)
    if (
        request["job"]["evaluation_reference"] is not None
        or source["cutoff_utc_ns"] != cutoff
        or not collected <= cutoff <= anchor
        or source["catalog"]["sha256"] != catalog_digest
        or request["causal_snapshots"].get(f"{collected}-{catalog_digest}.tle") != catalog_digest
    ):
        raise ValueError("the geometry catalogue lacks original causal authority")
    current = {}
    for norad, record in elements(newest, collected, wanted):
        if cutoff - 72 * 3600 * NS <= record.epoch_ns <= collected and (
            norad not in current or current[norad].epoch_ns < record.epoch_ns
        ):
            current[norad] = record
    sources = []
    for name, binding in request["causal_snapshots"].items():
        match = SNAPSHOT.fullmatch(name)
        if not match or match[2] != binding or int(match[1]) > cutoff:
            raise ValueError("the request contains an invalid or future snapshot binding")
        when = int(match[1])
        if cutoff - 72 * 3600 * NS <= when < collected:
            sources.append((when, name, binding))
    previous, used, opened, seen, missing = {}, {}, [], {catalog_digest}, 0
    root = Path(request["job"]["tle_root"]) / "archive/space-track"
    for when, name, binding in sorted(sources, reverse=True):
        if len(current) == len(previous) and all(p.epoch_ns >= when for p in previous.values()):
            break
        if binding in seen:
            continue
        try:
            raw = (root / name).read_bytes()
        except FileNotFoundError:
            missing += 1
            continue
        if digest(raw) != binding:
            raise ValueError("historical snapshot differs from its authenticated request")
        seen.add(binding)
        opened.append(dict(collected_ns=when, sha256=binding, bytes=len(raw)))
        for norad, older in elements(raw, when, current):
            if cutoff - 72 * 3600 * NS <= older.epoch_ns <= when and (
                older.epoch_ns + NS <= current[norad].epoch_ns
                and (norad not in previous or older.epoch_ns > previous[norad].epoch_ns)
            ):
                previous[norad], used[norad] = older, binding
    prior = {}
    for norad in sorted(wanted):
        now, old = current.get(norad), previous.get(norad)
        prior[str(norad)] = orbit_prior.age_width(
            now, old, anchor_ns=anchor, cutoff_ns=cutoff
        ) | dict(
            old_epoch_ns=old.epoch_ns if old else None,
            old_collection_ns=old.collected_ns if old else None,
            current_epoch_ns=now.epoch_ns if now else None,
            old_snapshot_sha256=used.get(norad),
        )
    return prior, dict(
        request_sha256=digest(request_raw),
        catalog_sha256=catalog_digest,
        cutoff_ns=cutoff,
        catalog_collection_ns=collected,
        anchor_ns=anchor,
        history_bytes=sum(x["bytes"] for x in opened),
        peak_single_snapshot_bytes=max((x["bytes"] for x in opened), default=0),
        retained_tle_text_bytes=sum(
            sum(map(len, element.lines)) + 2 for element in previous.values()
        ),
        missing_snapshot_files=missing,
        history_snapshots=opened,
        prior_wall_s=perf_counter() - wall,
        prior_cpu_s=process_time() - cpu,
    )


def worker(task, packet, cpu):
    invocation = _sandbox(cpu)
    invocation[-1:] = [WORKER, task]
    result = subprocess.run(invocation, input=encoded(packet), capture_output=True, timeout=75)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace")[-1700:])
    return json.loads(result.stdout)


def locked_earlier(panel):
    before = read(earlier.REPORT / "blind-lock.json")
    privileged = read(earlier.REPORT / "input-lock.json")
    if digest((panel / "blind-lock.json").read_bytes()) != privileged["blind_lock_sha256"]:
        raise ValueError("prior owner receipt differs")
    sources = []
    for name, expected in (
        ("blind-input-and-owners.jsonl.gz", before["inputs_sha256"]),
        ("privileged-inputs.jsonl.gz", privileged["privileged_sha256"]),
    ):
        raw = (panel / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError("sealed owner-model inputs differ")
        sources.append({r["case"]: r for r in map(json.loads, gzip.decompress(raw).splitlines())})
    return sources


def run(directory, prior_panel):
    affinity = sorted(os.sched_getaffinity(0))
    if affinity != list(CPU):
        raise ValueError("use assigned CPU 14 and 15 for the matched replay")
    tasks = roster()
    blind, privileged = locked_earlier(prior_panel)
    directory.mkdir(parents=True, exist_ok=False)
    paths = [
        Path(__file__),
        Path(__file__).with_name("orbit_prior_fixed.py"),
        Path(orbit_prior.__file__),
        Path(model.__file__),
        Path(archive.__file__),
        Path(robust_em.__file__),
        Path(robust_orbit_fit.__file__),
        REPORT / "PROTOCOL.md",
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    ]
    save_json(
        directory / "source-lock.json",
        dict(
            roster=tasks,
            files={str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths},
            reference_formula_sha256=digest(
                (SOURCE / "leo/analysis/localization_v3/phase_prior.py").read_bytes()
            ),
            frozen_previous_owner_input_lock=digest(
                (earlier.REPORT / "input-lock.json").read_bytes()
            ),
        ),
    )

    def one(job):
        i, (case, offer) = job
        cpu = CPU[i % 2]
        ident = case if offer == "matched-tile" else case + "-omitted"
        start = perf_counter()
        try:
            if case in blind:
                sealed = blind[case]
                packet, bindings, chosen = sealed["packet"], sealed["bindings"], sealed["rows"]
                if offer == "wrong-region":
                    packet, bindings = load(case, offer, directory / "cache")
                owned = privileged[case]["factors"]
            else:
                packet, bindings = load(case, offer, directory / "cache")
                chosen = worker("blind", packet, cpu)["rows"]
                owned, _sd, _shape, _archive_binding, _endpoint = archive.load_archive(case)
            sanitized = [{k: r[k] for k in FIELD_NAMES} for r in owned]
            masks, counts = model.join(sanitized, chosen)
            common = masks["common"]
            prior, history = load_history(case, packet, {row["lean_owner"] for row in common})
            order = ("equal", "history") if i % 2 == 0 else ("history", "equal")
            request = dict(packet=packet, rows=common, prior=prior, order=order)
            binding = digest(encoded(request))
            save_json(
                directory / f"{ident}-input.json",
                dict(
                    packet_sha256=binding,
                    digests=bindings,
                    history=history,
                    prior=prior,
                    common_mask_sha256=digest(encoded(common)),
                    counts=counts,
                ),
            )
            result = worker("fit", request, cpu)
            row = dict(
                id=ident,
                recording=case,
                offer=offer,
                input_sha256=binding,
                counts=counts,
                prior=prior,
                history=history,
                result=result,
                overall_wall_s=perf_counter() - start,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            row = dict(
                id=ident,
                recording=case,
                offer=offer,
                result=dict(status="unavailable", reason=str(error)),
            )
        save_json(directory / f"{ident}.json", row)
        print(ident, row["result"]["status"], row["result"].get("reason", ""), flush=True)
        return row

    def lane(i):
        os.sched_setaffinity(0, {CPU[i]})
        return [one(job) for job in list(enumerate(tasks))[i::2]]

    with ThreadPoolExecutor(2) as pool:
        rows = sum(pool.map(lane, range(2)), [])
    rows.sort(key=lambda x: tasks.index((x["recording"], x["offer"])))
    data = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    write(directory / "predictions.jsonl.gz", data)
    save_json(
        directory / "prediction-lock.json",
        dict(
            predictions_sha256=digest(data),
            source_lock_sha256=digest((directory / "source-lock.json").read_bytes()),
        ),
    )


def score(directory, output):
    raw = (directory / "predictions.jsonl.gz").read_bytes()
    lock = read(directory / "prediction-lock.json")
    if lock != dict(
        predictions_sha256=digest(raw),
        source_lock_sha256=digest((directory / "source-lock.json").read_bytes()),
    ):
        raise ValueError("prediction or source receipt changed before scoring")
    rows = list(map(json.loads, gzip.decompress(raw).splitlines()))
    refs = {}
    for prefix, panel in (("DS26-", "ds26-common127"), ("DS29-", "roof16")):
        selected = sorted({r["recording"] for r in rows if r["recording"].startswith(prefix)})
        refs.update({r["id"]: r for r in references(panel, selected)[1]})
    scores = []
    for row in rows:
        for method, result in row["result"].get("methods", {}).items():
            for arm, stage in result["arms"].items():
                ref = refs[row["recording"]]
                scores.append(
                    dict(
                        case=row["id"],
                        method=method,
                        arm=arm,
                        **stage,
                        error_km=distance_km(stage["forced_latlon"], ref["truth"]),
                        v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                    )
                )
    for name in ("predictions.jsonl.gz", "prediction-lock.json", "source-lock.json"):
        write(output / name, (directory / name).read_bytes())
    save_json(
        output / "scores.json",
        dict(
            rows=scores,
            statuses=Counter(r["result"]["status"] for r in rows),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--source-panel", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    run(local_output(args.work), args.source_panel)
    score(args.work, args.out)


if __name__ == "__main__":
    main()
