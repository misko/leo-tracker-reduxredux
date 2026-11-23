"""Run witnessed southern fits and dense nominal geometry for fixed RF epochs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from aperture_trial import archive_identity, configuration, inputs, machine, read, write
from arc_design import geometry_rows
from arc_design_trial import fit, labels, opportunity_rows, retained
from mixture_trial import elapsed
from owner_union_trial import owner_mask
from radio_epoch import blocks, select


CASES = ("south-containing", "south-far", "DS30-0008")
HERE = Path(__file__).resolve().parent
FAMILY_SHA = "481efa5fd7193da4fee69bdd4426d11668f3c9a31e8c0814ae8a44e644d553ca"


def checked_family(case, identity, solution):
    content = (HERE / "measurements/arc-design.json").read_bytes()
    if sha256(content).hexdigest() != FAMILY_SHA:
        raise ValueError("The previous shared-nuisance design has changed")
    earlier = json.loads(content)["cases"][case]
    nominal = earlier["design"]["nominal"]
    if earlier["identity"] != identity or not np.allclose(
            nominal["full"]["information"], solution["full_information"], rtol=1e-8, atol=1e-9):
        raise ValueError("The radio epoch benchmark must have the same original owner information")
    return nominal["frontier"]["3"]


def design(prepared, region, bound, native, full_tracks, roles, opportunities, case, identity):
    from blind_joint_finish import digest
    from tools.pipeline_eval.variants import v5_core

    stage = retained(prepared, full_tracks, roles, refit=False)
    scan = v5_core.scan_context(stage, region, digest(stage["noise"]), bound, "genuine_previous")
    source = native["source"]
    probes = source["probes"]
    start = native["clock_anchor"]["sample_counter"]
    original_ids = [oid for row in scan.tracks for oid in row["observation_ids"]]
    owner_indices = [opportunities[oid][0] for oid in original_ids]
    choices = blocks(probes, start, native["last_sample_counter"] - start, owner_indices)
    designs = [matrix for _, _, _, matrix in geometry_rows(scan, roles)]
    solution = select(choices, designs, len(probes) // 3)
    solution["whole_families"] = checked_family(case, identity, solution)
    chosen = [choices[i] for i in solution["best"]["indices"]] if solution["best"] is not None else []
    return dict(selection=solution, block_keys=[block.key for block in chosen],
                core_indices=sorted(set().union(*(b.core for b in chosen))),
                paid_indices=sorted(set().union(*(b.paid for b in chosen))))


def fit_memberships(full, owner_map, aliases, kept):
    from survey_owner_oracle import restrict

    owners = {oid: row for oid, row in owner_map.items() if oid in kept}
    tracks, roles, details = restrict(full, owners, aliases)
    curved = {description["norad"] for description in details
              if description["role"] == "conditional" and not description["issues"]}
    for description in details:
        if description["role"] == "predictive" and description["norad"] not in curved:
            description["issues"].append("no_eligible_curved_support")
    good = [i for i, row in enumerate(details) if not row["issues"]]
    selected_tracks = [tracks[i] for i in good]
    selected_roles = [roles[i] for i in good]
    selected_owners = {oid: owners[oid] for track in selected_tracks for oid in track["observation_ids"]}
    audit = {
        "owned_rows": len(owners), "owned_arcs": len(tracks), "can_fit_every_original_owner": len(good) == len(tracks),
        "witnessed_rows": len(selected_owners), "witnessed_arcs": len(good),
        "rejected": [row for row in details if row["issues"]],
        "role_counts": dict(Counter(role for _, role in owners.values())),
        "eligible_role_counts": dict(Counter(role for _, role in selected_owners.values())),
    }
    return selected_tracks, selected_roles, selected_owners, audit


def source_plan(path, authority):
    document = read(path)
    if document["identity"] != authority:
        raise ValueError("The radio epoch design must replay the sealed waveform")
    return document["plan"]


def geometry_fit(case, output, *, design_path=None):
    publication, spec = configuration()
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from survey_owner_oracle import restrict

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or set(host["threads"].values()) != {"1"}):
        raise ValueError("Expected one low-priority Gauss core")
    native, archive, offer, stock, identity = inputs(case)
    authority, authority_case = identity, case
    if case == "south-far":
        _, _, _, stock, authority = inputs("south-containing")
        authority_case = "south-containing"
        if authority["native_sha256"] != identity["native_sha256"]:
            raise ValueError("The paired offers must bind the same native packet")
    owner_map, aliases = labels(authority_case, authority, stock)
    opportunities = opportunity_rows(native, owner_map)
    override = None if design_path is None else source_plan(design_path, authority)
    if (case == "south-far") != (override is not None):
        raise ValueError("Only the omitted offer reuses a sealed containing design")
    result = {}

    def analyze(_recording, _root, assets, archive_root, region):
        reader = TleArchiveReader(archive_root)

        def diagnose(prepared, region, bound, _stages, *, selected_evidence):
            if prepared["status"] != "inputs_prepared":
                raise ValueError(f"Original prepared packet failed: {prepared['status']}")
            started = (process_time(), perf_counter())
            plan = override
            if plan is None:
                tracks, roles, _ = restrict(prepared["tracks"], owner_map, aliases)
                plan = design(prepared, region, bound, native, tracks, roles, opportunities, case, identity)
            core = set(plan["core_indices"])
            selected = {oid for oid, (i, _, _) in opportunities.items() if i in core}
            tracks, roles, owners, audit = fit_memberships(prepared["tracks"], owner_map, aliases, selected)
            result.update(plan=plan, feasibility=audit, design_and_audit_clocks=elapsed(*started),
                          paid_sha256=canonical_digest(plan["paid_indices"]), core_sha256=canonical_digest(plan["core_indices"]))
            if case == "DS30-0008" or not owners:
                result.update(status="frontier_only" if case == "DS30-0008" else "no_witnessed_fit",
                              reason=None)
                return {}
            started = (process_time(), perf_counter())
            stage = retained(prepared, tracks, roles, refit=True)
            try:
                result.update(fit(stage, region, bound, reader, owners, roles, result))
            except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                result.update(status="fixed_owner_fit_error", reason=f"{type(exc).__name__}: {exc}")
            result["cold_fit_clocks"] = elapsed(*started)
            return {}

        started = (process_time(), perf_counter())
        with patch.object(v5_core, "infer", diagnose):
            algo08_position.solve(native, reader, assets, region)
        result["all_saved_clocks"] = elapsed(*started)
        return {}

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        region_path = scratch / "offer.json"
        write(region_path, offer)
        destination = scratch / "output"
        destination.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=destination, archive=archive, region=region_path)
        with patch.object(algo08_scan, "analyze", analyze):
            publication.run(args, spec)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The causal archive changed during the saved replay")
    write(output, dict(case=case, identity=identity, authority=authority, host=host,
                       driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       selection_sha256=sha256((HERE / "radio_epoch.py").read_bytes()).hexdigest(), **result))


def project(native, plan):
    from leo.contracts.digests import canonical_digest

    probes = native["source"]["probes"]
    core, paid = set(plan["core_indices"]), set(plan["paid_indices"])
    if len(paid) > len(probes) // 3 or not core <= paid or not paid <= set(range(len(probes))):
        raise ValueError("The blind replay requires the original paid core mask")
    factor_indices = {i for i in core if probes[i]["candidates"]}
    packet = owner_mask(native, factor_indices)
    return packet, dict(core_lanes=len(core), paid_lanes=len(paid),
                        paid_visits=len({probes[i]["visit_index"] for i in paid}),
                        original_lanes=len(probes), original_visits=native["provenance"]["window_count"],
                        retained_factors=len(factor_indices), packet_digest=canonical_digest(packet),
                        core_sha256=canonical_digest(sorted(core)), paid_sha256=canonical_digest(sorted(paid)))


def blind(case, output, design_path):
    from rf_block_trial import run

    if case == "DS30-0008":
        raise ValueError("The dense screen is geometry and published-witness feasibility only")

    def apply(native):
        from leo.contracts.digests import canonical_digest

        sealed = read(design_path)
        if sealed["case"] != "south-containing" or sealed["identity"]["native_sha256"] != canonical_digest(native):
            raise ValueError("Blind solver must reuse the containing design's waveform")
        return project(native, sealed["plan"])

    run(case, output, project=apply)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="method", required=True)
    for method in ("geometry-fit", "blind"):
        parser = sub.add_parser(method)
        parser.add_argument("case", choices=CASES)
        parser.add_argument("output", type=Path)
        parser.add_argument("--design-path", type=Path, required=method == "blind")
    args = vars(cli.parse_args())
    method = args.pop("method")
    (geometry_fit if method == "geometry-fit" else blind)(**args)
