"""Verify and compare the four sealed capture-era and ordinary factor outcomes."""

import gzip
import json
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from .fractional_runtime_whole import verify_request
from .full_held_scores import held_references
from .full_v5_check import MARGIN_GATE, _load_case
from .input_factor_bridge import BULK, REPO, REPORT, RUN, _sha, check, checked_history, read
from .phase_confirmation import _case
from .prefix_figures import csv_file

CASES = ("DS26-0036", "DS26-0237", "DS29-0082", "DS29-0174")
DEVELOPMENT = ("DS26-0036", "DS29-0082")
SCREEN = REPORT.parents[1]
SECANT = "v5_secant_fit"
POLICY = "fast-v5-zero-recovery-control-v1"
NATIVE_KEYS = (
    "session_id",
    "input_manifest_sha256",
    "raw_recording_authority_digest",
    "sample_rate_hz",
    "probe_ms",
    "radio_id",
    "stream_generation",
    "capture_mode",
)


def sealed(folder, lock):
    file = folder / lock
    value = read(file)
    for name, digest in value["files"].items():
        check(folder / name, digest)
    if "source_lock_sha256" in value:
        check(folder / "source-lock.json", value["source_lock_sha256"])
    return value


def ledger(path):
    with gzip.open(path, "rt") as stream:
        rows = list(map(json.loads, stream))
    keyed = {r["id"]: r for r in rows}
    if len(keyed) != len(rows):
        raise ValueError(f"duplicate identities in {path}")
    return keyed


def native_header(document):
    source, provenance = document["source"], document["provenance"]
    probes = source["probes"]
    factors = [item for probe in probes for item in probe["candidates"]]
    if any(
        item["passed_fractional_margin_gate"] != (item["fractional_margin"] >= MARGIN_GATE)
        for item in factors
    ):
        raise ValueError("fractional factor gate does not match the documented margin")
    return dict(
        schema_version=document["schema_version"],
        **{k: source[k] for k in NATIVE_KEYS},
        analysis_manifest_sha256=source["analysis_manifest_sha256"],
        detector_sha256=provenance.get("detector_sha256"),
        run_id=provenance["run_id"],
        scope=provenance["scope"],
        window_count=provenance["window_count"],
        processed_windows=provenance["processed_windows"],
        invalid_capture=provenance["invalid_capture"],
        skipped_fast_score=provenance["skipped_fast_score"],
        probe_rows=len(probes),
        empty_probe_rows=sum(not row["candidates"] for row in probes),
        candidate_rows=len(factors),
        gate_passing_rows=sum(item["passed_fractional_margin_gate"] for item in factors),
        fractional_margin_gate=MARGIN_GATE,
    )


def factor_changes(before, after):
    first, second = map(native_header, (before, after))
    if (
        any(first[key] != second[key] for key in NATIVE_KEYS)
        or before["clock_anchor"] != after["clock_anchor"]
        or before["last_sample_counter"] != after["last_sample_counter"]
        or before["provenance"]["excluded_windows"] != after["provenance"]["excluded_windows"]
    ):
        raise ValueError("factor documents do not describe the same acquisition")
    probes_a, probes_b = (d["source"]["probes"] for d in (before, after))
    if any(
        (a["visit_index"], a["receiver_id"], a["valid_start_counter"])
        != (b["visit_index"], b["receiver_id"], b["valid_start_counter"])
        for a, b in zip(probes_a, probes_b, strict=True)
    ):
        raise ValueError("probe row sampling support or order changed")
    return dict(
        capture_era=first,
        ordinary=second,
        changed_candidate_probe_rows=sum(
            a["candidates"] != b["candidates"] for a, b in zip(probes_a, probes_b, strict=True)
        ),
    )


def endpoint(result):
    validate_result(result)
    if result["status"] != "ok":
        raise ValueError("expected a complete position in the frozen input comparison")
    return {arm: {key: result["arms"][arm][key] for key in ("latlon", "rf_rms_hz")} for arm in ARMS}


