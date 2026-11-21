"""Audit matched captures and reduce nominal and full physical-band search evidence."""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from .full_v5_check import _sha
from .reverse_glrt_reference import REPORT
from .reverse_glrt_report import analyze_orbits, expanded, literal, read, write_csv
from .reverse_glrt_search import distances, key
from .timing_first_roster import OUT
from .timing_first_trial import inventories
from .timing_first_wide_reference import PANELS

OLD = ("development", "heldout", "replication", "quarter_holdout")
FRESH = ("fresh_ds26", "fresh_ds29")
DETECTORS = ("original", "nominal", "physical")


def tab(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def verdict(p, target):
    if target is None:
        return "unresolved_return" if p else "unresolved_withheld"
    if p is None:
        return "withheld"
    return "match" if literal(p, target) else "different_peak"


def nominal(out):
    probes = []
    processed = set()
    tables = {}
    parity = []
    for cohort, folder in inventories(out).items():
        f = folder / "roster.json"
        if _sha(f) != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("nominal inventory changed")
        for row in read(f):
            name = key(row)
            if (row["case"], row["visit"]) in processed:
                raise ValueError("two entries for a physical stereo visit")
            processed.add((row["case"], row["visit"]))
            source = folder / "measurements" / (name + ".json")
            raw = read(source)
            path = out / "receiver" / (name + ".json")
            trial = read(path)
            stand = read(out / "standalone" / (name + ".json"))
            if (
                raw["signed_iq"] != trial["iq"]
                or raw["signed_iq"] != stand["iq"]
                or raw["row_id"] != row["id"]
                or trial["id"] != row["id"]
                or raw["grid_sha256"] != _sha(folder / "grids" / (name + ".npz"))
                or stand["prototype_file_sha256"] != _sha(path)
                or stand["null_iq"] != trial["null_iq"]
            ):
                raise ValueError("nominal trial inputs disagree")
            ref = raw["blind"]
            target = ref["even"] if ref["replicated"] else None
            tables[name] = dict(row=row, trial=trial, stand=stand, blind=target)
            for mode in DETECTORS:
                final = stand["methods"]["real"][mode]
                lane = final["lanes"][row["rx"]]
                win = lane["winner"]
                frozen = trial["methods"]["real"][mode]["lanes"][row["rx"]]["winner"]
                if mode == "original" and (
                    bool(win) != bool(frozen) or (win and not literal(win, frozen))
                ):
                    raise ValueError("original replay changed")
                null_result = (trial if mode == "original" else stand)["methods"]["null"][mode]
                nullwin = null_result["lanes"][row["rx"]]["winner"]
                de, df = distances(win, target) if win and target else (None, None)
                probes.append(
                    dict(
                        key=name,
                        id=row["id"],
                        case=row["case"],
                        visit=row["visit"],
                        rx=row["rx"],
                        channel=row["channel"],
                        edge=row["edge"],
                        counter=row["counter"],
                        cohort=cohort,
                        selection=row.get(
                            "selection", "stratified" if cohort in OLD else "reverse"
                        ),
                        stratum=row["stratum"],
                        iq=trial["iq"],
                        null_iq=trial["null_iq"],
                        method=mode,
                        reference_hz=target["hz"] if target else None,
                        reference_epoch=target["epoch"] if target else None,
                        strongest_repeated=bool(target),
                        wrong_code_repeated=literal(
                            raw["wrong_blind"]["even"], raw["wrong_blind"]["odd"]
                        ),
                        returned=bool(win),
                        reported_hz=win["hz"] if win else None,
                        reported_epoch=win["epoch"] if win else None,
                        confirmation=win.get("confirmation") if win else None,
                        null_return=bool(nullwin),
                        outcome=verdict(win, target),
                        delta_hz=df,
                        delta_samples=de,
                        mono_cpu_ms=1e3 * lane["cpu_s"],
                        mono_wall_ms=1e3 * lane["wall_s"],
                        stereo_cpu_ms=1e3 * final["cpu_s"],
                        stereo_wall_ms=1e3 * final["wall_s"],
                        original_lane_cpu_ms=1e3
                        * stand["methods"]["real"]["original"]["lanes"][row["rx"]]["cpu_s"],
                    )
                )
            for kind in ("real", "null"):
                for mode in ("nominal", "physical"):
                    for i, lane in enumerate(stand["methods"][kind][mode]["lanes"]):
                        parity.append(
                            dict(key=name, kind=kind, mode=mode, rx=i, **lane["against_prototype"])
                        )
    if len(processed) != 389:
        raise ValueError("incomplete prospective capture set")
    write_csv(out / "probes.csv", probes)
    write_csv(out / "standalone-parity.csv", parity)
    groups = {
        name: [r for r in probes if r["cohort"] == name] for name in (*OLD, *FRESH, "recovery")
    }
    groups["earlier_200"] = [r for r in probes if r["cohort"] in OLD]
    groups["earlier_replication_150"] = [
        r for r in groups["earlier_200"] if r["cohort"] != "development"
    ]
    groups["fresh_160"] = [r for r in probes if r["cohort"] in FRESH]
    groups["all_360"] = groups["earlier_200"] + groups["fresh_160"]
    for cohort in (*FRESH, "fresh_160"):
        for selection in ("uniform", "stratified"):
            groups[cohort + "_" + selection] = [
                r for r in groups[cohort] if r["selection"] == selection
            ]
    compare = []
    for name, rows in groups.items():
        baseline = {r["key"]: r["outcome"] for r in rows if r["method"] == "original"}
        for mode in DETECTORS:
            select = [r for r in rows if r["method"] == mode]
            counts = Counter(r["outcome"] for r in select)
            gains = sum(r["outcome"] == "match" and baseline[r["key"]] != "match" for r in select)
            lost = sum(r["outcome"] != "match" and baseline[r["key"]] == "match" for r in select)
            ci = binomtest(sum(r["null_return"] for r in select), len(select)).proportion_ci()
            compare.append(
                dict(
                    group=name,
                    method=mode,
                    visits=len(select),
                    references=sum(r["strongest_repeated"] for r in select),
                    matches=counts["match"],
                    different_peak=counts["different_peak"],
                    withheld_on_reference=counts["withheld"],
                    unresolved_returns=counts["unresolved_return"],
                    returns=sum(r["returned"] for r in select),
                    null_returns=sum(r["null_return"] for r in select),
                    null_ci_low=ci.low,
                    null_ci_high=ci.high,
                    paired_gains=gains,
                    paired_losses=lost,
                    median_paired_cpu_fraction=float(
                        np.median([r["mono_cpu_ms"] / r["original_lane_cpu_ms"] for r in select])
                    ),
                    **{
                        metric + "_" + q: float(
                            np.percentile([r[metric] for r in select], percentile)
                        )
                        for metric in (
                            "mono_cpu_ms",
                            "mono_wall_ms",
                            "stereo_cpu_ms",
                            "stereo_wall_ms",
                        )
                        for q, percentile in (("p50", 50), ("p95", 95))
                    },
                    stereo_wall_within_20ms=sum(r["stereo_wall_ms"] <= 20 for r in select),
                )
            )
    write_csv(out / "comparison.csv", compare)
    reverse = []
    for r in tab(REPORT / "strict-misses.csv"):
        t = tables[r["key"]]
        if r["iq"] != t["stand"]["iq"] or r["physical_id"] != t["row"]["id"]:
            raise ValueError("strict backward reference differs from raw probe")
        target = dict(hz=float(r["confirmed_hz"]), epoch=float(r["confirmed_epoch_samples"]))
        for mode in DETECTORS:
            win = t["stand"]["methods"]["real"][mode]["lanes"][int(r["rx"])]["winner"]
            de, df = distances(win, target) if win else (None, None)
            reverse.append(
                dict(
                    key=r["key"],
                    norad=r["norad_first_both_arms"],
                    iq=r["iq"],
                    method=mode,
                    target_hz=target["hz"],
                    target_epoch=target["epoch"],
                    winner_hz=win["hz"] if win else None,
                    winner_epoch=win["epoch"] if win else None,
                    delta_hz=df,
                    delta_samples=de,
                    orbit_target_outcome=verdict(win, target),
                    blind_reference_hz=t["blind"]["hz"] if t["blind"] else None,
                    strongest_waveform_outcome=verdict(win, t["blind"]),
                )
            )
    write_csv(out / "strict-recoveries.csv", reverse)
    receipt = read(out / "injection-receipt.json")
    if receipt["table"] != _sha(out / "injections.csv"):
        raise ValueError("planted waveform table changed")
    planted = defaultdict(list)
    for r in tab(out / "injections.csv"):
        planted[r["mode"], r["supported_band"], r["snr_db"], r["short_burst"]].append(r)
    grouped = []
    for (mode, band, snr, short), items in sorted(planted.items()):
        grouped.append(
            dict(
                method=mode,
                supported_band=band,
                snr_db=float(snr),
                short_burst=short,
                inputs=len(items),
                matched=sum(r["match"] == "True" for r in items),
                returned=sum(r["returned"] == "True" for r in items),
            )
        )
    write_csv(out / "injection-summary.csv", grouped)
    print(
        "verified real and phase-null records",
        len(processed),
        "standalone comparisons",
        len(parity),
    )


def stable(region):
    peak = region["peaks"][0]
    return bool(
        region["official"]["gate"]
        and literal(region["even"], region["odd"])
        and literal(peak, region["even"])
        and literal(peak, region["official"])
    )


def wide(out):
    wdir = out / "physical-reference"
    bank = read(REPORT / "complete-associations/orbit-summary.json.gz")
    probe_results = []
    alias_results = []
    unique_inputs = set()
    total_surfaces = 0
    for panel in PANELS:
        folder = REPORT / panel
        roster = read(folder / "roster.json")
        if _sha(folder / "roster.json") != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("wrong wide inventory")
        cover, aliases = expanded(folder)
        lookup = {r["key"]: r for r in cover}
        by_name = defaultdict(dict)
        for a in aliases:
            by_name[a["key"]][a["arm"], a["component"], a["norad"], a["alias"]] = a
        if len(lookup) != len(roster):
            raise ValueError(
                f"original-statistic search incomplete for {panel or 'initial'} "
                f"({len(lookup)}/{len(roster)})"
            )
        for row in roster:
            name = key(row)
            if name in unique_inputs:
                raise ValueError("wide input repeated")
            unique_inputs.add(name)
            normal = read(folder / "measurements" / (name + ".json"))
            raw = read(wdir / "measurements" / (name + ".json"))
            stock = read(folder / "stock" / (name + ".json"))
            receiver = read(out / "standalone" / (name + ".json"))
            if (
                len({normal["signed_iq"], raw["signed_iq"], stock["signed_iq"], receiver["iq"]})
                != 1
                or raw["reused_grid_sha256"] != normal["grid_sha256"]
                or raw["row_id"] != row["id"]
                or raw["grid_sha256"] != _sha(wdir / "grids" / (name + ".npz"))
                or raw["bounds"] != stock["interval_hz"]
                or stock["scope"] != "analog"
                or raw["frequency_counts"] != [1313, 3900, 5213]
                or stock["integer_epochs"] != 13333
                or stock["residual_bins"] != 512
            ):
                raise ValueError("full-band reference bound, input or grid changed")
            for c in stock["centers"]:
                if _sha(Path(c["surface"])) != c["sha256"]:
                    raise ValueError("original-statistic surface changed")
                total_surfaces += 1
            stable_regions = [
                c["regions"]["band"]["official"]
                for c in stock["centers"]
                if stable(c["regions"]["band"])
            ]
            first = raw["blind"]["even"] if raw["blind"]["replicated"] else None
            before = normal["blind"]["even"] if normal["blind"]["replicated"] else None
            peaks = sorted(stable_regions, key=lambda p: -p["margin"])
            strongest = peaks[0] if peaks else None
            data = dict(
                key=name,
                case=row["case"],
                visit=row["visit"],
                rx=row["rx"],
                sample_counter=row["counter"],
                channel=row["channel"],
                edge=row["edge"],
                panel=panel or "initial",
                role=row["stratum"],
                iq=raw["signed_iq"],
                grid_sha256=raw["grid_sha256"],
                stock_record_sha256=_sha(folder / "stock" / (name + ".json")),
                physical_direct_hz=first["hz"] if first else None,
                physical_direct_epoch=first["epoch"] if first else None,
                physical_direct_repeat=bool(first),
                nominal_repeat=bool(before),
                nominal_direct_hz=before["hz"] if before else None,
                nominal_epoch=before["epoch"] if before else None,
                same_nominal_and_wide=literal(first, before) if first and before else None,
                full_band_winner_outside_nominal=abs(first["hz"]) > 800000 if first else None,
                wrong_pilot_repeated=literal(raw["wrong_blind"]["even"], raw["wrong_blind"]["odd"]),
                stock_strongest_stable_fractional_hz=strongest["hz"] if strongest else None,
                stock_strongest_stable_fractional_epoch=strongest["epoch"] if strongest else None,
                direct_matches_any_stable_stock_tile=any(literal(first, p) for p in peaks)
                if first
                else None,
                direct_matches_best_stable_stock_tile=literal(first, strongest) if first else None,
                **{k: v for k, v in lookup[name].items() if k != "key"},
            )
            positive = {}
            for a in analyze_orbits(raw, row, bank):
                k = a["calibration"], a["component"], a["norad"], a["alias"]
                old = by_name[name].get(k, {})
                p = dict(epoch=a["epoch"], hz=a["frequency_hz"])
                q = dict(epoch=old.get("fractional_epoch"), hz=old.get("fractional_hz"))
                matched = bool(a["agrees"] and old.get("stock_split_agrees") and literal(p, q))
                if matched:
                    positive[k] = p
                alias_results.append(
                    dict(
                        **a,
                        stock_split_agrees=old.get("stock_split_agrees"),
                        stock_fractional_hz=q["hz"],
                        stock_fractional_epoch=q["epoch"],
                        both_objectives_same_peak=matched,
                        named_first_both_catalogues=a["causal_named_rank"] == 1
                        and a["later_named_rank"] == 1,
                    )
                )
            accepted = [p for k, p in positive.items() if k[0] == "fitted_c"]
            data["joint_orbit_frequency_count_fitted"] = len(distinct(accepted))
            data["joint_orbit_frequency_count_c0"] = len(
                distinct([p for k, p in positive.items() if k[0] == "c0"])
            )
            data["joint_orbit_outside_nominal_fitted"] = sum(
                abs(p["hz"]) > 800000 for p in distinct(accepted)
            )
            data["strongest_direct_is_orbit_compatible"] = (
                any(literal(first, p) for p in accepted) if first else None
            )
            data["joint_orbit_norads_fitted"] = " ".join(
                map(str, sorted({k[2] for k in positive if k[0] == "fitted_c"}))
            )
            data["joint_orbit_norads_c0"] = " ".join(
                map(str, sorted({k[2] for k in positive if k[0] == "c0"}))
            )
            for method in DETECTORS:
                detected = receiver["methods"]["real"][method]["lanes"][row["rx"]]["winner"]
                data[method + "_on_physical_winner"] = verdict(detected, first)
            probe_results.append(data)
    if len(probe_results) != 200:
        raise ValueError("full physical-band benchmark must include all 200 planned probes")
    write_csv(out / "wide-reference.csv", probe_results)
    write_csv(out / "wide-orbit-candidates.csv", alias_results)
    print(
        "verified original GLRT surfaces",
        total_surfaces,
        "on",
        len(probe_results),
        "real probes and",
        len(alias_results),
        "direct orbit and alias comparisons",
    )


def distinct(peaks):
    result = []
    for p in peaks:
        if not any(literal(p, q) for q in result):
            result.append(p)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("nominal", "wide"))
    parser.add_argument("--report", type=Path, default=OUT)
    args = parser.parse_args()
    (nominal if args.action == "nominal" else wide)(args.report)
