"""Compare an alternating fifth timing search on reconstructed and full-IQ receiver runs."""

import csv
from itertools import product
from math import atan2, cos, degrees, sin
from statistics import median

import numpy as np

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import complete_detector_roster as fixed
from . import screening_figures
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

BASE = fixed.SCREEN / "receiver-choice"
REPORT = BASE / "staggered-benchmark"
FRESH = BASE / "fresh-panel"
RECONSTRUCTED = BASE / "staggered-reconstruction"
DIRECT = BASE / "staggered-whole"
OLD_PIN = "2bc3768d2c146adc402992f5bbb5714119c2be77ec1959fa6c16329bdebef73a"
FRESH_PIN = "3c242cadc057614759a17a66959ee2dd4cedd739392d65756c68d2df63ea3f18"
RECONSTRUCTION_PIN = "ed62f55f943367b018d7fa774a35f24b6dfe4c592bafde6b7295ee8428072501"
DIRECT_PIN = "9d5d14e31cfda8a2671d43a169fae056de8face7643d503993ce46a316b958d9"
MIXED = "staggered_fifth_lane"
METHODS = (fixed.FOUR, fixed.FIVE, MIXED)
LABELS = {
    fixed.FOUR: "Four timing regions",
    fixed.FIVE: "Five timing regions",
    MIXED: "Alternating fifth antenna",
}
COHORTS = {
    "all": "Alternating the fifth search on twenty-two roof recordings",
    "reconstructed": "Twenty staggered streams reconstructed from measured antenna outputs",
    "fresh": "Alternating the fifth search from saved I/Q on two new lower-edge recordings",
    "difficult": "Recordings where both fixed detectors missed the earlier 10% allowance",
}
FIXED_HITS = {
    (True, True): "both",
    (True, False): "four_only",
    (False, True): "five_only",
    (False, False): "neither",
}


def read_receipt(folder, name, digest=None):
    path = folder / name
    if digest is not None:
        whole_iq.checked(path, digest)
    return whole_iq.read(path)


def frozen_groups():
    earlier = read_receipt(fixed.REPORT, "all-figure-lock.json", OLD_PIN)
    fresh = read_receipt(FRESH, "source-lock.json", FRESH_PIN)["cases"]
    old = earlier["cases"]
    if len(set(old)) != 20 or len(old) != 20 or len(fresh) != 2 or set(old) & fresh.keys():
        raise ValueError("expected twenty earlier recordings and two disjoint new ones")
    with fixed.member(fixed.REPORT, earlier, "scores.csv").open(newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["method"] in (fixed.FOUR, fixed.FIVE)]
    missed = {ident: set() for ident in old}
    for r in rows:
        if r["status"] == "ok" and float(r["error_km"]) > 1.10 * float(r["baseline_km"]):
            missed[r["id"]].add((r["method"], r["arm"]))
    both = set(product((fixed.FOUR, fixed.FIVE), ARMS))
    return dict(
        all=sorted(set(old) | fresh.keys()),
        reconstructed=sorted(old),
        fresh=sorted(fresh),
        difficult=sorted(i for i, states in missed.items() if states == both),
    )


def prediction_rows(folder, name, filename, cases):
    receipt = read_receipt(folder, name)
    if len(receipt["cases"]) != len(cases) or set(receipt["cases"]) != set(cases):
        raise ValueError(f"{folder.name} changed the scheduled recording set")
    return rows_from(fixed.member(folder, receipt, filename))


def joined_panel(controls, source_methods, staggered, staggered_method, ids, boundary):
    by_method = {
        canonical: fixed.select(controls, original, ids)
        for canonical, original in zip(METHODS[:2], source_methods, strict=True)
    }
    by_method[MIXED] = fixed.select(staggered, staggered_method, ids)
    result = []
    for ident in ids:
        four, five, mixed = (by_method[m][ident] for m in METHODS)
        for row in (five, mixed):
            fixed.same_capture(four, row)
        if boundary == "reconstructed" and (
            mixed.get("stock_native_sha256") != four.get("native_sha256")
            or mixed.get("fifth_native_sha256") != five.get("native_sha256")
        ):
            raise ValueError(f"{ident} reconstruction used different source detector outputs")
        for method, row in zip(METHODS, (four, five, mixed), strict=True):
            kind = (
                "reconstructed antenna records"
                if method == MIXED and boundary == "reconstructed"
                else "full saved I/Q"
            )
            result.append(dict(row, method=method, acquisition_evidence=kind))
    return result


