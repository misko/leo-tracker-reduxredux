"""Measure a cold mixture, one original finish, and a checked installed-v3 fallback."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, write


CASES = ("DS30-0008", "south-containing", "south-far")


def elapsed(cpu, wall):
    return dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall)


def summarize(decision, packet, policy):
    from leo.contracts.digests import canonical_digest

    result = dict(status=decision["status"], reason=decision.get("reason"), orbit_policy=policy,
                  arms=decision["arms"], science={})
    if packet is None:
        return result, {}
    summaries = packet["arms"]
    result.update(
        science={name: canonical_digest({k: v for k, v in packet[f"position_{name}"].items()
                                        if k not in ("binding", "elapsed_seconds")})
                 for name in ("path", "grid")},
        owners={arm: summaries[arm]["owner_sha256"] for arm in ARMS},
        associated={arm: summaries[arm]["associated_points"] for arm in ARMS},
        objective_replay=packet["objective_replay"], grid_points=packet["position_grid"]["evaluated_points"],
    )
    return result, {arm: {r["observation_id"]: r["norad"] for r in packet["rows"][arm]} for arm in ARMS}


def audit(proposal, baseline):
    """All-data owner labels enter only after storing the cold prediction."""
    if proposal["status"] != "complete" or not baseline:
        return None
    catalogue = set(proposal["catalogue"])
    result = {}
    common = {key: row for row in proposal["arms"]["c0"]["tracks"] for key in row["observations"]}
    for arm, complete in baseline.items():
        by_id = {key: row for row in proposal["arms"][arm]["tracks"] for key in row["observations"]}
        joined = [(key, owner, by_id[key]) for key, owner in complete.items() if key in by_id]
        result[arm] = dict(
            baseline_owned=len(complete), curved_owned=len(joined),
            causal_catalogue_upper_bound=sum(o in catalogue for _, o, _ in joined),
            all_nodes_top_eight_oracle_upper_bound=sum(o in row["region_union"] for _, o, row in joined),
            endpoint_top_eight_oracle_upper_bound=sum(o in row["shortlist"] for _, o, row in joined),
            arm_member_owner_match=sum(row["retained"] and o == row.get("norad") for _, o, row in joined),
            common_mask_owner_match=sum(common[k]["retained"] and o == common[k].get("norad")
                                        for k, o, _ in joined),
            common_mask_different_owner=sum(common[k]["retained"] and o != common[k].get("norad")
                                            for k, o, _ in joined),
        )
    return result


def trial(case, output):
    publication, spec = configuration()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    import numpy as np
    from mixture_finish import finish
    from mixture_position import propose

    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("Saved input detector differs from installed v3")
    observations = []

    def analyze(_recording, _root, assets, archive_root, region):
        stock_infer = v5_core.infer

        def route(prepared, search_region, bound, stage_s, *, selected_evidence=None):
            measured = {}
            observations.append(measured)
            cpu, wall = process_time(), perf_counter()
            try:
                proposal = propose(prepared, search_region)
            except (AssertionError, ValueError, np.linalg.LinAlgError) as error:
                proposal = dict(status="proposal_error", reason=str(error), arms={})
            measured.update(proposal=proposal, proposal_clocks=elapsed(cpu, wall))
            cpu, wall = process_time(), perf_counter()
            try:
                validation, signed = finish(prepared, search_region, bound, proposal)
                if signed is not None:
                    selected_evidence(prepared, signed, None)
            except (AssertionError, ValueError, np.linalg.LinAlgError) as error:
                validation, signed = dict(decision="fallback", reasons=["validation_error"], detail=str(error)), None
            measured.update(finish=validation, finish_clocks=elapsed(cpu, wall))
            if signed is not None:
                return dict(status="ok", reason=None, metrics=stage_s, arms={
                    a: {key: validation["arms"][a][key] for key in ("latlon", "rf_rms_hz")} for a in ARMS
                })
            cpu, wall = process_time(), perf_counter()
            try:
                return stock_infer(prepared, search_region, bound, stage_s, selected_evidence=selected_evidence)
            finally:
                measured["fallback_clocks"] = elapsed(cpu, wall)

        cpu, wall = process_time(), perf_counter()
        with patch.object(v5_core, "infer", route):
            chosen = algo08_position.solve(native, TleArchiveReader(archive_root), assets, region)
        candidate_clocks = elapsed(cpu, wall)
        result, owners = summarize(*chosen)
        if "fallback_clocks" in observations[-1]:
            control, control_owners = result, owners
            control_clocks = None
        else:
            cpu, wall = process_time(), perf_counter()
            control, control_owners = summarize(*algo08_position.solve(native, TleArchiveReader(archive_root), assets, region))
            control_clocks = elapsed(cpu, wall)
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if control.get(key) != expected.get(key):
                raise ValueError(f"Checked ALGO08v3 {key} differs from the archived decision")
        oracle = audit(observations[-1]["proposal"], control_owners)
        comparison = {arm: dict(
            shared=len(rows.keys() & control_owners.get(arm, {}).keys()),
            replaced=sum(rows[key] != control_owners[arm][key] for key in rows.keys() & control_owners.get(arm, {}).keys()),
        ) for arm, rows in owners.items()}
        return dict(result=result, candidate_clocks=candidate_clocks, control=control,
                    control_clocks=control_clocks, attempts=observations, oracle=oracle, owner_comparison=comparison)

    with TemporaryDirectory() as work:
        scratch = Path(work)
        offer_file = scratch / "offer.json"
        offer_file.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=offer_file)
        with patch.object(algo08_scan, "analyze", analyze):
            data = publication.run(args, spec)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    data.update(identity=identity, machine=machine(), source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    trial(**vars(parser.parse_args()))