def within(candidate, control):
    return candidate <= control * 1.10


def score(ident, arms, truth):
    rows = []
    for arm in ARMS:
        original, capture, ordinary = (a[arm] for a in arms)
        a, b, c = (distance_km(fit["latlon"], truth) for fit in (original, capture, ordinary))
        rows.append(
            dict(
                id=ident,
                arm=arm,
                original_error_km=a,
                capture_era_secant_error_km=b,
                ordinary_secant_error_km=c,
                fixed_factor_delta_km=b - a,
                changed_factor_delta_km=c - b,
                total_delta_km=c - a,
                original_residual_rms_hz=original["rf_rms_hz"],
                capture_era_conditional_rms_hz=capture["rf_rms_hz"],
                ordinary_conditional_rms_hz=ordinary["rf_rms_hz"],
                compact_conditional_rms_delta_hz=ordinary["rf_rms_hz"] - capture["rf_rms_hz"],
                capture_within_10pct_original=within(b, a),
                ordinary_within_10pct_capture=within(c, b),
                ordinary_within_10pct_original=within(c, a),
            )
        )
    return rows


def publish():
    compact_folder = SCREEN / "secant-full"
    compact_receipt = sealed(compact_folder, "receipt.json")
    compact = ledger(compact_folder / f"{SECANT}.jsonl.gz")
    originals = read(compact_folder / "original-v5-inputs.json")
    integrated = SCREEN / "integration/cavity-lifetime"
    sealed(integrated, "direct-lock.json")
    lifetime_plan = read(integrated / "plan.json")["source"]
    lifetime = ledger(integrated / "direct.jsonl.gz")
    next_direct = SCREEN / "next/direct-lifetime"
    sealed(next_direct, "receipt.json")
    ordinary_secant = ledger(next_direct / "secant-positions.jsonl.gz")
    for path, digest in lifetime_plan["sources"].items():
        check(REPO / path, digest)
    for path, digest in lifetime_plan["experiment"].items():
        if path in ("v5_cavity_lifetime.py", "cavity_lifetime_worker.py"):
            folder = "variants" if path.startswith("v5_") else "qualification"
            check(REPO / "tools/pipeline_eval" / folder / path, digest)
    for name, digest in compact_receipt["sources"].items():
        check(REPO / "tools/pipeline_eval/variants" / name, digest)
        integrated_path = f"tools/pipeline_eval/variants/{name}"
        if lifetime_plan["sources"].get(integrated_path) != digest:
            raise ValueError(f"secant and lifetime sources differ on {name}")
    bridge_lock = sealed(REPORT, "bridge-lock.json")
    bridge_plan = read(REPORT / "bridge-plan.json")
    bridge = ledger(REPORT / "bridge-positions.jsonl.gz")
    planned = {row["id"]: row for row in bridge_plan["recordings"]}
    sources = list(REPORT / name for name in bridge_lock["files"])
    sources.extend(
        (
            REPORT / "bridge-lock.json",
            compact_folder / "receipt.json",
            integrated / "direct-lock.json",
            next_direct / "receipt.json",
        )
    )
    audits, scores, chart = {}, [], []
    refs = {r["id"]: r for r in held_references("", CASES)[1]}
    for ident in CASES:
        case = _load_case(ident)
        dev = ident in DEVELOPMENT
        whole = SCREEN / ("streamlined/whole-fractional" if dev else "next/full-held-pair")
        key = whole.name
        whole_lock = sealed(whole, "prediction-lock.json")
        sources.append(whole / "prediction-lock.json")
        whole_source = read(whole / "source-lock.json")
        if whole_source["sources"][str(integrated / "plan.json")] != _sha(integrated / "plan.json"):
            raise ValueError("whole replay and integrated lifetime source differ")
        read_lock = whole_source["inputs"][ident]
        ordinary = ledger(whole / "positions.jsonl.gz")[ident]
        stock = ledger(whole / "control-positions.jsonl.gz")[ident]
        trace = json.loads(gzip.decompress((whole / "stages.json.gz").read_bytes()))[ident]
        trace = trace if dev else trace["optimized_whole_iq"]
        replay = trace["raw"]
        if (
            ident not in whole_lock["cases"]
            or not trace["exact_endpoints_and_radio"]
            or not replay["factor_parity"]["complete_native_science_exact"]
            or not replay["request_parity"]
            or endpoint(ordinary["result"]) != endpoint(stock["result"])
            or replay["control_native_sha256"] != read_lock["native_sha256"]
            or ordinary["origin_native_sha256"] != read_lock["native_sha256"]
            or stock["native_sha256"] != read_lock["native_sha256"]
        ):
            raise ValueError(f"ordinary authority differs on {ident}")
        capture = compact[ident]
        capture_sha = case["native"]["sha256"]
        native_sha = replay["native_sha256"]
        for row, sha in ((capture, capture_sha), (ordinary, native_sha)):
            if (
                row["native_sha256"] != sha
                or row["catalog_sha256"] != case["catalog"]["sha256"]
                or row["tile"] != case["regions"][0]
            ):
                raise ValueError(f"input/offer receipt differs on {ident}")
        metrics = capture["result"]["metrics"]
        if (
            capture["source_sha256"] != compact_receipt["sources"]
            or metrics["initial_phase_refresh_counts"] != [5] * metrics["initial_branches"]
            or ordinary["result"]["metrics"]["kernel_sha256"] != metrics["kernel_sha256"]
        ):
            raise ValueError(f"five-refresh or projector lineage differs on {ident}")
        original_path = BULK / case["request"]["path"]
        check(original_path, case["request"]["sha256"])
        original = read(original_path)
        job = original["job"]
        identity = job["identity"]
        old_receipt = originals[ident]["baseline"]
        execution_path = original_path.parent.parent / "baseline-execution.json"
        executed = read(execution_path)
        check(execution_path, old_receipt["execution_sha256"])
        if (
            executed["request_sha256"] != old_receipt["request_sha256"]
            or executed["worker"]["request_sha256"]
            != "sha256:" + sha256(encoded(original)).hexdigest()
            or executed["status"] != "complete"
            or executed["worker"]["policy"] != POLICY
            or original["policy"] != POLICY
            or executed["role"] != "baseline"
            or identity["session_id"] != case["session_id"]
            or job["search_center"] != case["regions"][0]["center"]
            or original["source"]["sha256"] != compact_receipt["scientific_source"]
        ):
            raise ValueError(f"original no-repair v5 proof differs on {ident}")
        resolved = Path(_case(case)["request_path"])
        check(resolved, capture["resolved_request_sha256"])
        original_secant_request = read(resolved)
        normalized = dict(
            original_secant_request,
            job=dict(
                original_secant_request["job"],
                native_input=job["native_input"],
                output_root=job["output_root"],
            ),
        )
        if normalized != original:
            raise ValueError(f"capture-era secant scientific request differs on {ident}")
        candidate_dir = RUN / key / ident
        candidate_path = candidate_dir / "native.json"
        candidate_request = candidate_dir / "position/request.json"
        check(candidate_request, replay["worker_request_sha256"])
        verify_request(
            read(candidate_request), original, native_path=candidate_path, native_sha256=native_sha
        )
        check(candidate_path, native_sha)
        capture_path = BULK / case["native"]["path"]
        check(capture_path, capture_sha)
        check(Path(job["track_config"]["path"]), case["track_config"]["sha256"])
        history = checked_history(job, original["causal_snapshots"], case["cutoff_utc_ns"])
        if history[-1] != dict(
            utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"]
        ):
            raise ValueError(f"current causal catalogue differs on {ident}")
        authority = refs[ident]["reference"]["baseline"]
        arms = {
            k: dict(latlon=r["endpoint_latlon"], rf_rms_hz=r["residual_rms_hz"])
            for k, r in executed["worker"]["arms"].items()
        }
        if any(arms[k] != {x: authority[k][x] for x in ("latlon", "rf_rms_hz")} for k in ARMS):
            raise ValueError(f"original execution differs from its frozen endpoint on {ident}")
        capture_end, ordinary_end = endpoint(capture["result"]), endpoint(ordinary["result"])
        if dev:
            other = ordinary_secant[ident]
            checked = (
                other["native_sha256"] == read_lock["native_sha256"]
                and other["result"]["metrics"]["initial_phase_refresh_counts"]
                == [5] * other["result"]["metrics"]["initial_branches"]
                and endpoint(other["result"]) == ordinary_end
            )
            implementation = "same secant on both factor sources"
        elif ident in lifetime:
            other = lifetime[ident]
            checked = (
                other["native_sha256"] == capture_sha
                and other["mode"] == "direct"
                and endpoint(other["result"]) == capture_end
            )
            implementation = "same direct lifetime on both factor sources"
        else:
            expected = {
                "capture-era": (capture_end, capture_sha),
                "ordinary": (ordinary_end, native_sha),
            }
            checked = True
            for kind, (expected_end, expected_sha) in expected.items():
                pair = bridge[f"{kind}-{ident}"]
                bound = planned[pair["id"]]
                same_input = all(
                    pair[k] == value
                    for k, value in bound.items()
                    if k not in ("archive", "history")
                )
                proof = pair["runtime"]["proof"]
                checked &= (
                    same_input
                    and pair["native_sha256"] == expected_sha
                    and pair["exit_code"] == 0
                    and len(proof) == 1
                    and proof[0]["cpu"] == bridge_plan["cpu"]
                    and proof[0]["memory"] == bridge_plan["memory_bytes"]
                    and proof[0]["swap"] == bridge_plan["swap_bytes"]
                    and endpoint(pair["result"]) == expected_end
                )
            implementation = "same 78-source compact standalone on both factor sources"
        scores.extend(score(ident, (arms, capture_end, ordinary_end), refs[ident]["truth"]))
        chart.extend((capture, ordinary))
        audits[ident] = dict(
            session_id=case["session_id"],
            capture_era_native_sha256=capture_sha,
            ordinary_native_sha256=native_sha,
            ordinary_stock_sha256=read_lock["native_sha256"],
            original_v5_execution_sha256=old_receipt["execution_sha256"],
            request_sha256={
                kind: _sha(path)
                for kind, path in (
                    ("original", original_path),
                    ("capture_secant", resolved),
                    ("ordinary", candidate_request),
                )
            },
            scientific_request_matches=True,
            solver_lineage=implementation,
            exact_endpoint_bridge=bool(checked),
            causal_history=history,
            track_config_sha256=case["track_config"]["sha256"],
            tile=case["regions"][0],
            screen_center=job["screen_center"],
            policy=POLICY,
            factors=factor_changes(read(capture_path), read(candidate_path)),
            prepared={
                name: {k: r["result"]["metrics"][k] for k in ("observations", "tracks")}
                for name, r in (("capture_era", capture), ("ordinary", ordinary))
            },
        )
    counts = {
        arm: {
            key: sum(r[key] for r in scores if r["arm"] == arm)
            for key in (
                "capture_within_10pct_original",
                "ordinary_within_10pct_capture",
                "ordinary_within_10pct_original",
            )
        }
        for arm in ARMS
    }
    save_json(REPORT / "comparison.json", dict(cases=audits, within_10pct=counts))
    csv_file(REPORT / "scores.csv", scores)
    path = REPORT / "positions.jsonl.gz"
    write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in chart), mtime=0))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            files={
                name: _sha(REPORT / name)
                for name in ("positions.jsonl.gz", "comparison.json", "scores.csv")
            },
            source_sha256=_sha(Path(__file__)),
            parent_locks={str(p.relative_to(REPO)): _sha(p) for p in sources},
        ),
    )


if __name__ == "__main__":
    publish()
