"""Isolate signed measurement and membership changes on the sealed 0016 pair."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, RELEASE, archive_identity, read, write
from dense_geographic_trial import host


HERE = Path(__file__).resolve().parent
PAIR = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
ARCHIVE = PAIR / "tle/archive"
ARCHIVE_SHA = "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
OFFER_SHA = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
INVENTORY_SHA = "sha256:e22b918df63370a0590757b70f71a0e620792cf90cf78a833e601af7a0b395a6"
RAW_AUTHORITY = "sha256:64e945e9717c2612fdb3118d7b65c713076a1b56f5de49f8fdf291a3220fc252"
SEAL_SHA = "e011f66be6db6f04473cc7be701ca30979c5af358e54f71cba9daf9b18783b6f"
CONTROLS = {
    "stock": ("4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0",
              "a3a18c37ee19ad6c7aaaf09b5ba41e2526028e7fe4404fe5107f8f2ab224b773"),
    "candidate": ("c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589",
                  "8eb8fec4f8e5bf1cd535887c3f8dccf3fc837a0edbbdda9bdb4bc530d2dddbe2"),
}
CELLS = ("matched-measurements", "also-drop-stock", "mixed-stock-matches")
EIGHT_MS_REFERENCE = "d5db26385ce031957206e47a0cf12ee2f93b04e2898daff2f10d7fd4e0452a7a"
CROSSOVER_REFERENCE = "7ad1cb18caacdcd101537b8f490ac096373e3fcff5b2baf82fce40cbf6b2c89a"


def verified(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Pinned file changed at {path}")
    return json.loads(data)


def epoch(factor):
    return factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]


def compatible(a, b):
    return (abs(remainder(epoch(a)-epoch(b), 40000/3)) <= 2
            and abs(a["fractional_tracking_cfo_hz"]-b["fractional_tracking_cfo_hz"]) <= 250)


def factor(lane):
    rows = lane["candidates"]
    if len(rows) > 1 or any(r["passed_fractional_margin_gate"] is not True for r in rows):
        raise ValueError("Expected a single genuine selected factor or an empty lane")
    return rows[0] if rows else None


def signature(packet):
    return dict(packet, source={k: v for k, v in packet["source"].items()
                                if k not in ("probes", "analysis_manifest_sha256")},
                provenance={k: v for k, v in packet["provenance"].items() if k not in ("run_id", "detector_sha256")})


def strata(stock, mixed):
    from mixed_aperture_receiver import FULL_RULE

    if signature(stock) != signature(mixed):
        raise ValueError("Original packets carry differing signed scope or capture clocks")
    probes = stock["source"]["probes"]
    counters, keys, rows = Counter(), set(), []
    for a, b in zip(probes, mixed["source"]["probes"], strict=True):
        if dict(a, candidates=[]) != dict(b, candidates=[]):
            raise ValueError("A signed lane changed identity")
        radio = a["receiver_id"]
        key = radio, a["valid_start_counter"]
        if radio != len(rows) % 2 or key in keys:
            raise ValueError("Expected original unique and ordered stereo lanes")
        keys.add(key)
        stream = (a["edge"], a["channel"], a["actual_rf_hz"], radio)
        anchor = FULL_RULE[counters[stream] % len(FULL_RULE)] == "full"
        counters[stream] += 1
        x, y = factor(a), factor(b)
        if x is not None and y is not None:
            kind = "matched" if compatible(x, y) else "changed_identity"
        else:
            kind = "stock_only" if x is not None else "mixed_only" if y is not None else "empty"
        rows.append((a, x, y, kind, anchor))
    return rows


def substituted(rows, cell):
    out = []
    for lane, stock, mixed, kind, _ in rows:
        if cell == "stock":
            selected = stock
        elif cell == "candidate":
            selected = mixed
        elif cell == CELLS[0]:
            selected = mixed if kind == "matched" else stock
        elif cell == CELLS[1]:
            selected = mixed if kind == "matched" else None
        elif cell == CELLS[2]:
            selected = stock if kind == "matched" else mixed
        else:
            raise ValueError("Unknown frozen substitution")
        out.append(dict(lane, candidates=[] if selected is None else [selected]))
    return out


def census(rows):
    counts, evidence = {}, []
    for lane, stock, mixed, kind, anchor in rows:
        key = f"rx{lane['receiver_id']}/{'anchor' if anchor else 'short'}"
        count = counts.setdefault(key, Counter())
        count[kind] += 1
        if kind == "matched" and stock != mixed:
            count["changed_tuple"] += 1
        if stock is not None or mixed is not None:
            evidence.append(dict(visit=lane["visit_index"], radio=lane["receiver_id"], channel=lane["channel"],
                counter=lane["valid_start_counter"], actual_rf_hz=lane["actual_rf_hz"], anchor=anchor,
                stock=stock, mixed=mixed, kind=kind))
    return dict(counts=counts, evidence=evidence)


def enrolled():
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    archive = archive_identity(ARCHIVE)
    if archive["snapshots_sha256"] != ARCHIVE_SHA:
        raise ValueError("Staged causal TLE archive differs from the original")
    offer = Algo08Region.parse(verified(PAIR / "offer.json", OFFER_SHA)).document()
    seal = verified(PAIR / "prediction-seal.json", SEAL_SHA)
    controls = {}
    for name, (native_sha, terminal_sha) in CONTROLS.items():
        folder = PAIR / name
        native, = folder.glob("fast-scan-automatic-work/*/detections.json")
        terminal, = folder.glob("fast-scan-automatic-work/*/terminal.json")
        metadata, = folder.glob("fast-scan-inputs/*.json")
        if any(seal[str(p.relative_to(PAIR))] != sha256(p.read_bytes()).hexdigest()
               for p in (native, terminal, metadata)):
            raise ValueError("Archived acquisition or terminal differs from the paired seal")
        packet, result = verified(native, native_sha), verified(terminal, terminal_sha)
        source = packet["source"]
        analysis = canonical_digest(["cancellation", RAW_AUTHORITY,
                                     packet["provenance"]["detector_sha256"][7:], source["probes"]])
        if (canonical_digest(packet) != result["native_sha256"] or canonical_digest(result)[7:] != terminal_sha
                or result["region"] != offer or result["decision"] != "complete" or set(result["arms"]) != set(ARMS)
                or source["raw_recording_authority_digest"] != RAW_AUTHORITY or analysis != source["analysis_manifest_sha256"]
                or source["input_manifest_sha256"] != INVENTORY_SHA or len(source["probes"]) != 1426
                or canonical_digest(read(metadata)) != INVENTORY_SHA):
            raise ValueError("Signed archived endpoint does not match the enrolled recording and offer")
        controls[name] = dict(packet=packet, terminal=result, inventory=str(metadata), native_sha256=native_sha,
                              terminal_sha256=terminal_sha)
    return dict(offer=offer, archive=archive, controls=controls)


def worker(saved, digest, output, inventory_path):
    from joint_publication import run
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    native = read(saved)
    inventory = read(inventory_path)
    if canonical_digest(inventory) != INVENTORY_SHA or canonical_digest(native) != digest:
        raise ValueError("Saved measurement or inventory binding changed")
    session = native["source"]["session_id"]
    # A diagnostic token that cannot resolve to original storage.
    recording = output.parent / inventory["recording_name"]

    def metadata_only(_store, selected, *, verify_windows=True):
        if verify_windows or selected != recording:
            raise ValueError("Only the sealed inventory metadata may be used")
        return session, INVENTORY_SHA, inventory

    def deny_waveform(*args, **kwargs):
        raise RuntimeError("No raw waveform reads are allowed in this saved substitution")

    def graph(prepared):
        tracks = prepared["tracks"]
        return dict(points=tracks["graph_points"], tracks=len(tracks["tracks"]), curved=len(tracks["curved_indices"]))

    args = SimpleNamespace(recording=recording, archive=ARCHIVE, region=PAIR / "offer.json", output=output,
                           saved=saved, saved_digest=digest, stock_control=True, verify_images=True, observe_prepared=graph)
    with (patch.object(FastScanStore, "inventory", metadata_only),
          patch.object(FastSegmentSource, "windows", deny_waveform), patch.object(ShortWindowReader, "__init__", deny_waveform)):
        run(args, saved_receiver=native["provenance"]["detector_sha256"][7:])


def bind_publication(root, native, expected):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    report = read(root / "joint-research-receipt.json")
    receipt = report["receipt"]
    work = root / "fast-scan-automatic-work"
    path, = work.glob("*/detections.json")
    terminal = read(work / receipt["run_id"] / "terminal.json")
    store = FastStandardAnalysisStore(root)
    detail = store.detail(receipt["run_id"])
    grid = store.position_grid(receipt["run_id"])
    position_path = store.position_path(receipt["run_id"])
    media = json.loads(json.dumps(artifacts(root, receipt)))
    if (native != read(path) or canonical_digest(native) != terminal["native_sha256"]
            or terminal["native_sha256"] != report["saved_digest"] or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["region"] != expected or terminal["decision"] != "complete" or set(terminal["arms"]) != set(ARMS)
            or report["saved_handoff_manifest"] != INVENTORY_SHA or detail["raw_authority"] != RAW_AUTHORITY
            or report["route"] != "stock" or media != report["evidence"] or len(media["images"]) != 8
            or not grid["complete"] or grid["evaluated_points"] != grid["planned_points"]
            or any(d["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"] for d in (grid, position_path))
            or set(report["solve"]["objective_replay"]) != set(ARMS)
            or any(abs(v) > 1e-5 for v in report["solve"]["objective_replay"].values())):
        raise ValueError("Saved substitution does not bind a complete original-route science publication")
    owners = report["selected_rows"]
    for arm in ARMS:
        mapping = {oid: sat for oid, sat, _ in owners[arm]}
        if len(mapping) != len(owners[arm]) or owner_digest(mapping) != detail["arms"][arm]["owner_sha256"]:
            raise ValueError("Original ordered owner rows do not bind the published owners")
    return dict(arms=terminal["arms"], native=terminal["native_sha256"], terminal=receipt["terminal_sha256"],
                observation_count=sum(len(p["candidates"]) for p in native["source"]["probes"]), owners=owners,
                owner_counts=report["selected_roles"], solve=report["solve"], media=media)


def score(sealed, root):
    from mixture_score import section

    old = verified(HERE / "measurements/eight-ms-physical.json", EIGHT_MS_REFERENCE)
    cross = verified(HERE / "measurements/full-short-crossover-summary.json", CROSSOVER_REFERENCE)
    controls = sealed["controls"]
    stock, mixed = (controls[label]["terminal"]["arms"] for label in CONTROLS)
    for run, arms in (("v3", stock), ("12ms", mixed)):
        if old["runs"][run]["arms"] != arms:
            raise ValueError("Original archive does not reproduce the sealed endpoints")
    for cell, arms in (("stock-stock", stock), ("candidate-stock", mixed)):
        old_fit = {arm: {key: cross["cells"][cell]["fit"]["arms"][arm][key] for key in ("latlon", "rf_rms_hz")} for arm in ARMS}
        if old_fit != arms:
            raise ValueError("Prior installed solver control does not exactly match the enrolled scientific finish")
    arms = {"stock": stock, "candidate": mixed, **{name: trial["arms"] for name, trial in sealed["trials"].items()}}
    fits = {label: section(measures, old["survey"], stock) for label, measures in arms.items()}
    changes = {}
    for a, b in (("stock", CELLS[0]), (CELLS[0], CELLS[1]), (CELLS[1], "candidate"), (CELLS[2], "candidate")):
        changes[f"{a} -> {b}"] = section(arms[b], old["survey"], arms[a])
    write(root / "scored.json", dict(fits=fits, contrasts=changes, survey_sha256=EIGHT_MS_REFERENCE,
                                     numerical_seal_sha256=sha256((root / "numerical-seal.json").read_bytes()).hexdigest()))


def run(root):
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from north_factor_swap import rebound
    from weak_combined_raw import measure

    machine = host()
    if root.resolve() != root or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use a fresh canonical tmpfs directory")
    setup = enrolled()
    controls = setup["controls"]
    originals = [controls[label]["packet"] for label in CONTROLS]
    rows = strata(*originals)
    if any(substituted(rows, label) != original["source"]["probes"]
           for label, original in zip(CONTROLS, originals, strict=True)):
        raise ValueError("Substitution failed to reproduce both signed endpoint lists")
    root.mkdir()
    environment_vars = environment(root)
    (root / "tmp").mkdir()
    environment_vars["TMPDIR"] = str(root / "tmp")
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=environment_vars, timeout=20)
    packets = {}
    for cell in CELLS:
        rows_for_cell = substituted(rows, cell)
        selected = rebound(originals[0], rows_for_cell, ["saved 20 ms mixed factor contrast v1", CONTROLS, cell])
        path = root / f"{cell}-detections.json"
        write(path, selected)
        packets[cell] = (path, selected)
    write(root / "inputs.json", dict(packets={name: canonical_digest(packet) for name, (_, packet) in packets.items()},
                                     controls=CONTROLS, census=census(rows)))
    for cell, (path, packet) in packets.items():
        command = [python, "-BPs", str(Path(__file__).resolve()), "worker", str(path), canonical_digest(packet),
                   str(root / cell), controls["stock"]["inventory"]]
        measure(command, environment_vars, root, cell)
    trials = {cell: dict(**bind_publication(root / cell, packet, setup["offer"]), process=read(root / f"{cell}-clock.json"))
              for cell, (_, packet) in packets.items()}
    if archive_identity(ARCHIVE) != setup["archive"]:
        raise ValueError("Original causal archive changed during the saved replay")
    sealed = dict(setup, machine=machine, trials=trials, order=CELLS, raw_waveform_reads=0,
                  controls={name: {k: v for k, v in row.items() if k != "packet"} for name, row in controls.items()},
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  protocol_sha256=sha256((HERE / "full-short-factor-contrast-protocol.md").read_bytes()).hexdigest())
    write(root / "numerical-seal.json", sealed)
    score(sealed, root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("run").add_argument("root", type=Path)
    replay = sub.add_parser("worker")
    replay.add_argument("saved", type=Path)
    replay.add_argument("digest")
    replay.add_argument("output", type=Path)
    replay.add_argument("inventory_path", type=Path)
    values = vars(parser.parse_args())
    {"run": run, "worker": worker}[values.pop("action")](**values)
