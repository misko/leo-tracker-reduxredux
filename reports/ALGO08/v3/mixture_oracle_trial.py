"""Compare two label oracles while keeping the cold mixture and finish gates frozen."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, inputs, machine, write
from mixture_trial import CASES, elapsed, summarize


HERE = Path(__file__).resolve().parent
WITNESS = HERE / "measurements/mixture-position.json.gz"
WITNESS_SHA256 = "8988a733014b18f11dd805bb162b11e2118d320ea2fddcfdb2bc9708da155771"


def phase_packet(prepared, signed, algo08_position):
    from leo.analysis.localization_v3.reassociation_context import objective
    from leo.analysis.localization_v3.recovery_inventory import recovery_context
    from leo.presentation import localization_v3
    import numpy as np

    grid_calls = []
    sample = localization_v3.sample_position_grid

    def measured(*args, **kwargs):
        cpu, wall = process_time(), perf_counter()
        grid = sample(*args, **kwargs)
        grid_calls.append(dict(elapsed(cpu, wall), evaluated_points=grid["evaluated_points"],
                               status=grid.get("status")))
        return grid

    cpu, wall = process_time(), perf_counter()
    diagnostics = {}
    try:
        with patch.object(localization_v3, "sample_position_grid", measured):
            packet = algo08_position.selected_packet(prepared, signed, None)
        diagnostics.update(status="complete", owners={arm: data["owner_sha256"] for arm, data in packet["arms"].items()},
                           associated={arm: data["associated_points"] for arm, data in packet["arms"].items()},
                           objective_replay=packet["objective_replay"])
    except (ValueError, AssertionError) as error:
        diagnostics.update(status="rejected_evidence", reason=f"{type(error).__name__}: {error}")
    diagnostics["standard_evidence_clocks"] = elapsed(cpu, wall)
    if not grid_calls:
        # Compatibility belongs to the actual finish. Here we only measure
        # the numerical grid when the usual figure evidence stopped earlier.
        saved = dict(status="complete", accepted=False, baseline_node=signed["node"],
                     baseline_entries=signed["entries"], baseline_means=signed["means"],
                     original_mask=signed["keep"], powers=signed["powers"], model=signed["model"],
                     policy_arms=signed["arms"])
        cpu, wall = process_time(), perf_counter()
        try:
            context = recovery_context(signed["scan"], saved)
            context["families"] = []
            problems = context["problems"]
            measured(lambda arm, point: objective(problems[arm][0], context, np.asarray(point)),
                     {arm: list(x) for arm, (_, x) in problems.items()}, maximum_seconds=30,
                     box_width_km=signed["scan"].search_region.width_km)
        except (ValueError, AssertionError) as error:
            diagnostics["grid_error"] = f"{type(error).__name__}: {error}"
        diagnostics["diagnostic_grid_and_reconstruction_clocks"] = elapsed(cpu, wall)
    diagnostics["grid_calls"] = grid_calls
    return diagnostics


def run(case, output_directory):
    publication, spec = configuration()
    import numpy as np
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from mixture_finish import finish
    from mixture_oracle import MODES, capture_labels, frozen_at_endpoint, proposal_for

    raw = WITNESS.read_bytes()
    if sha256(raw).hexdigest() != WITNESS_SHA256:
        raise ValueError("The frozen mixture receipt changed")
    witness = json.loads(gzip.decompress(raw))["receipts"][case]
    native, archive, offer, expected, identity = inputs(case)
    if identity != witness["identity"]:
        raise ValueError("The archived blind proposal is bound to a different packet or offer")
    blind = witness["attempts"][0]
    proposal = blind["proposal"]
    results = {}

    def analyze(_recording, _root, assets, archive_root, region):
        original_infer = v5_core.infer
        original_packet = algo08_position.prepare_packet

        def capture(context, owners, *args, **kwargs):
            packet = original_packet(context, owners, *args, **kwargs)
            results["labels"] = capture_labels(context, packet)
            return packet

        def route(prepared, search_region, bound, stages, *, selected_evidence=None):
            if "oracle" in results:
                raise ValueError("Expected one stock orbital context")
            cpu, wall = process_time(), perf_counter()
            frozen = frozen_at_endpoint(prepared, search_region, proposal)
            results["frozen_endpoint_clocks"] = elapsed(cpu, wall)
            cpu, wall = process_time(), perf_counter()
            with patch.object(algo08_position, "prepare_packet", capture):
                control = original_infer(prepared, search_region, bound, stages, selected_evidence=selected_evidence)
            results["stock_inference_and_label_capture_clocks"] = elapsed(cpu, wall)
            labels = results.get("labels")
            if case == "south-far":
                cpu, wall = process_time(), perf_counter()
                transferred = (output_directory / "south-containing.json").read_bytes()
                previous = json.loads(transferred)
                for key in ("native_sha256", "raw_authority", "archive", "specification"):
                    if previous["identity"][key] != identity[key]:
                        raise ValueError(f"Cannot transfer same-packet oracle labels with changed {key}")
                if previous["control"]["status"] != "ok" or labels is not None:
                    raise ValueError("Expected a containing owner witness and omitted withholding")
                labels = previous["labels"]
                labels["curved"] = {key: tuple(pair) for key, pair in labels["curved"].items()}
                results["label_transfer"] = dict(source_sha256=sha256(transferred).hexdigest(),
                                                 clocks=elapsed(cpu, wall))
            if labels is None:
                raise ValueError("Expected exact accepted owner and alias evidence")
            results["oracle"] = {}
            for name in MODES:
                cpu, wall = process_time(), perf_counter()
                selected, masks, counts = proposal_for(proposal, frozen, labels, name)
                assignment = elapsed(cpu, wall)
                cpu, wall = process_time(), perf_counter()
                try:
                    report, signed = finish(prepared, search_region, bound, selected,
                                            observation_masks=masks, include_rejected=True)
                except (ValueError, AssertionError, np.linalg.LinAlgError) as error:
                    report, signed = dict(decision="fallback", reasons=["numerical_error"], detail=str(error)), None
                finish_clocks = elapsed(cpu, wall)
                numerical = None if signed is None else phase_packet(prepared, signed, algo08_position)
                results["oracle"][name] = dict(
                    counts=counts, retained_by_track=selected["arms"]["c0"]["tracks"],
                    assignment_clocks=assignment, finish=report, finish_clocks=finish_clocks,
                    numerical_evidence=numerical,
                )
            return control

        cpu, wall = process_time(), perf_counter()
        with patch.object(v5_core, "infer", route):
            control, _ = summarize(*algo08_position.solve(native, TleArchiveReader(archive_root), assets, region))
        results["entire_diagnostic_clocks"] = elapsed(cpu, wall)
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if control.get(key) != expected.get(key):
                raise ValueError(f"Stock label source changed its archived {key}")
        results.update(control=control, imported_blind_proposal_clocks=blind["proposal_clocks"],
                       original_alias_witness_sha256=canonical_digest(results.get("labels")),
                       imported_blind_match=witness["oracle"],
                       imported_blind_shared_prep_other_cpu_s=(witness["candidate_clocks"]["cpu_s"] - sum(
                           value["cpu_s"] for key, value in blind.items() if key.endswith("_clocks"))))
        return results

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
        raise ValueError("Causal archive changed during the diagnostic")
    data.update(identity=identity, machine=machine(), frozen_mixture_sha256=sha256(raw).hexdigest())
    write(output_directory / f"{case}.json", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output_directory", type=Path)
    run(**vars(parser.parse_args()))