def load_rows(groups):
    recon_plan = read_receipt(RECONSTRUCTED, "plan.json", RECONSTRUCTION_PIN)
    direct_plan = read_receipt(DIRECT, "source-lock.json", DIRECT_PIN)
    if (
        recon_plan["parent_sha256"] != OLD_PIN
        or sorted(recon_plan["roster"]) != groups["reconstructed"]
        or sorted(direct_plan["cases"]) != groups["fresh"]
    ):
        raise ValueError("staggered receiver inputs differ from the frozen parents or schedule")
    earlier = prediction_rows(
        fixed.REPORT, "all-figure-lock.json", "all-positions.jsonl.gz", groups["reconstructed"]
    )
    recon = prediction_rows(
        RECONSTRUCTED, "prediction-lock.json", "positions.jsonl.gz", groups["reconstructed"]
    )
    fresh = prediction_rows(FRESH, "prediction-lock.json", "positions.jsonl.gz", groups["fresh"])
    direct = prediction_rows(DIRECT, "prediction-lock.json", "positions.jsonl.gz", groups["fresh"])
    old_rows = joined_panel(
        earlier,
        METHODS[:2],
        recon,
        "staggered_reconstruction",
        groups["reconstructed"],
        "reconstructed",
    )
    scheduled = {r["id"]: r for r in recon_plan["scheduled"]}
    for r in old_rows:
        if r["method"] == MIXED and r.get("native_sha256") != scheduled[r["id"]].get(
            "native_sha256"
        ):
            raise ValueError("solver used a different reconstructed antenna stream")
    new_rows = joined_panel(
        fresh,
        ("receiver_choice_four", "receiver_choice_five"),
        direct,
        "staggered_native_whole",
        groups["fresh"],
        "fresh",
    )
    plan = read_receipt(FRESH, "source-lock.json", FRESH_PIN)["cases"]
    for r in new_rows:
        case = plan[r["id"]]
        if [r[k] for k in fixed.BINDINGS] != [
            case[k] for k in ("capture_native_sha256", "request_sha256", "catalog_sha256", "tile")
        ]:
            raise ValueError(f"{r['id']} differs from its frozen lower-edge capture")
    return old_rows + new_rows


def fresh_references():
    authority, positions = [], []
    for folder in (fixed.REPORT, FRESH):
        receipt = read_receipt(folder, "all-figure-lock.json")
        authority.extend(
            whole_iq.read(fixed.member(folder, receipt, fixed.REFS["authority"]))["cases"]
        )
        positions.extend(rows_from(fixed.member(folder, receipt, fixed.REFS["predictions"])))
    return authority, positions


