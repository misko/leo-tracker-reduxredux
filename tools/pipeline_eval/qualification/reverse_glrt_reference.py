"""Freeze published algo07v5 satellite predictions and native opportunities before reading I/Q."""

import argparse
import bisect
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .full_v5_check import BULK, _load_case, _sha

CASES = ("DS26-0020", "DS26-0036", "DS26-0066", "DS26-0162", "DS26-0237")
ARMS = ("c0", "fitted_c")
ALIAS = 1 / 4.4e-6
MAX_BRACKET_S = 8.0
REPORT = Path(__file__).resolve().parents[3] / "reports/2026_11_20_ds26_reverse_glrt"


def packed(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bound(locator):
    data = (BULK / locator["path"]).read_bytes()
    if digest(data) != locator["sha256"]:
        raise ValueError(f"changed archived input {locator['path']}")
    return json.loads(data)


def wrapped(delta):
    return (delta + ALIAS / 2) % ALIAS - ALIAS / 2


def brackets(series, at):
    """Interpolate emitted satellite predictions across two other native opportunities."""
    guesses = []
    for (sat, component), (times, points) in series.items():
        left = bisect.bisect_left(times, at) - 1
        right = bisect.bisect_right(times, at)
        if left < 0 or right == len(times):
            continue
        a, b = points[left], points[right]
        span = b["time_s"] - a["time_s"]
        if span > MAX_BRACKET_S:
            continue
        fraction = (at - a["time_s"]) / span
        step = wrapped(b["prediction_hz"] - a["prediction_hz"])
        if abs(step) > 8000 * span + 1000:
            continue
        guesses.append(
            dict(
                norad=sat,
                component=component,
                hz=a["prediction_hz"] + fraction * step,
                span_s=span,
                endpoints=[a["observation_id"], b["observation_id"]],
            )
        )
    return sorted(guesses, key=lambda g: (g["span_s"], g["norad"], g["component"]))


def index_predictions(worker):
    owners, curves = {}, {}
    for arm in ARMS:
        rows = worker["prediction_rows"][arm]
        owners[arm] = {p["observation_id"]: p for p in rows}
        if (
            len(owners[arm]) != len(rows)
            or {p["observation_id"]: p["norad"] for p in rows} != worker["arms"][arm]["owners"]
        ):
            raise ValueError("prediction IDs differ from final v5 ownership")
        grouped = defaultdict(lambda: defaultdict(list))
        for p in rows:
            grouped[p["receiver"] - 1, p["channel"]][p["norad"], p["component"]].append(p)
        curves[arm] = {}
        for lane, paths in grouped.items():
            curves[arm][lane] = {}
            for key, points in paths.items():
                points.sort(key=lambda p: p["time_s"])
                curves[arm][lane][key] = ([p["time_s"] for p in points], points)
    return owners, curves


def freeze_case(ident):
    case = _load_case(ident)
    request = read_bound(case["request"])
    folder = (BULK / case["request"]["path"]).parent
    worker = json.loads((folder / "worker-result.json").read_bytes())
    valid = json.loads((folder / "validated-archive.json").read_bytes())
    native = read_bound(case["native"])
    if not (
        valid["validated"]
        and worker["status"] == "complete"
        and worker["role"] == "baseline"
        and valid["worker_sha256"] == "sha256:" + digest(packed(worker))
        and valid["request_sha256"]
        == worker["request_sha256"]
        == "sha256:" + digest(packed(request))
        and valid["artifact"]["sha256"]
        == worker["artifact"]["sha256"]
        == "sha256:" + _sha(folder / "experimental-evidence.zip")
        and request["job"]["evaluation_reference"] is None
        and request["job"]["native_input"]["sha256"] == "sha256:" + case["native"]["sha256"]
        and native["provenance"]["run_id"] == case["run_id"]
        and native["source"]["session_id"] == case["session_id"]
    ):
        raise ValueError(f"unbound v5 publication for {ident}")
    owners, curves = index_predictions(worker)
    opportunities = []
    observed = set()
    for p in native["source"]["probes"]:
        rx, ch, counter = (p[k] for k in ("receiver_id", "channel", "valid_start_counter"))
        oid = "sha256:" + digest(f"{case['session_id']}:{rx}:{counter}".encode())
        if oid in observed:
            raise ValueError("duplicate native opportunity")
        observed.add(oid)
        t = (counter - native["clock_anchor"]["sample_counter"]) / 1e7 + 0.01
        accepted = [c for c in p["candidates"] if c["passed_fractional_margin_gate"]]
        win = max(
            accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None
        )
        label, alternatives = {}, {}
        for arm in ARMS:
            own = owners[arm].get(oid)
            if own and (
                not win
                or own["receiver"] != rx + 1
                or own["channel"] != ch
                or abs(own["time_s"] - t) > 1e-8
                or abs(own["measured_cfo_hz"] - win["fractional_tracking_cfo_hz"]) > 1e-5
            ):
                raise ValueError("v5 prediction disagrees with the native measurement")
            label[arm] = own
            alternatives[arm] = brackets(curves[arm].get((rx, ch), {}), t)
        status = "owned" if any(label.values()) else "gap" if any(alternatives.values()) else "open"
        opportunities.append(
            dict(
                case=ident,
                visit=p["visit_index"],
                rx=rx,
                channel=ch,
                edge=p["edge"],
                counter=counter,
                time_s=t,
                rf_hz=p["actual_rf_hz"],
                id=oid,
                stratum=status,
                old_pass=bool(win),
                incumbent=win,
                owners=label,
                brackets=alternatives,
            )
        )
    if any(set(owners[arm]) - observed for arm in ARMS):
        raise ValueError("published owner vanished from opportunity inventory")
    excluded = sorted(row["visit"] for row in native["provenance"]["excluded_windows"])
    visits = {p["visit"] for p in opportunities}
    if (
        len(opportunities) != 2 * len(visits)
        or visits.intersection(excluded)
        or len(visits) + len(excluded) != case["recording"]["window_count"]
    ):
        raise ValueError("incomplete native exposure accounting")
    disagreed = sum(
        (a := p["owners"]["c0"]) is not None
        and (b := p["owners"]["fitted_c"]) is not None
        and a["norad"] != b["norad"]
        for p in opportunities
    )
    summary = dict(
        case=ident,
        edge=opportunities[0]["edge"],
        session=case["session_id"],
        run=case["run_id"],
        native_sha256=case["native"]["sha256"],
        archive_sha256=valid["artifact"]["sha256"],
        worker_sha256=valid["worker_sha256"],
        request_sha256=valid["request_sha256"],
        anchor=native["clock_anchor"],
        cutoff_utc_ns=case["cutoff_utc_ns"],
        catalogue=case["catalog"],
        catalogue_available_utc_ns=case["catalog_timestamp_ns"],
        segments=case["recording"]["segments"],
        scheduled=case["recording"]["window_count"],
        valid_visits=len(visits),
        excluded_visits=excluded,
        counted_probes=dict(Counter(f"{r['stratum']}_{r['old_pass']}" for r in opportunities)),
        owner_disagreements=disagreed,
        arms={
            a: {
                k: v
                for k, v in worker["arms"][a].items()
                if k
                in (
                    "associated_points",
                    "satellites",
                    "tracks",
                    "residual_rms_hz",
                    "endpoint_latlon",
                )
            }
            for a in ARMS
        },
    )
    return summary, opportunities


def select(rows):
    """Each selection is made from archived metadata before any new waveform score."""
    chosen, used = [], set()
    for stratum, old_pass, count in (
        ("owned", True, 4),
        ("gap", False, 2),
        ("gap", True, 2),
        ("open", False, 1),
        ("open", True, 1),
    ):
        pool = [r for r in rows if (r["stratum"], r["old_pass"]) == (stratum, old_pass)]
        for slot in range(count):
            remaining = [r for r in pool if r["visit"] not in used]
            if not remaining:
                break

            def key(r, stratum=stratum, slot=slot):
                own = r["owners"]["fitted_c"] or r["owners"]["c0"] or {}
                role_cost = stratum == "owned" and (own.get("role") == "predictive") != (slot >= 2)
                return (
                    role_cost,
                    r["rx"] != slot % 2,
                    digest(packed(["ds26-reverse-v1", slot, r["id"]])),
                )

            item = min(remaining, key=key)
            chosen.append(item)
            used.add(item["visit"])
    return chosen


def freeze(out):
    out.mkdir(parents=True, exist_ok=True)
    cases, selected = [], []
    inventory = bytearray()
    for ident in CASES:
        summary, rows = freeze_case(ident)
        cases.append(summary)
        selected.extend(select(rows))
        for row in rows:
            inventory.extend(packed(row) + b"\n")
    contents = gzip.compress(bytes(inventory), compresslevel=5, mtime=0)
    (out / "opportunities.jsonl.gz").write_bytes(contents)
    (out / "roster.json").write_bytes(packed(selected) + b"\n")
    manifest = dict(
        cases=cases,
        opportunities_sha256=digest(contents),
        roster_sha256=_sha(out / "roster.json"),
        source_sha256=_sha(Path(__file__)),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print([(r["case"], r["counted_probes"]) for r in cases], "selected", len(selected), flush=True)


def reserve(source, out, other_roster=None):
    manifest = json.loads((source / "manifest.json").read_bytes())
    raw = (source / "opportunities.jsonl.gz").read_bytes()
    first = (source / "roster.json").read_bytes()
    if (
        digest(first) != manifest["roster_sha256"]
        or digest(raw) != manifest["opportunities_sha256"]
    ):
        raise ValueError("original reference inventory changed")
    used = {(r["case"], r["visit"]) for r in json.loads(first)}
    other_hash = None
    if other_roster:
        body = (other_roster / "roster.json").read_bytes()
        signed = json.loads((other_roster / "manifest.json").read_bytes())
        if digest(body) != signed["roster_sha256"] or signed["opportunities_sha256"] != digest(raw):
            raise ValueError("second exclusion roster has different provenance")
        used.update((r["case"], r["visit"]) for r in json.loads(body))
        other_hash = digest(body)
    available = defaultdict(list)
    for line in gzip.decompress(raw).splitlines():
        row = json.loads(line)
        if (row["case"], row["visit"]) not in used:
            available[row["case"]].append(row)
    second = [r for ident in CASES for r in select(available[ident])]
    out.mkdir(parents=True, exist_ok=True)
    data = packed(second) + b"\n"
    (out / "roster.json").write_bytes(data)
    (out / "manifest.json").write_bytes(
        packed(
            dict(
                cases=manifest["cases"],
                roster_sha256=digest(data),
                parent_roster_sha256=digest(first),
                other_excluded_roster_sha256=other_hash,
                opportunities_sha256=digest(raw),
                protocol_sha256=_sha(REPORT / "FOLLOWUP.md"),
                source_sha256=_sha(Path(__file__)),
            )
        )
        + b"\n"
    )
    print("reserved disjoint visits", len(second), flush=True)


def components(source, out):
    manifest = json.loads((source / "manifest.json").read_bytes())
    raw = (source / "opportunities.jsonl.gz").read_bytes()
    if digest(raw) != manifest["opportunities_sha256"]:
        raise ValueError("component roster and opportunity ledger differ")
    seen, selected = set(), []
    for line in gzip.decompress(raw).splitlines():
        row = json.loads(line)
        keys = {
            (row["case"], arm, own["norad"], own["component"])
            for arm, own in row["owners"].items()
            if own
        }
        if keys - seen:
            selected.append(row)
            seen.update(keys)
    out.mkdir(exist_ok=True, parents=True)
    data = packed(selected) + b"\n"
    (out / "roster.json").write_bytes(data)
    (out / "manifest.json").write_bytes(
        packed(
            dict(
                cases=manifest["cases"],
                roster_sha256=digest(data),
                opportunities_sha256=digest(raw),
                scope="every published component / NORAD / calibration arm pair",
                pairs=len(seen),
            )
        )
        + b"\n"
    )
    print("all published component and arm pairs", len(seen), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument("--reserve-from", type=Path)
    parser.add_argument("--also-exclude", type=Path)
    parser.add_argument("--components-from", type=Path)
    options = parser.parse_args()
    if options.components_from:
        components(options.components_from, options.out)
    elif options.reserve_from:
        reserve(options.reserve_from, options.out, options.also_exclude)
    else:
        freeze(options.out)
