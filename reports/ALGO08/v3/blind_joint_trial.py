"""Measure a blind joint finish under the installed ALGO08v3 evidence and veto."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, write
from mixture_trial import CASES, elapsed, summarize


def publication_roles(packet):
    return {} if packet is None else {
        arm: dict(Counter(row["role"] for row in rows)) for arm, rows in packet["rows"].items()
    }


def trial(case, output, *, repair=False):
    publication, spec = configuration()
    import numpy as np
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from blind_joint_finish import propose
    from blind_joint_repair import repair_once

    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("The saved receiver packet differs from the released binary")
    attempts = []

    def analyze(_recording, _root, assets, archive_root, region):
        installed = v5_core.infer
        reader = TleArchiveReader(archive_root)

        def route(prepared, search_region, bound, stages, *, selected_evidence=None):
            observed = {}
            attempts.append(observed)
            cpu, wall = process_time(), perf_counter()
            try:
                signed, reason = propose(prepared, search_region, bound, observed, repair=repair_once if repair else None)
            except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                signed, reason = None, f"{type(exc).__name__}: {exc}"
            observed["candidate_pre_evidence_clocks"] = elapsed(cpu, wall)
            if signed is not None:
                cpu, wall = process_time(), perf_counter()
                endpoints = {key: record["endpoint_east_north_km"] for key, record in signed["arms"].items()}
                exterior = regional_bound_guard.inspect_boundary(
                    endpoints, search_region.width_km,
                    lambda: regional_bound_guard.causal_probes(prepared["tracks"], reader, search_region,
                                                               terminal_only=True), terminal_only=True,
                )
                observed.update(exterior=exterior, exterior_clocks=elapsed(cpu, wall))
                if exterior["would_withhold"]:
                    observed["decision"] = "withheld"
                    return dict(status="withheld", reason="both_receivers_support_far_exterior", metrics=stages,
                                arms={arm: {"latlon": None} for arm in ARMS})
                if exterior.get("diagnostic_error"):
                    reason = "exterior_evidence_unavailable"
                else:
                    cpu, wall = process_time(), perf_counter()
                    try:
                        if repair:
                            packet_builder = algo08_position.selected_packet

                            def complete_packet(*args, **kwargs):
                                packet = packet_builder(*args, **kwargs)
                                if not packet["position_grid"]["complete"]:
                                    raise ValueError("The original numerical evidence grid is incomplete")
                                return packet

                            with patch.object(algo08_position, "selected_packet", complete_packet):
                                selected_evidence(prepared, signed, None)
                        else:
                            selected_evidence(prepared, signed, None)
                    except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                        reason = f"standard_evidence: {type(exc).__name__}: {exc}"
                    finally:
                        observed["standard_evidence_clocks"] = elapsed(cpu, wall)
                if reason is None:
                    observed["decision"] = "complete"
                    return dict(status="ok", reason=None, metrics=stages, arms={arm: dict(
                        latlon=list(record["endpoint_latlon"]), rf_rms_hz=float(record["RMS_hz"])
                    ) for arm, record in signed["arms"].items()})
            observed.update(decision="fallback", reason=reason)
            cpu, wall = process_time(), perf_counter()
            try:
                return installed(prepared, search_region, bound, stages, selected_evidence=selected_evidence)
            finally:
                observed["fallback_clocks"] = elapsed(cpu, wall)

        cpu, wall = process_time(), perf_counter()
        with patch.object(v5_core, "infer", route):
            published = algo08_position.solve(native, reader, assets, region)
        charged = elapsed(cpu, wall)
        result, chosen_owners = summarize(*published)
        if attempts[-1]["decision"] == "fallback":
            control, stock_owners, stock_roles = result, chosen_owners, publication_roles(published[1])
            control_clocks = None
        else:
            cpu, wall = process_time(), perf_counter()
            baseline = algo08_position.solve(native, reader, assets, region)
            control_clocks = elapsed(cpu, wall)
            control, stock_owners = summarize(*baseline)
            stock_roles = publication_roles(baseline[1])
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if control.get(key) != expected.get(key):
                raise ValueError(f"Checked installed v3 {key} changed its archived result")
        changes = {}
        for arm in ARMS:
            before, after = stock_owners.get(arm, {}), chosen_owners.get(arm, {})
            shared = before.keys() & after.keys()
            changes[arm] = dict(shared=len(shared), lost=len(before.keys() - after.keys()),
                                new=len(after.keys() - before.keys()), changed=sum(before[k] != after[k] for k in shared))
        return dict(result=result, control=control, charged=charged, control_clocks=control_clocks,
                    attempts=attempts, published_roles=publication_roles(published[1]),
                    stock_roles=stock_roles, published_owner_changes=changes)

    with TemporaryDirectory() as work:
        scratch = Path(work)
        path = scratch / "offer.json"
        path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=path)
        with patch.object(algo08_scan, "analyze", analyze):
            data = publication.run(args, spec)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    data.update(identity=identity, machine=machine(), repair_enabled=repair,
                driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repair", action="store_true")
    trial(**vars(parser.parse_args()))