def parity_rows(rows, cases):
    receipt = read_receipt(DIRECT, "figure-lock.json")
    audit = whole_iq.read(fixed.member(DIRECT, receipt, "probe-parity.json"))
    if (
        audit["prediction_sha256"] != _sha(DIRECT / "prediction-lock.json")
        or audit["raw_parent_sha256"] != _sha(FRESH / "raw-prediction-lock.json")
        or set(audit["cases"]) != set(cases)
    ):
        raise ValueError("antenna comparisons differ from the measured detector streams")
    inputs = {(r["id"], r["method"]): r.get("native_sha256") for r in rows}
    result = []
    for ident in cases:
        d = audit["cases"][ident]
        expected = {
            "control": inputs[ident, fixed.FOUR],
            "candidate": inputs[ident, fixed.FIVE],
            "staggered": inputs[ident, MIXED],
        }
        if (d["status"] != "incomplete" or "native_sha256" in d) and d.get(
            "native_sha256"
        ) != expected:
            raise ValueError(
                f"per-antenna proof used different complete native outputs for {ident}"
            )
        counts = d.get("per_role_lane", {})
        matched = sum(n for c in counts.values() for k, n in c.items() if k.endswith("_matched"))
        missed = sum(n for c in counts.values() for k, n in c.items() if k.endswith("_mismatched"))
        if d["status"] == "exact" and (not matched or missed or matched != 2 * d["valid"]):
            raise ValueError(
                f"exact proof must cover both antennas of every valid visit for {ident}"
            )
        result.append(
            dict(
                id=ident,
                status=d["status"],
                valid_visits=d.get("valid"),
                matched_antennas=matched if counts else None,
                differing_antennas=missed if counts else None,
                reason=d.get("reason"),
                **{f"{k}_native_sha256": v for k, v in expected.items()},
            )
        )
    return result


def export_references(out, key, cases, authority, positions):
    local = [r for r in authority if r["id"] in cases]
    if not local:
        return {}, {}
    spec = dict(authority=f"{key}-roof.json", predictions=f"{key}-v5.jsonl.gz")
    save_json(out / spec["authority"], dict(cases=local))
    pack(out / spec["predictions"], [r for r in positions if r["id"] in cases])
    receipt = dict(files={p: _sha(out / p) for p in spec.values()})
    return spec, screening_figures.new_roof_references(out, receipt, spec, [r["id"] for r in local])


def comparison(scores, groups):
    summary, counts, pairs = [], [], []
    for cohort, ids in groups.items():
        for arm in ARMS:
            rows = [r for r in scores if r["id"] in ids and r["arm"] == arm]
            summary.extend(fixed.summary_row(rows, ids, cohort, arm, m) for m in (*ROLES, *METHODS))
            keyed = {(r["id"], r["method"]): r for r in rows}
            for pct, flag in ((5, "within_5pct"), (10, "within_10pct")):
                cats = dict(both=0, four_only=0, five_only=0, neither=0, no_reference=0)
                gained = lost = mixed_count = 0
                for ident in ids:
                    four, five, mixed = (keyed[ident, m] for m in METHODS)
                    avail = four["baseline_km"] is not None
                    a, b, c = (r[flag] for r in (four, five, mixed))
                    category = FIXED_HITS[a, b] if avail else "no_reference"
                    cats[category] += 1
                    mixed_count += c
                    gained += c and not (a or b)
                    lost += (a or b) and not c
                    pairs.append(
                        dict(
                            cohort=cohort,
                            arm=arm,
                            tolerance_pct=pct,
                            id=ident,
                            baseline_km=four["baseline_km"],
                            four_km=four["error_km"],
                            five_km=five["error_km"],
                            staggered_km=mixed["error_km"],
                            fixed_result=category,
                            staggered_status=mixed["status"],
                            staggered_meets_allowance=c,
                        )
                    )
                counts.append(
                    dict(
                        cohort=cohort,
                        arm=arm,
                        tolerance_pct=pct,
                        scheduled=len(ids),
                        **cats,
                        best_possible_fixed=cats["both"] + cats["four_only"] + cats["five_only"],
                        staggered=mixed_count,
                        beyond_fixed=gained,
                        lost_from_fixed=lost,
                    )
                )
    return summary, counts, pairs


def calibration_effects(scores, groups, methods=METHODS):
    by_key = {(r["id"], r["method"], r["arm"]): r for r in scores}
    effects = []
    for cohort, ids in groups.items():
        for method in methods:
            row = dict(cohort=cohort, method=method, scheduled=len(ids))
            for field in ("error_km", "rf_rms_hz", "frequency_score"):
                diffs = []
                for ident in ids:
                    zero, fitted = (by_key[ident, method, a][field] for a in ARMS)
                    if zero is not None and fitted is not None:
                        diffs.append(fitted - zero)
                row[f"paired_{field}"] = len(diffs)
                row[f"median_fitted_minus_zero_{field}"] = median(diffs) if diffs else None
            effects.append(row)
    return effects


