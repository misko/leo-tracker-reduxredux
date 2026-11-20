"""Freeze a sparse recording-level detector audit and run missing exact compact controls."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from itertools import islice
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, POSITION_FAILURES, coordinate, distance_km, validate_result
from ..variants import selective_capture
from . import complete_detector_roster as fixed
from . import one_lane_roster as roster
from . import one_lane_roster_results as stock
from . import support_cross_trial as compact
from . import two_rate_holdout_trial as two_rate
from .factor_cross import CFO, winner
from .full_v5_check import ALIAS_HZ, FRAME_HZ, _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

REPORT = fixed.SCREEN / "retry-and-transfer/cascade-audit"
DEVELOPMENT = ("DS26-0036", "DS29-0082")
CPUS = (14, 15)
STRIDE = 32
SALT = "cascade-audit/v1"


def digest(*fields):
    return sha256(encoded([SALT, *fields])).hexdigest()


def audit_schedule(probes, manifest):
    """Return fixed selections from complete blocks of valid dual visits."""
    rows = selective_capture.visit_pairs(probes)
    selected = []
    for block in range(len(probes) // (2 * STRIDE) + 1):
        chunk = list(islice(rows, STRIDE))
        if len(chunk) < STRIDE:
            return selected, block * STRIDE + len(chunk)
        offset = int(digest(manifest, block), 16) % STRIDE
        visit, lanes = chunk[offset]
        selected.append((visit, lanes))
    raise ValueError("inconsistent physical probe count")


def signal(original, fast, sample_rate):
    indexes = [winner(p["candidates"]) for p in (original, fast)]
    if None in indexes:
        outcome = (
            "neither"
            if indexes == [None, None]
            else "fast_only"
            if indexes[0] is None
            else "original_only"
        )
        return dict(outcome=outcome, epoch_samples=None, cfo_hz=None, alias_steps=None)
    a, b = [p["candidates"][i] for p, i in zip((original, fast), indexes, strict=True)]
    a_time, b_time = [
        c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"] for c in (a, b)
    ]
    epoch = selective_capture.wrapped(a_time - b_time, round(sample_rate / FRAME_HZ))
    difference = a[CFO] - b[CFO]
    alias = round(difference / ALIAS_HZ)
    residual = difference - alias * ALIAS_HZ
    if abs(epoch) <= sample_rate * 0.2e-6 and abs(residual) <= 1000:
        outcome = "aliased" if alias else "literal"
    else:
        outcome = "different"
    return dict(outcome=outcome, epoch_samples=epoch, cfo_hz=difference, alias_steps=alias)


def measure(fast, original):
    selective_capture.same_support(fast, original)
    source = fast["source"]
    chosen, n_visits = audit_schedule(source["probes"], source["input_manifest_sha256"])
    exact = dict(chosen)
    counts, witness = defaultdict(Counter), []
    full = Counter()
    for visit, rows in selective_capture.visit_pairs(original["source"]["probes"]):
        rf = int(rows[0]["actual_rf_hz"])
        if not rf or rf != rows[0]["actual_rf_hz"] or rf != rows[1]["actual_rf_hz"]:
            raise ValueError("expected a common physical RF per stereo visit")
        full[rf] += 1
        if visit in exact:
            for rx, (a, b) in enumerate(zip(rows, exact.pop(visit), strict=True)):
                item = signal(a, b, source["sample_rate_hz"])
                counts[rf][item["outcome"]] += 1
                witness.append(dict(visit=visit, rx=rx, rf_hz=rf, **item))
    if exact or sum(full.values()) != n_visits:
        raise ValueError("audit schedule does not account for the exact full capture")
    total = sum(counts.values(), Counter())
    positive = len(witness) - total["neither"]
    return witness, dict(
        manifest=source["input_manifest_sha256"],
        valid_visits=n_visits,
        audit_visits=[visit for visit, _ in chosen],
        full_rf=full,
        sampled_rf=dict(counts),
        union=positive,
        counts=total,
        disagreement=1 - total["literal"] / positive if positive else 1.0,
    )


def requires_original(fast, original):
    if any(r["status"] in POSITION_FAILURES for r in (fast, original)):
        return True
    for arm in ARMS:
        a, b = [coordinate(r.get("arms", {}).get(arm, {}).get("latlon")) for r in (fast, original)]
        if (a is None) != (b is None) or (a is not None and distance_km(a, b) > 0.5):
            return True
    return False


def threshold(development):
    """Largest threshold that covers all declared development discordance labels."""
    return min((score for score, target in development if target), default=2.0)


def bind_control(row, case, source, digest):
    if any(row.get(k) != v for k, v in case.items()):
        raise ValueError(f"{row['id']} compact control changes the raw/request/catalogue binding")
    if row.get("native_sha256") != digest:
        raise ValueError(f"{row['id']} compact control changes detector input bytes for {source}")
    validate_result(row["result"])
    if row["result"]["status"] in ("ok", "withheld") and set(row["result"]["arms"]) != set(ARMS):
        raise ValueError("completed control needs both calibration arms")
    return dict(row, condition=source)


def development_rows(path, method):
    with gzip.open(path, "rb") as stream:
        for line in stream:
            if not any(f'"id":"{ident}"'.encode() in line for ident in DEVELOPMENT):
                continue
            row = json.loads(line)
            if row["method"] == method and row["id"] in DEVELOPMENT:
                yield row


def reused(pins, release, *, development_only=False):
    endpoint_path = whole_iq.checked(two_rate.REPORT / "prediction-lock.json", pins["two_rate"])
    lock = whole_iq.read(endpoint_path)
    plan = whole_iq.read(fixed.member(two_rate.REPORT, lock, "source-lock.json"))
    if any(plan[k] != v for k, v in release.items()):
        raise ValueError("paired archive ran a different installed compact release")
    path = fixed.member(two_rate.REPORT, lock, "positions.jsonl.gz")
    method = "two_rate_original"
    if development_only:
        return fixed.select(development_rows(path, method), method, DEVELOPMENT)
    return fixed.select(rows_from(path), method, lock["cases"])


def stage(work):
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the experiment source is already locked")
    groups, archives, bindings, extensions, release = roster.inventory()
    work.mkdir(parents=True, exist_ok=False)
    source_names = (REPORT / "PROTOCOL.md", Path(__file__))
    pins = dict(
        two_rate=_sha(two_rate.REPORT / "prediction-lock.json"),
        stock=_sha(fixed.REPORT / "all-figure-lock.json"),
        fresh=_sha(roster.FRESH / "prediction-lock.json"),
        roster=roster.ROSTER_SHA,
    )
    known = whole_iq.read(two_rate.REPORT / "prediction-lock.json")["cases"]
    jobs, evidence = [], {}
    for ident in groups["all"]:
        case, request, body, fast, original, _ = two_rate.bind(
            ident, archives, bindings, extensions
        )
        rows, value = measure(fast, original)
        path = REPORT / "audit" / f"{ident}.jsonl.gz"
        pack(path, rows)
        value.update(
            witness_sha256=_sha(path),
            fast_native_sha256=archives[ident]["native_sha256"],
            causal_snapshots=request["causal_snapshots"],
            **bindings[ident],
        )
        evidence[ident] = value
        if ident not in known:
            jobs.append(
                two_rate.prepare(
                    work,
                    ident,
                    case,
                    request,
                    body,
                    bindings[ident],
                    release,
                    "original",
                    cpu=CPUS[len(jobs) % len(CPUS)],
                )
            )
        print(ident, value["disagreement"], len(value["audit_visits"]), flush=True)
    if not set(DEVELOPMENT) <= set(known) or len({r["manifest"] for r in evidence.values()}) != 22:
        raise ValueError("the two development controls or distinct 22-recording roster changed")
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases=evidence,
            development=DEVELOPMENT,
            jobs=jobs,
            pins=pins,
            release=release,
            protocol_sha256=_sha(source_names[0]),
            program_sha256=_sha(source_names[1]),
            fit_limit_s=compact.LIMIT,
            cpus=CPUS,
            stock_groups=groups,
        ),
    )
    save_json(work / "source-lock.json", dict(sha256=_sha(REPORT / "source-lock.json")))


def controls(source, *, development_only=False):
    pins, release = source["pins"], source["release"]
    receipt = whole_iq.read(whole_iq.checked(fixed.REPORT / "all-figure-lock.json", pins["stock"]))
    whole_iq.checked(roster.FRESH / "prediction-lock.json", pins["fresh"])
    if development_only:
        path = fixed.member(fixed.REPORT, receipt, "all-positions.jsonl.gz")
        fast = fixed.select(development_rows(path, fixed.FOUR), fixed.FOUR, DEVELOPMENT)
    else:
        fast = stock.released_stock(source["stock_groups"])
    original = reused(pins, release, development_only=development_only)
    for method, archive, key in (
        ("fast", fast, "fast_native_sha256"),
        ("original", original, "paired_capture_sha256"),
    ):
        for ident, row in archive.items():
            evidence = source["cases"][ident]
            bound = {k: evidence[k] for k in fixed.BINDINGS}
            archive[ident] = bind_control(row, bound, method, evidence[key])
    return fast, original


def lock_routes(source):
    fast, original = controls(source, development_only=True)
    cases = source["cases"]
    development = {
        ident: dict(
            disagreement=cases[ident]["disagreement"],
            target=requires_original(fast[ident]["result"], original[ident]["result"]),
        )
        for ident in DEVELOPMENT
    }
    cut = threshold((row["disagreement"], row["target"]) for row in development.values())
    held = sorted(cases.keys() - set(DEVELOPMENT))
    decision = {ident: evidence["disagreement"] >= cut for ident, evidence in cases.items()}
    order = sorted(held, key=lambda ident: digest("random-escalation", cases[ident]["manifest"]))
    randomized = set(order[: sum(decision[ident] for ident in held)])
    save_json(
        REPORT / "route-lock.json",
        dict(
            threshold=cut,
            development=development,
            holdout=held,
            escalation=decision,
            random_escalation=sorted(randomized),
            source_sha256=_sha(REPORT / "source-lock.json"),
        ),
    )


def run(work):
    seal = REPORT / "source-lock.json"
    whole_iq.checked(seal, whole_iq.read(work / "source-lock.json")["sha256"])
    source = whole_iq.read(seal)
    whole_iq.checked(Path(__file__), source["program_sha256"])
    whole_iq.checked(REPORT / "PROTOCOL.md", source["protocol_sha256"])
    roster.check_release(source["release"])
    lock_routes(source)

    def lane(cpu):
        for row in source["jobs"]:
            if row["cpu"] == cpu:
                compact.service(work, row)

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        list(pool.map(lane, CPUS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--work", required=True, type=local_output)
    args = parser.parse_args()
    {"stage": stage, "run": run}[args.action](args.work)


if __name__ == "__main__":
    main()
