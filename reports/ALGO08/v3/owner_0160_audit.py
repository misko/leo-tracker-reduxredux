"""Compare exact signed publication ownership using only completed DS30-0160 receipts."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path


PAIR = Path("/dev/shm/leo-v3-saved-0160-pair-01")
CONFIRMED = Path("/dev/shm/leo-v3-saved-0160-confirm-01/cumulative")
AUDIT = Path("/dev/shm/leo-v3-saved-0160-audit.json")
PINS = {
    "audit": "80c0658736c7e94ecdbbc56839171ccb10a0fa74880266f29c6dca8a61229038",
    "native": "1c56c47f871933cdc1887e41d79d2b28da0624b3104d2e5b05d0957c488bd4b5",
    "stock": "ebf1a80ae206a9c32cae2374e49b050faa1d0087413b313a3189a541d7e4ed08",
    "cumulative": "73e54beda2194af4807b06b4d26e60f58afea4acc73b64cf479d7b1e33456666",
    "stock_worker": "8e08a9af8f911a2b212be56249e07b0d78db471a14f8f295424d0aaa1ccefae5",
    "cumulative_worker": "dcff021b1ea2c21379c2c2307eb59eed66dbb5eda48ac33c9f95135797fc0943",
}
ARMS = ("c0", "fitted_c")
# Keys transcribed from the two digest-bound original track-RMS PNGs.
LOST_COMPONENTS = {
    (62127, 1, 1): "SCAN-RX1-CH1-T000-RF10940312500.000000",
    (57781, 1, 5): "SCAN-RX1-CH5-T002-RF11940312500.000000",
    (57781, 1, 6): "SCAN-RX1-CH6-T002-RF12190312500.000000",
}


def sha(data):
    return sha256(data).hexdigest()


def canonical(doc):
    return "sha256:"+sha(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


def load(path, expected=None):
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError(f"Pinned forensic input changed at {path}")
    return json.loads(raw)


def observations(document):
    source, anchor = document["source"], document["clock_anchor"]["sample_counter"]
    rx_order = sorted({row["receiver_id"] for row in source["probes"]})
    result = {}
    for row in source["probes"]:
        candidates = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
        if not candidates:
            continue
        first = max(candidates, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        radio, sample = row["receiver_id"], row["valid_start_counter"]
        identity = "sha256:"+sha(f"{source['session_id']}:{radio}:{sample}".encode())
        if identity in result:
            raise ValueError("A signed observation identity occurs twice")
        result[identity] = dict(receiver=1+rx_order.index(radio), native_receiver_id=radio,
                                channel=row["channel"], rf_hz=row["actual_rf_hz"], visit_index=row["visit_index"],
                                time_s=(sample-anchor)/source["sample_rate_hz"] + source["probe_ms"]*.0005,
                                sample_counter=sample, signed_cfo_hz=first["fractional_tracking_cfo_hz"])
    return result


def owners(rows):
    table = {oid: (norad, role) for oid, norad, role in rows}
    if len(table) != len(rows) or any(role not in ("conditional", "predictive", "family") for _, role in table.values()):
        raise ValueError("Ambiguous retained ownership")
    return table


def transitions(before, after):
    common = before.keys() & after.keys()
    return dict(removed=sorted(before.keys()-after.keys()), added=sorted(after.keys()-before.keys()),
                owner_switch=sorted(oid for oid in common if before[oid][0] != after[oid][0]),
                role_switch=sorted(oid for oid in common if before[oid][1] != after[oid][1]),
                unchanged=sorted(oid for oid in common if before[oid] == after[oid]))


def summaries(owner_map, signed):
    groups = defaultdict(list)
    for oid, (norad, role) in owner_map.items():
        row = signed[oid]
        groups[norad, role, row["receiver"], row["channel"], row["rf_hz"]].append(dict(id=oid, **row))
    result = []
    for (norad, role, receiver, channel, rf), subset in sorted(groups.items()):
        selected = sorted(subset, key=lambda row: (row["time_s"], row["id"]))
        result.append(dict(norad=norad, role=role, receiver=receiver, channel=channel, rf_hz=rf, count=len(selected),
                           time_s=[selected[0]["time_s"], selected[-1]["time_s"]],
                           visits=[selected[0]["visit_index"], selected[-1]["visit_index"]],
                           signed_cfo_hz=[min(row["signed_cfo_hz"] for row in selected),
                                          max(row["signed_cfo_hz"] for row in selected)],
                           observations=selected))
    return result


def published(directory):
    terminal, = directory.glob("fast-scan-automatic-work/*/terminal.json")
    detector, = directory.glob("fast-scan-automatic-work/*/detections.json")
    manifest, = directory.glob("fast-scan-standard-v2/*/final-error-v7/manifest.json")
    native, target, details = load(detector, PINS["native"]), load(terminal), load(manifest)
    path = load(manifest.with_name("position-path.json"))
    grid = load(manifest.with_name("position-grid.json"))
    digests = {kind: artifact["sha256"] for kind, artifact in (("path", path), ("grid", grid))}
    if (canonical(target) != details["terminal_sha256"] or target["native_sha256"] != canonical(native)
            or any(canonical(artifact["document"]) != digests[kind] for kind, artifact in (("path", path), ("grid", grid)))
            or native["source"]["raw_recording_authority_digest"] != details["raw_authority"]):
        raise ValueError("Standard publication did not bind its terminal, source or sidecars")
    return dict(manifest=details, terminal=target, path=path["document"], grid=grid["document"], digests=digests)


def run():
    prior = load(AUDIT, PINS["audit"])
    native = load(PAIR / "named-detections.json", PINS["native"])
    stock, candidate = (load(path / "joint-research-receipt.json", PINS[mode])
                        for mode, path in (("stock", PAIR / "stock"), ("cumulative", CONFIRMED)))
    workers = {mode: load(path / "saved-0160-worker.json", PINS[mode+"_worker"])
               for mode, path in (("stock", PAIR / "stock"), ("cumulative", CONFIRMED))}
    for mode, receipt in (("stock", stock), ("cumulative", candidate)):
        worker = workers[mode]
        if (worker["receipt"] != receipt["receipt"] or worker["solve"] != receipt["solve"]
                or worker["native_sha256"] != PINS["native"] or not worker["no_waveform"] or worker["handoffs"] != 1):
            raise ValueError("The forensic join requires one verified same-input saved handoff")
    before, first, after = (published(root) for root in (PAIR / "stock", PAIR / "cumulative", CONFIRMED))
    if (any(first[key] != after[key] for key in ("manifest", "terminal", "path"))
            or {k: v for k, v in first["grid"].items() if k != "elapsed_seconds"}
            != {k: v for k, v in after["grid"].items() if k != "elapsed_seconds"}):
        raise ValueError("Corrected trace changed the original cumulative publication")
    signed, arm_reports = observations(native), {}
    for arm in ARMS:
        prev, new = (owners(receipt["selected_rows"][arm]) for receipt in (stock, candidate))
        for table, product, receipt in ((prev, before, stock), (new, after, candidate)):
            record = product["manifest"]["arms"][arm]
            if (len(table) != record["associated_points"] or canonical({k: v[0] for k, v in table.items()}) != record["owner_sha256"]
                    or canonical(product["terminal"]) != receipt["receipt"]["terminal_sha256"]
                    or not table.keys() <= signed.keys()):
                raise ValueError("Ordered rows do not replay published ownership or signed support")
        delta = transitions(prev, new)
        removed = summaries({oid: prev[oid] for oid in delta["removed"]}, signed)
        for group in removed:
            group["component"] = LOST_COMPONENTS[group["norad"], group["receiver"], group["channel"]]
        arm_reports[arm] = dict(before_count=len(prev), after_count=len(new), delta=delta, removed=removed,
                                before_roles=dict(Counter(role for _, role in prev.values())),
                                after_roles=dict(Counter(role for _, role in new.values())),
                                start={mode: node["path"]["stages"][-1]["arms"][arm]["rounds"][0]["points"][0]
                                       for mode, node in (("stock", before), ("cumulative", after))},
                                end={mode: node["path"]["stages"][-1]["arms"][arm]["endpoint"]
                                     for mode, node in (("stock", before), ("cumulative", after))})
    if arm_reports["c0"]["delta"] != arm_reports["fitted_c"]["delta"]:
        raise ValueError("Ownership transitions differ across calibration arms")
    trace = candidate["route_details"]
    return dict(pins=PINS, original_audit=prior["status"], native_authority=native["source"]["raw_recording_authority_digest"],
                terminal_sha256={mode: receipt["receipt"]["terminal_sha256"] for mode, receipt in (("stock", stock), ("cumulative", candidate))},
                accuracy={mode: {k: row[k] for k in ("horizontal_error_km", "rf_rms_hz")} for mode, row in prior["runs"].items()},
                arms=arm_reports, stock_solve=stock["solve"], candidate_solve=candidate["solve"],
                candidate_trace=trace, recovered_inference=candidate["recovered_inference"],
                candidate_early_regional=candidate["early_regional"],
                pinned_figures={mode: next(row for row in node["manifest"]["artifacts"] if row["name"] == "track-rms")
                                for mode, node in (("stock", before), ("cumulative", after))})


if __name__ == "__main__":
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("output", type=Path)
    with options.parse_args().output.open("x") as stream:
        json.dump(run(), stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