def segment_bound(first, second, truth):
    """Smallest surveyed error on the short spherical arc joining two published endpoints."""
    if first is None or second is None:
        return None, None
    a, b, target = (
        np.array([cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)])
        for lat, lon in np.radians([first, second, truth])
    )
    normal = np.cross(a, b)
    length = np.linalg.norm(normal)
    if length < 1e-12:
        return (distance_km(first, truth), 0.0) if a @ b > 0 else (None, None)
    arc = atan2(length, a @ b)
    tangent = np.cross(normal / length, a)
    closest = atan2(target @ tangent, target @ a)
    # atan2 can put the closest point outside the arc, including across its angular wrap.
    if not 0 < closest < arc:
        return min((distance_km(first, truth), 0.0), (distance_km(second, truth), 1.0))
    x, y, z = a * cos(closest) + tangent * sin(closest)
    endpoint = [degrees(atan2(z, np.hypot(x, y))), degrees(atan2(y, x))]
    return distance_km(endpoint, truth), closest / arc


def geographic_bounds(rows, refs):
    keyed = {(r["id"], r["method"]): r for r in rows}
    data = []
    for ident, ref in sorted(refs.items()):
        for arm in ARMS:
            points = [
                keyed[ident, m]["result"].get("arms", {}).get(arm, {}).get("latlon")
                for m in METHODS[:2]
            ]
            error, fraction = segment_bound(*points, ref["truth"])
            baseline = ref["reference"]["baseline"][arm]["error_km"]
            data.append(
                dict(
                    id=ident,
                    arm=arm,
                    baseline_km=baseline,
                    closest_on_arc_km=error,
                    fraction_from_four_to_five=fraction,
                    arc_within_10pct=error <= 1.1 * baseline
                    if error is not None and baseline is not None
                    else None,
                )
            )
    return data


def timing_row(row, raw=None, fit=None, elapsed=None, calls=None, within=None, cores=None):
    if calls is not None and within is not None and not 0 <= within <= calls:
        raise ValueError("detector deadline count exceeds measured calls")
    if row["acquisition_evidence"] == "reconstructed antenna records" and any(
        v is not None for v in (raw, elapsed, calls, within)
    ):
        raise ValueError("a packet reconstruction cannot measure detector or full service clocks")
    return dict(
        id=row["id"],
        method=row["method"],
        acquisition_evidence=row["acquisition_evidence"],
        status=row["result"]["status"],
        native_sha256=row.get("native_sha256"),
        detection_and_assembly_s=raw,
        position_worker_s=fit,
        full_service_s=elapsed,
        complete_detector_calls=calls,
        wall_within_20ms=within,
        deadline_fraction=within / calls if within is not None and calls else None,
        cores=cores,
    )


