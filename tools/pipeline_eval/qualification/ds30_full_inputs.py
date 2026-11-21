"""Freeze every DS30 member and its truth-free, causal position input on Gauss."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from ..variants import v5_lean
from . import blind_compact_run, ds30_panel, original_v5, recording_to_v5
from .blind_compact_roster import BULK, DS29, locator, seal
from .capture_release import inventory_digest
from .full_v5_check import _probe, _sha
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read

ROOT = Path(__file__).resolve().parents[3]
WORK = BULK / "leo-dev/ds30-full-20261121"
OUT = ROOT / "reports/2026_11_21_ds30_full"
INPUTS = WORK / "snapshot/inputs"
SEED = "DS30-full-v1"
METHODS = ("algo07v5", "compact_two_scan")


def frozen_members():
    expected = read(ds30_panel.OUT / "dataset/verification.json")["manifest_sha256"]
    path = ds30_panel.DATA / "manifest.json"
    if "sha256:" + _sha(path) != expected:
        raise ValueError("DS30 manifest differs from the published revision")
    members = read(path)["members"]
    if len({m["raw_recording"]["identity_sha256"] for m in members}) != len(members):
        raise ValueError("repeated DS30 recording content")
    return expected, members


def reserve():
    digest, members = frozen_members()
    previous = {r["case"]["id"] for r in read(ds30_panel.OUT / "roster.json")["cases"]}
    roster = [
        dict(
            id=m["dataset_label"],
            content=m["raw_recording"]["identity_sha256"],
            recording_state=m["recording_state"],
            windows=m["window_count"],
            archived_original=bool(m["tracking_inputs"]),
            previous=m["dataset_label"] in previous,
            captured_utc_ns=m["captured_utc_ns"],
        )
        for m in members
    ]
    roster.sort(key=lambda r: hashlib.sha256((SEED + r["content"]).encode()).digest())
    seal(
        OUT / "cohort.json",
        dict(
            dataset_sha256=digest,
            seed=SEED,
            members=roster,
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
        ),
    )
    previous_build = read(ds30_panel.OUT / "build.json")
    for method, path in blind_compact_run.LIBS.items():
        if _sha(path) != previous_build["libraries"][method]:
            raise ValueError("receiver binary differs from the eight-recording benchmark")
    for edge, expected in previous_build["assets"].items():
        if _sha(blind_compact_run.TWO_WORK / "embedded" / (edge + ".f32")) != expected:
            raise ValueError("receiver pilot changed")
    seal(
        OUT / "build.json",
        dict(
            libraries=previous_build["libraries"],
            assets=previous_build["assets"],
            roster_sha256=_sha(OUT / "cohort.json"),
            predecessor_build_sha256=_sha(ds30_panel.OUT / "build.json"),
            original_source=v5_lean.SOURCE_SHA256,
            runner_hashes=original_v5.RUNNER_DIGESTS,
        ),
    )
    return roster


def checked_source(entry):
    from leo.contracts.digests import canonical_digest

    source = read(Path(entry["path"]))
    if canonical_digest(source) != entry["sha256"]:
        raise ValueError("published acquisition inventory digest changed")
    return source


def index_timing(member):
    """Rebuild native clocks, quality exclusions and empty probe headers from signed indexes."""
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support

    policy = FastScanPolicyV2()
    entries, hashes, clocks, probes, excluded, anchors = [], [], [], [], [], []
    serials, generations, authorities = set(), set(), set()
    previous_end = None
    for index, item in enumerate(member["raw_recording"]["segments"]):
        path = Path(item["path"])
        data = path.read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("segment manifest digest changed")
        seg = json.loads(data)
        receivers = tuple(seg["receiver_ids"])
        rate = seg["sample_rate_hz"]
        if receivers != (0, 1) or rate != 10_000_000 or seg["configuration"]["window_ms"] != 20:
            raise ValueError("unsupported device sampling geometry")
        serials.add(seg["radio"]["serial"])
        targets = {v["target_id"]: v for v in seg["configuration"]["targets"]}
        sequences = 0
        for chunk in seg["chunks"]:
            filename = chunk["index_relative_path"]
            if Path(filename).name != filename or chunk["first_sequence"] != sequences:
                raise ValueError("invalid chunk order or index path")
            data = (path.parent / filename).read_bytes()
            if (
                len(data) != chunk["index_bytes"]
                or "sha256:" + hashlib.sha256(data).hexdigest() != chunk["index_sha256"]
            ):
                raise ValueError("recorded index digest changed")
            rows = data.splitlines()
            if len(rows) != chunk["window_count"]:
                raise ValueError("chunk index count mismatch")
            for raw in rows:
                r = json.loads(raw)
                a = r["acquisition"]
                count = len(hashes)
                if r["sequence"] != sequences or a["global_visit"] != count:
                    raise ValueError("nonconsecutive recording index")
                lo, hi = a["sample_start"], a["sample_end"]
                if (
                    type(lo) is not int
                    or type(hi) is not int
                    or hi < lo
                    or (previous_end is not None and lo < previous_end)
                ):
                    raise ValueError("unusable hardware sample counter")
                previous_end = hi
                generations.add(a["generation"])
                receipt = json.loads(a["retune_receipt"])
                clock = receipt["host_delivery_clock"]
                if (
                    type(clock.get("monotonic_ns")) is not int
                    or type(clock.get("realtime_ns")) is not int
                ):
                    raise ValueError("missing delivery clock")
                clocks.append(clock)
                if receipt.get("utc_clock_bracket") is not None:
                    anchor = receipt["utc_clock_bracket"]
                    if count or anchor["sample_counter"] != lo:
                        raise ValueError("recording does not have a unique initial sample anchor")
                    anchors.append(anchor)
                target = targets[r["target_id"]]
                authorities.add(target.get("rf_mapping_authority", "unknown"))
                hashes.append(r["iq_sha256"])
                shape = (r["sample_count"], r["receiver_count"], 2)
                if valid_window_support(a, rate, shape, receivers, policy):
                    header = SimpleNamespace(acquisition=a, target=target, sample_rate_hz=rate)
                    probes.extend(_probe(header, rx, ()) for rx in receivers)
                else:
                    excluded.append(
                        dict(
                            visit=count,
                            sample_start=lo,
                            sample_end=hi,
                            iq_sha256=r["iq_sha256"],
                            reason="invalid sample support or retune quality",
                        )
                    )
                sequences += 1
        if sequences != seg["window_count"]:
            raise ValueError("sealed segment window count mismatch")
        entries.append(
            dict(
                scope=f"segment-{index:08d}",
                path=str(path.parent),
                manifest_digest=item["sha256"],
                windows=sequences,
            )
        )
    if (
        len(hashes) != member["window_count"]
        or len(anchors) != 1
        or len(serials) != 1
        or len(generations) != 1
        or not all(type(g) is int for g in generations)
    ):
        raise ValueError("raw timing or capture identity is incomplete")
    if member["source_inputs"]:
        # A physical copy can live on another spool. Preserve the producer's inventory paths.
        (published_source,) = member["source_inputs"]
        signed = checked_source(published_source)

        def signature(entry):
            return (
                entry["scope"],
                Path(entry["path"]).name,
                entry["manifest_digest"],
                entry["windows"],
            )

        if (
            [signature(e) for e in entries] != [signature(e) for e in signed["segments"]]
            or signed["recording_name"] != member["recording_id"]
            or signed["window_count"] != len(hashes)
        ):
            raise ValueError("recorded source inventory differs from signed segment contents")
        entries = signed["segments"]
    inventory = inventory_digest(entries, len(hashes))
    if member["source_inputs"] and inventory != published_source["sha256"]:
        raise ValueError("published acquisition inventory digest changed")
    identity = recording_to_v5.digest([inventory, hashes])
    session = "fast-" + inventory[7:39]
    if member["session_id"] and member["session_id"] != session:
        raise ValueError("rebuilt session differs from the published acquisition inventory")
    if member["tracking_inputs"] and member["raw_authority_digest"] != identity:
        raise ValueError("rebuilt timing differs from published source identity")
    timing_digest = recording_to_v5.digest(
        ["recorded DS30 clock and receiver headers", inventory, identity]
    )
    return dict(
        schema_version=2,
        clock_anchor=anchors[0],
        delivery_clocks=clocks,
        last_sample_counter=previous_end,
        source=dict(
            session_id=session,
            capture_mode="adaptive",
            sample_rate_hz=rate,
            radio_id=serials.pop(),
            stream_generation=f"continuous-iio-{generations.pop():016x}",
            input_manifest_sha256=inventory,
            analysis_manifest_sha256=timing_digest,
            raw_recording_authority_digest=identity,
            qualified=True,
            timing=None,
            probes=probes,
            probe_ms=20,
            capture_start_utc_ns=None,
            capture_end_utc_ns=None,
        ),
        provenance=dict(
            run_id="clock-" + timing_digest[7:39],
            window_count=len(hashes),
            processed_windows=len(probes) // 2,
            invalid_capture=len(excluded),
            excluded_windows=excluded,
            skipped_fast_score=0,
            rf_mapping_authorities=sorted(authorities),
            scope="recorded clocks and hardware quality only; no detector measurements",
        ),
    )


def check_timing(rebuilt, published):
    for key in ("clock_anchor", "delivery_clocks", "last_sample_counter"):
        if rebuilt[key] != published[key]:
            raise ValueError("index clock differs from published " + key)
    for key in ("excluded_windows", "window_count", "processed_windows"):
        if rebuilt["provenance"][key] != published["provenance"][key]:
            raise ValueError("index mask differs from published " + key)
    for key in rebuilt["source"]:
        if (
            key not in ("analysis_manifest_sha256", "probes")
            and rebuilt["source"][key] != published["source"][key]
        ):
            raise ValueError("index source differs from published " + key)
    headers = [dict(row, candidates=[]) for row in published["source"]["probes"]]
    if rebuilt["source"]["probes"] != headers:
        raise ValueError("index opportunities differ from the published receiver headers")


def audit_bindings(roster, parent_sha, bindings):
    """Check whole-cohort readiness using only capture evidence."""
    sessions, windows, valid = set(), 0, 0
    rebuilt = {"complete": 0, "incomplete": 0}
    evidence, parity = {}, []
    for row in roster:
        label = row["id"]
        path = bindings / (label + ".json")
        record = read(path)
        case = record["case"]
        usable = case["valid_visits"]
        if (
            case["id"] != label
            or label in evidence
            or case["session_id"] in sessions
            or record["roster_sha256"] != parent_sha
            or record["archived_original"] != row["archived_original"]
            or record["index_parity"] != row["previous"]
            or case["recording"]["window_count"] != row["windows"]
            or not 0 <= usable <= row["windows"]
        ):
            raise ValueError("input audit differs from the committed recording: " + label)
        if not record["archived_original"]:
            rebuilt[row["recording_state"]] += 1
        if record["index_parity"]:
            parity.append(label)
        windows += row["windows"]
        valid += usable
        sessions.add(case["session_id"])
        evidence[label] = dict(binding_sha256=_sha(path), usable_visits=usable)
    return dict(
        roster_sha256=parent_sha,
        recordings=len(sessions),
        recorded_visits=windows,
        usable_visits=valid,
        excluded_visits=windows - valid,
        antenna_opportunities=2 * valid,
        archived_original=len(sessions) - sum(rebuilt.values()),
        rebuilt_inputs=rebuilt,
        reconstructed_timing_matched_published=sorted(parity),
        bindings=evidence,
    )


def prepare():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore

    roster = reserve()
    _, members = frozen_members()
    lookup = {m["dataset_label"]: m for m in members}
    old = {r["case"]["id"]: r["case"] for r in read(ds30_panel.OUT / "roster.json")["cases"]}
    sample = next(iter(old.values()))
    template = read(DS29 / "template-request.json")
    base = read_bound(sample["request"])
    config = DS29 / "inputs/config.json"
    if (
        template["evaluation_reference"] is not None
        or "sha256:" + _sha(config) != template["track_config"]["sha256"]
    ):
        raise ValueError("DS29 template or tracking configuration changed")
    ds30_panel.save_bytes(INPUTS / "config.json", config.read_bytes())
    store = FastScanStore(ds30_panel.ARCHIVE)
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = archive.list_snapshots("space-track")
    adapter = ds30_panel.snapshot_tools()
    sys.path.insert(0, str(v5_lean.RUNNER))
    from evaluate_accuracy_repair import worker_request

    for row in roster:
        label = row["id"]
        dest = WORK / "bindings" / (label + ".json")
        dest.parent.mkdir(exist_ok=True, parents=True)
        if dest.exists():
            continue
        member = lookup[label]
        folder = INPUTS / label
        if member["tracking_inputs"]:
            payload, doc, run, _ = adapter.native_evidence(member, store)
            if label in old:
                check_timing(index_timing(member), doc)
        else:
            doc = index_timing(member)
            payload = (recording_to_v5.encoded(doc) + "\n").encode()
            run = doc["provenance"]["run_id"]
        native = folder / "native.json"
        ds30_panel.save_bytes(native, payload)
        cutoff = doc["clock_anchor"]["before"]["realtime_ns"]
        if cutoff > member["captured_utc_ns"]:
            raise ValueError("orbit cutoff occurs after the initial acquisition")
        hashes = {}
        for ref in adapter.causal(snapshots, cutoff):
            shared = INPUTS / "causal-tle" / ref.path.name
            if not shared.exists():
                ds30_panel.save_bytes(shared, archive.read(ref).encode("ascii"))
            if _sha(shared) != ref.sha256:
                raise ValueError("historical orbit file changed")
            link = folder / "tle/archive/space-track" / ref.path.name
            link.parent.mkdir(exist_ok=True, parents=True)
            if not link.exists():
                os.link(shared, link)
            if not link.samefile(shared):
                raise ValueError("per-recording orbit link differs")
            hashes[ref.path.name] = ref.sha256
        native_sha = "sha256:" + hashlib.sha256(payload).hexdigest()
        session = doc["source"]["session_id"]
        cohort = dict(
            template=template,
            config_sha256=template["track_config"]["sha256"],
            snapshot=str(INPUTS.parent),
            members=[
                dict(
                    dataset_label=label,
                    availability="available",
                    input_sha256=native_sha,
                    causal_snapshots=hashes,
                    session_id=session,
                    recording_id=member["recording_id"],
                )
            ],
        )
        skeleton = dict(
            source=base["source"],
            native_manifest=base["native_manifest"],
            policies={"baseline": base["policy"]},
            output=str(WORK / "jobs"),
            cohorts={"DS30": cohort},
        )
        request = worker_request(
            skeleton, dict(dataset="DS30", case=label, repetition=0), "baseline"
        )
        if request["job"]["evaluation_reference"] is not None:
            raise ValueError("scoring reference in solver input")
        req = folder / "request.json"
        seal(req, request)
        case = dict(
            id=label,
            panel="DS30",
            session_id=session,
            run_id=run,
            regions=sample["regions"],
            native=locator(native, native_sha),
            request=locator(req, _sha(req)),
            raw_authority=doc["source"]["raw_recording_authority_digest"],
            valid_visits=doc["provenance"]["processed_windows"],
            recording=dict(
                window_count=member["window_count"],
                segments=[ds30_panel.raw_locator(s) for s in member["raw_recording"]["segments"]],
            ),
        )
        # Publish only after all of this member's dependencies and the request are complete.
        tmp = dest.with_suffix(".partial")
        seal(
            tmp,
            dict(
                case=case,
                roster_sha256=_sha(OUT / "cohort.json"),
                orbit_cutoff_ns=cutoff,
                orbit_count=len(hashes),
                archived_original=row["archived_original"],
                index_parity=label in old,
            ),
        )
        os.replace(tmp, dest)
        print("prepared", label, case["valid_visits"], flush=True)
    seal(
        OUT / "input-audit.json",
        audit_bindings(roster, _sha(OUT / "cohort.json"), WORK / "bindings"),
    )


if __name__ == "__main__":
    prepare()
