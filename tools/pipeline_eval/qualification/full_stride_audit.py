"""Audit the complete-waveform coarse CFO stride comparison after prediction sealing."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from .. import iq_comparison_results as published
from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json
from ..iq_compare import BRANCHES
from ..scoring import ARMS, distribution
from . import scout_control_check as check
from .full_held_scores import held_references
from .full_v5_check import _sha

REPORT = check.SCREEN / "receiver-core/full-stride"
PRIMARY = check.ACQUISITION / "scout-full"
REPEAT = check.ACQUISITION / "deadline-repeat"
REPEAT_CASE = "DS29-0082"
REQUEST = (*check.INPUT_FIELDS, "paired_capture_sha256")
SUPPORT = (*check.NATIVE_FIELDS, "input_manifest_sha256", "probe_order_sha256")


def pending(work):
    """Avoid freezing a worker that has a live reserved service or a pending failure receipt."""
    lock = whole_iq.checked(
        work / "source-lock.json", (work / "source-lock.sha256").read_text().strip()
    )
    missing = []
    for ident in check.read(lock)["cases"]:
        for branch in BRANCHES:
            folder = work / ident / branch
            terminal = folder / "service.json"
            recorded_failure = (folder.parent / f"{branch}-failure.json").is_file()
            if terminal.is_file():
                completed = (
                    iq_service.succeeded(check.read(terminal)) and (folder / "end.json").is_file()
                )
            else:
                completed = recorded_failure and not (folder / "service-launch.json").exists()
            if not completed and not (terminal.is_file() and recorded_failure):
                missing.append(f"{ident}/{branch}")
    return missing


def archive(folder):
    seal, digest = check.sealed(folder)
    source = check.read(folder / "source-lock.json")
    resources = check.read(folder / "resources.json")
    if set(seal["cases"]) != set(source["cases"]) or set(seal["cases"]) != set(resources):
        raise ValueError("sealed positions, source plan and resources do not bind the same roster")
    return seal, digest, source, resources


def products(folder, seal, row, resource, branch, scratch=None):
    ident = row["id"]
    member = f"native/{branch}/{ident}.json.gz"
    expected = row.get("native_sha256")
    if (member in seal["files"]) != bool(expected):
        raise ValueError(f"{ident}/{branch} did not export all completed detector products")
    if not expected:
        return None
    # The same helper authenticates the native bytes against their factor digest and raw receipt.
    staged = scratch / ident / branch if scratch else folder
    if branch == "control":
        return check.control_signature(folder, seal, staged, row, resource)[0]
    native = gzip.decompress((folder / member).read_bytes())
    return check.native_signature(native, expected, [resource])


def prior_repeat(before, old_resource, repeat, repeat_resource):
    fields = (*check.NATIVE_FIELDS, "input_manifest_sha256", "detector_sha256", "dual_calls")
    if (
        before["result"]["status"] != "timed_out"
        or repeat["result"]["status"] != "ok"
        or not before.get("native_sha256")
        or before["native_sha256"] != repeat.get("native_sha256")
        or any(before[k] != repeat[k] for k in REQUEST)
        or any(old_resource[k] != repeat_resource[k] for k in fields)
    ):
        raise ValueError("deadline repeat must reference the complete native primary input")


def control_parity(ident, row, native, prior_row, prior_native, repeat=None):
    if any(row[k] != prior_row[k] for k in REQUEST):
        raise ValueError(f"{ident}: historical control has a different causal request or region")
    output = dict(
        state="compared",
        primary_native=prior_native,
        native_fields_exact=(
            {k: native[k] == value for k, value in prior_native.items()}
            if native is not None and prior_native is not None
            else None
        ),
        primary_position=check.endpoints(row["result"], prior_row["result"]),
        primary_position_arms_exact=(
            encoded(row["result"]["arms"]) == encoded(prior_row["result"]["arms"])
            if row["result"]["status"] == prior_row["result"]["status"] == "ok"
            else None
        ),
    )
    if repeat is not None:
        output.update(
            deadline_repeat_native_sha256=repeat["native_sha256"],
            deadline_repeat_position=check.endpoints(row["result"], repeat["result"]),
            deadline_repeat_position_arms_exact=(
                encoded(row["result"]["arms"]) == encoded(repeat["result"]["arms"])
                if row["result"]["status"] == "ok"
                else None
            ),
        )
    return output


def historic_counts(records):
    controls = [row["historical_control"] for row in records]
    compared = [old for old in controls if old["state"] == "compared"]
    return dict(
        no_prior_waveform_control=len(controls) - len(compared),
        primary_native=Counter(
            "missing"
            if old["native_fields_exact"] is None
            else "exact"
            if all(old["native_fields_exact"].values())
            else "different"
            for old in compared
        ),
        primary_position_arms=Counter(
            "missing"
            if old["primary_position_arms_exact"] is None
            else "exact"
            if old["primary_position_arms_exact"]
            else "different"
            for old in compared
        ),
        separate_deadline_repeat_position_arms_exact=next(
            old["deadline_repeat_position_arms_exact"]
            for old in compared
            if "deadline_repeat_position_arms_exact" in old
        ),
    )


def detector_stats(measurements):
    complete = [(ident, m) for ident, m in measurements if "dual_calls" in m]
    count = sum(m["dual_calls"] for _, m in complete)
    met = sum(m["within_20ms"] for _, m in complete)
    if any(not 0 <= m["within_20ms"] <= m["dual_calls"] for _, m in complete):
        raise ValueError("invalid complete detector deadline counts")
    cpu = sum(m["counts"]["detector_cpu_s"] for _, m in complete)
    return dict(
        complete_ids=[ident for ident, _ in complete],
        valid_dual_rx_calls=count,
        wall_at_most_20_ms=met,
        deadline_fraction=met / count if count else None,
        mean_detector_cpu_ms=cpu * 1000 / count if count else None,
        positives=sum(m["counts"]["positive_candidates"] for _, m in complete),
    )


def delta(pairs, key):
    values = [
        b[key] - a[key] for a, b in pairs if a.get(key) is not None and b.get(key) is not None
    ]
    return dict(**distribution(values), candidate_lower=sum(v < 0 for v in values))


def panel_cases(ids, positions, resources, scores):
    services = {}
    for branch in BRANCHES:
        measurements = [(ident, resources[ident][branch]) for ident in ids]
        statuses = (positions[branch][ident]["result"]["status"] for ident in ids)
        services[branch] = dict(
            detector=detector_stats(measurements),
            terminal_outcomes=Counter(statuses),
            service_success=sum(iq_service.succeeded(m["service"]) for _, m in measurements),
        )
    paired = [(resources[ident]["control"], resources[ident]["candidate"]) for ident in ids]
    fits = {}
    for arm in ARMS:
        series = {branch: [scores[ident, branch, arm] for ident in ids] for branch in BRANCHES}
        fits[arm] = {
            branch: dict(
                scheduled=len(ids),
                published=sum(row["published"] for row in rows),
                v5_comparable=sum(row["original_v5_km"] is not None for row in rows),
                within_5pct=sum(row["within_5pct"] is True for row in rows),
                within_10pct=sum(row["within_10pct"] is True for row in rows),
                **{
                    key: distribution([row[key] for row in rows if row[key] is not None])
                    for key in ("error_km", "conditional_rms_hz")
                },
            )
            for branch, rows in series.items()
        }
        same_ids = list(zip(*series.values(), strict=True))
        fits[arm]["candidate_minus_control"] = {
            key: delta(same_ids, key)
            for key in ("error_km", "conditional_rms_hz", "conditional_frequency_score")
        }
    return dict(
        recordings=ids,
        services=services,
        position=fits,
        candidate_minus_control_s={
            key: delta(paired, key) for key in ("wall_s", "cpu_s", "raw_s", "position_s")
        },
    )


def criterion(overall, additional):
    before, after = (overall["services"][b]["detector"] for b in BRANCHES)
    same_trials = (
        before["complete_ids"] == after["complete_ids"]
        and before["valid_dual_rx_calls"] == after["valid_dual_rx_calls"] > 0
    )
    deadline = same_trials and after["wall_at_most_20_ms"] > before["wall_at_most_20_ms"]
    retains = {
        panel: {
            arm: (
                summary["position"][arm]["candidate"]["within_10pct"]
                >= summary["position"][arm]["control"]["within_10pct"]
            )
            for arm in ARMS
        }
        for panel, summary in (("all", overall), ("additional", additional))
    }
    return dict(
        matched_stage_denominator=same_trials,
        deadline_fraction_improved=deadline,
        v5_within_10pct_counts_preserved=retains,
        passes=deadline and all(all(arms.values()) for arms in retains.values()),
    )


def audit(folder=REPORT, scratch=None):
    seal, digest, source, resources = archive(folder)
    for name in ("spec", "protocol"):
        path = folder / ("study.json" if name == "spec" else "PROTOCOL.md")
        whole_iq.checked(path, source[name + "_sha256"])
    ids = seal["cases"]
    spec = source["spec"]
    positions = {
        b: check.positions(folder, seal, published.method(spec["id"], b)) for b in BRANCHES
    }
    row_plan = {row["id"]: row for row in spec["cases"]}
    selection = check.read(folder / "selection.json")
    additional = [i for i in ids if row_plan[i]["cohort"] == "additional waveform"]
    previous = [i for i in ids if i not in additional]
    selected = [selection[band] for band in ("DS26", "DS29")]
    if set(additional) != {item["selected_id"] for item in selected}:
        raise ValueError("additional waveforms differ from the registered metadata selection")
    for item in selected:
        capture = source["cases"][item["selected_id"]]
        if (
            capture["clock_authority"] != item["capture_authority"]
            or capture["recording"]["segments"][0]["sha256"] != item["first_segment"]
            or item["selected_id"] in selection["excluded"]
        ):
            raise ValueError("selected waveform's first manifest or capture authority changed")
    primary_seal, primary_digest, primary_source, primary_resources = archive(PRIMARY)
    repeat_seal, repeat_digest, repeat_source, repeat_resources = archive(REPEAT)
    for prior in (primary_source, repeat_source):
        if (
            prior["detectors"]["control"]["sha256"] != source["detectors"]["control"]["sha256"]
            or prior["receiver_files"] != source["receiver_files"]
            or prior["native_sources"] != source["native_sources"]
        ):
            raise ValueError("historical comparison uses a different detector or position worker")
    primary = check.positions(
        PRIMARY, primary_seal, published.method(primary_source["spec"]["id"], "control")
    )
    repeat = check.positions(
        REPEAT, repeat_seal, published.method(repeat_source["spec"]["id"], "control")
    )
    if (
        set(primary).intersection(ids) != set(previous)
        or len(previous) != 6
        or len(additional) != 2
    ):
        raise ValueError("the requested six historical and two fresh radio admissions changed")
    prior_repeat(
        primary[REPEAT_CASE],
        primary_resources[REPEAT_CASE]["control"],
        repeat[REPEAT_CASE],
        repeat_resources[REPEAT_CASE]["control"],
    )
    _, refs = held_references(None, ids)
    scored = published.score_rows(
        [row for rows in positions.values() for row in rows.values()], resources, refs, spec["id"]
    )
    scores = {(s["id"], s["branch"], s["arm"]): s for s in scored}
    records = []
    for ident in ids:
        row = {b: positions[b][ident] for b in BRANCHES}
        if any(row["control"][k] != row["candidate"][k] for k in REQUEST):
            raise ValueError(f"{ident}: study arms have differing causal request or offered region")
        signature = {
            b: products(folder, seal, row[b], resources[ident][b], b, scratch) for b in BRANCHES
        }
        first, second = signature.values()
        if first is not None and second is not None and any(first[k] != second[k] for k in SUPPORT):
            raise ValueError(f"{ident}: paired waveform, delivery clocks or probe support changed")
        if ident in additional:
            history = dict(state="no_prior_waveform_control")
        else:
            former = products(
                PRIMARY,
                primary_seal,
                primary[ident],
                primary_resources[ident]["control"],
                "control",
            )
            history = control_parity(
                ident,
                row["control"],
                signature["control"],
                primary[ident],
                former,
                repeat[ident] if ident == REPEAT_CASE else None,
            )
        bindings = {k: row["control"][k] for k in REQUEST}
        records.append(
            dict(
                id=ident,
                cohort=row_plan[ident]["cohort"],
                bindings=bindings,
                detector_signatures=signature,
                historical_control=history,
                services={b: service_row(resources[ident][b]) for b in BRANCHES},
                scores={b: {arm: scores[ident, b, arm] for arm in ARMS} for b in BRANCHES},
            )
        )
    all_rows = panel_cases(ids, positions, resources, scores)
    fresh = panel_cases(additional, positions, resources, scores)
    return dict(
        boundary="Host local saved IQ through the identical compact position backend",
        prediction_lock_sha256=digest,
        previous_scout_full_prediction_lock_sha256=primary_digest,
        secondary_deadline_repeat_prediction_lock_sha256=repeat_digest,
        metadata_selection_sha256=_sha(folder / "selection.json"),
        scorer_sha256=_sha(Path(__file__)),
        detector_sha256={b: source["detectors"][b]["sha256"] for b in BRANCHES},
        memory_cap_bytes=source["memory_max"],
        swap_cap_bytes=source["swap_max"],
        service_deadline_s=source["limit_s"],
        panels=dict(
            all=all_rows,
            additional=fresh,
            previous=panel_cases(previous, positions, resources, scores),
        ),
        adoption_criterion=criterion(all_rows, fresh),
        historical_control_summary=historic_counts(records),
        records=records,
    )


def service_row(resource):
    keys = (
        "wall_s",
        "cpu_s",
        "raw_s",
        "position_s",
        "assembly_s",
        "wall_to_failure_s",
        "cpu_to_failure_s",
        "failure_clock",
        "max_bytes",
        "charged_peak_to_failure_bytes",
        "swap_bytes",
        "dual_calls",
        "within_20ms",
        "detector_call_wall_ms",
        "detector_call_cpu_ms",
        "failure",
        "service",
    )
    return {key: resource.get(key) for key in keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=local_output, default=REPORT)
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--pending", action="store_true", help="only list pending worker terminals")
    args = parser.parse_args()
    if args.pending:
        if args.work is None:
            parser.error("--pending requires the existing --work directory")
        remaining = pending(args.work)
        for item in remaining:
            print(item)
        raise SystemExit(2 if remaining else 0)
    save_json(args.study / "audit.json", audit(args.study, args.work))


if __name__ == "__main__":
    main()