def timing(rows, groups):
    keyed = {(r["id"], r["method"]): r for r in rows}
    out = []
    folder = fixed.BASE / "complete-timing"
    receipt = read_receipt(folder, "prediction-lock.json")
    with fixed.member(folder, receipt, "resources.csv").open(newline="") as f:
        stock_times = list(csv.DictReader(f))
    older = [r for r in rows if r["id"] in groups["reconstructed"] and r["method"] != MIXED]
    fixed.verify_timed_positions(older, stock_times)
    for t in stock_times:
        r = keyed[t["id"], t["method"]]
        span = (
            float(t["raw_s"]) + float(t["assembly_s"]) if t["raw_s"] and t["assembly_s"] else None
        )
        out.append(
            timing_row(
                r,
                span,
                float(t["position_s"]) if t["position_s"] else None,
                float(t["worker_s"]) if t["worker_s"] else None,
                int(t["detector_calls"]),
                int(t["detector_wall_within_20"]),
                t["cores"],
            )
        )
    for ident in groups["reconstructed"]:
        r = keyed[ident, MIXED]
        solver = r.get("position_resources") or {}
        out.append(timing_row(r, fit=solver.get("wall_s"), cores=r.get("cpu")))

    fresh_lock = read_receipt(FRESH, "prediction-lock.json")
    timed = whole_iq.read(fixed.member(FRESH, fresh_lock, "resources.json"))
    authority = whole_iq.read(fixed.member(FRESH, fresh_lock, "raw-authority.json"))
    direct_lock = read_receipt(DIRECT, "prediction-lock.json")
    direct_times = whole_iq.read(fixed.member(DIRECT, direct_lock, "resources.json"))
    plan = read_receipt(FRESH, "source-lock.json", FRESH_PIN)
    for ident in groups["fresh"]:
        for role, method in (("control", fixed.FOUR), ("candidate", fixed.FIVE)):
            r = keyed[ident, method]
            audit, t = authority[ident][role], timed[ident][role]
            if audit.get("native_sha256") != r.get("native_sha256") or any(
                audit.get(k) != t.get(k)
                for k in ("clock_sha256", "excluded_sha256", "probes_sha256")
            ):
                raise ValueError(f"{ident} timing and detector payload disagree")
            span = (
                t["raw_s"] + t["assembly_s"]
                if t.get("raw_s") is not None and t.get("assembly_s") is not None
                else None
            )
            out.append(
                timing_row(
                    r,
                    span,
                    t.get("position_s"),
                    t.get("wall_s"),
                    t.get("dual_calls"),
                    t.get("within_20ms"),
                    plan["cases"][ident]["cpus"],
                )
            )
        r = keyed[ident, MIXED]
        t = direct_times[ident]
        if t["id"] != ident or t["position_status"] != r["result"]["status"]:
            raise ValueError(f"{ident} mixed timing and terminal position disagree")
        out.append(
            timing_row(
                r,
                t.get("raw_wall_s"),
                t.get("position_wall_s"),
                t.get("pipeline_wall_s"),
                t.get("native_calls"),
                t.get("decoded_within_20ms"),
                t["detector_cores"],
            )
        )
    if len(out) != len(keyed) or {(r["id"], r["method"]) for r in out} != set(keyed):
        raise ValueError("times must represent every scheduled method and recording exactly once")
    return sorted(out, key=lambda r: (r["id"], METHODS.index(r["method"])))


def render_panels(out, rows, groups, references, positions, *, prefix, panels, series, provenance):
    descriptors = []
    for key, ids in groups.items():
        source = f"{key}-positions.jsonl.gz"
        pack(out / source, [r for r in rows if r["id"] in ids])
        extra, _ = export_references(out, key, ids, references, positions)
        files = [source, *provenance, *extra.values()]
        seal = f"{key}-figure-lock.json"
        save_json(out / seal, dict(cases=ids, files={p: _sha(out / p) for p in files}))
        title, caption = panels[key]
        spec = dict(
            id=f"{prefix}-{key}",
            method=series[0][1],
            title=title,
            caption=caption,
            scope="roof",
            cases="sealed",
            seal=seal,
            provenance=provenance,
            series=[
                dict(
                    key=s,
                    file=source,
                    value=m,
                    label=label,
                    native_field=fixed.BINDINGS[0],
                    match=list(fixed.BINDINGS),
                )
                for s, m, label in series
            ],
        )
        if extra:
            spec["roof_references"] = extra
        descriptors.append(spec)
    save_json(out / "figures.json", dict(version=2, charts=descriptors))
    screening_figures.generate(out / "charts", evidence=out)


def render(out, rows, groups, references, positions):
    captions = {
        "fresh": "Two new lower-edge recordings from saved I/Q through position.",
        "difficult": "Selected on earlier fixed errors. Staggered uses recorded antenna rows.",
        "reconstructed": "New positions use reconstructed streams of measured antenna records.",
        "all": "Staggered uses recorded antenna outputs on twenty cases and raw I/Q on two.",
    }
    render_panels(
        out,
        rows,
        groups,
        references,
        positions,
        prefix="staggered-benchmark",
        panels={key: (title, captions[key]) for key, title in COHORTS.items()},
        series=[
            (k, m, LABELS[m])
            for k, m in (("one", MIXED), ("stock", fixed.FOUR), ("one_native_factors", fixed.FIVE))
        ],
        provenance=["inputs.json", "roster.json", "scores.csv", "summary.csv", "choice-counts.csv"],
    )


def run(out):
    groups = frozen_groups()
    schedule = dict(groups=groups, protocol_sha256=_sha(REPORT / "PROTOCOL.md"))
    if whole_iq.read(REPORT / "roster.json") != schedule:
        raise ValueError("the registered staggered recording groups changed")
    rows = load_rows(groups)
    authority, originals = fresh_references()
    _, extra = export_references(out, "all", groups["all"], authority, originals)
    _, frozen = held_references(None, [i for i in groups["all"] if i not in extra])
    refs = {r["id"]: r for r in frozen} | extra
    scores = fixed.scored(rows, refs)
    boundaries = {(r["id"], r["method"]): r["acquisition_evidence"] for r in rows}
    for r in scores:
        r["acquisition_evidence"] = boundaries[r["id"], r["method"]]
    summary, counts, pairs = comparison(scores, groups)
    sources = (
        (fixed.REPORT, "all-figure-lock.json"),
        (fixed.BASE / "complete-timing", "prediction-lock.json"),
        (FRESH, "source-lock.json"),
        (FRESH, "all-figure-lock.json"),
        (FRESH, "prediction-lock.json"),
        (RECONSTRUCTED, "plan.json"),
        (RECONSTRUCTED, "prediction-lock.json"),
        (DIRECT, "source-lock.json"),
        (DIRECT, "prediction-lock.json"),
        (DIRECT, "figure-lock.json"),
    )
    save_json(
        out / "inputs.json",
        {
            str((folder / name).relative_to(fixed.SCREEN)): _sha(folder / name)
            for folder, name in sources
        },
    )
    save_json(out / "roster.json", schedule)
    for name, table in (
        ("scores", scores),
        ("summary", summary),
        ("choice-counts", counts),
        ("paired-errors", pairs),
        ("timing", timing(rows, groups)),
        ("direct-parity", parity_rows(rows, groups["fresh"])),
        ("calibration-effects", calibration_effects(scores, groups)),
        ("fixed-endpoint-geometry", geographic_bounds(rows, refs)),
    ):
        csv_file(out / f"{name}.csv", table)
    render(out, rows, groups, authority, originals)
    return summary


def show(summary, out):
    names = LABELS | dict(
        zip(
            ROLES,
            ("v5 no repair", "v5 selective gap", "v5 one omitted", "v5 two omitted"),
            strict=True,
        )
    )
    print(
        "Cohort          Calibration   Receiver                    Fixes   Within +10%  "
        "Median km    P95 km"
    )
    for r in summary:
        if r["cohort"] != "all" and r["method"] not in ("baseline", *METHODS):
            continue
        method = names[r["method"]]
        n = r["scheduled"]
        printed = [f"{r[k]:.3f}" if r[k] is not None else "—" for k in ("median_km", "p95_km")]
        print(
            f"{r['cohort']:15} {r['arm']:12} {method:24} {r['published']:2}/{n:<2}   "
            f"{r['within_10pct']:2}/{n:<2}     {printed[0]:>8}  {printed[1]:>8}"
        )
    with (out / "timing.csv").open(newline="") as stream:
        for r in csv.DictReader(stream):
            if r["method"] != MIXED or r["acquisition_evidence"] != "full saved I/Q":
                continue
            wall = f"{float(r['full_service_s']):.1f} s" if r["full_service_s"] else r["status"]
            on_time = r["wall_within_20ms"] or "—"
            calls = r["complete_detector_calls"] or "—"
            print(
                f"{r['id']}  Raw I/Q through position  {wall}  "
                f"{on_time}/{calls} detector calls within 20 ms"
            )
    print(f"Per-recording scores, fixed-policy limits, timing and charts in {out}")
