"""Reconstruct one selected genuine native context and test only a 24-call grid slice."""

import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

import numpy as np

from aperture_trial import configuration, inputs, read, solve, write
from cold_track_row_trial import REPLAY_PIN
from cold_track_row_transfer import DENSE, GEOGRAPHIC, PREVIOUS, RAW
from dense_full_short_crossover import CASE, HERE, OWNER_KEYS, TRACK_ASSET_PIN, file_sha
from dense_geographic_trial import elapsed, host, now
from grid_neighbor_gamma import Compare, build, score_rows


COLD = HERE / "measurements/cold-track-row-reuse.json.gz"
COLD_PIN = "27baf73f3eb1ccf8293b847fdc482b41dd8ad6cf249a3f503b8c8e81d5325692"


def cold_witness(prepared, region, bound, branch, original):
    from blind_joint_finish import digest
    from leo.analysis.localization_v3.discovery import signature, zero_state
    from tools.pipeline_eval.variants import v5_core

    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    witnesses = {name: (candidate, norad, alias) for name, candidate, norad, alias in branch["selected_signature"]}
    rows, aliases = [], []
    for index in scan.curved:
        track = scan.tracks[index]
        key = track["key"]
        j, norad, alias = witnesses[key]
        if int(scan.norads[j]) != norad:
            raise ValueError("The preserved cold node uses a different causal catalogue order")
        rows.append(dict(component=key, candidate_index=j, candidate_norad=norad, active_curvature=True))
        aliases.append(alias)
    node = dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=aliases)
    if list(map(list, signature(node))) != branch["selected_signature"]:
        raise ValueError("The cold assignment witness changed")
    return node, np.asarray(branch["east_north_km"]), {int(k): v for k, v in branch["reference"].items()}, original


def reconstruct(observer):
    """Rebuild the checked selected fit and let the caller sample the original objective."""
    publication, specification = configuration()
    from blind_joint_repair import repair_once
    from certified_salvage import propose
    from lighter_joint_estimator import update
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from leo.presentation import localization_v3 as presentation
    from tools.pipeline_eval.variants import v5_core

    start = now()
    if file_sha(DENSE) != REPLAY_PIN or file_sha(COLD) != COLD_PIN:
        raise ValueError("The sealed chosen context or original full grid changed")
    baseline = read(DENSE)
    old = baseline["attempts"][0]
    witness = json.loads(gzip.decompress(COLD.read_bytes()))
    cold = witness["pair"]["released"]["branch"]
    archived = PREVIOUS / "reports/ALGO08/v3/dense_full_short_crossover.py"
    if file_sha(archived) != baseline["code"][archived.name]:
        raise ValueError("The original dense source verifier changed")
    original, archive, offer, _, identity = inputs(CASE)
    native, evidence = run_path(str(archived))["raw_candidate"](
        RAW / "publication", RAW / "process.json", GEOGRAPHIC, original, identity)
    if (witness["input_sha256"] != evidence["raw_native_sha256"] or witness["offer"] != offer
            or any(cold[key] != old["cold"][key] for key in ("branch", "scores", "east_north_km", "overlap"))):
        raise ValueError("The chosen cold witness does not bind this checked dense control")
    source_clock = elapsed(start)
    measured = observer(baseline["grid"])
    old_solve, old_prepare = algo08_position.solve, algo08_position.prepare_packet
    observation, attempt = {}, {}

    def remember(context, *args, **kwargs):
        measured.context = context
        clock = now()
        packet = old_prepare(context, *args, **kwargs)
        observation["evidence_slice_clock"] = elapsed(clock)
        observation["owners"] = {arm: [[r[key] for key in OWNER_KEYS] for r in rows] for arm, rows in packet["rows"].items()}
        return packet

    def observed(document, reader, assets, region):
        if document is not native or reader.root != archive or region.document() != offer or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN:
            raise ValueError("The frozen saved input, catalogue, offer or graph changed")
        entered = now()

        def infer(prepared, region, bound, _stages, *, selected_evidence):
            if prepared["status"] != "inputs_prepared":
                raise ValueError("The selected solve inputs could not be reconstructed")
            observation["preparation"] = elapsed(entered)
            timer = now()
            frozen_start = lambda p, r, b: cold_witness(p, r, b, cold, old["cold"])
            ordinary, reason = propose(prepared, region, bound, attempt, repair=repair_once,
                                       certified=True, cold_start=frozen_start)
            if ordinary is None:
                raise ValueError(f"Frozen cold witness did not rebuild the selected support: {reason}")
            signed = update(prepared, ordinary, attempt)
            observation["frozen_context_reconstruction"] = elapsed(timer)
            selected_evidence(prepared, signed, None)
            return dict(status="ok", reason=None, arms={arm: dict(latlon=list(r["endpoint_latlon"]),
                        rf_rms_hz=float(r["RMS_hz"])) for arm, r in signed["arms"].items()})

        with ExitStack() as stack:
            stack.enter_context(handoff(reader))
            stack.enter_context(reduced_grid())
            stack.enter_context(patch.object(algo08_position, "prepare_packet", remember))
            stack.enter_context(patch.object(v5_core, "infer", infer))
            return old_solve(document, reader, assets, region)

    with (patch.object(algo08_position, "solve", observed),
          patch.object(presentation, "sample_position_grid", measured.sample)):
        result = solve(publication, specification, native, archive, offer)
    checks = dict(owners=observation.pop("owners") == baseline["selected_rows"], arms=result["arms"] == baseline["arms"],
                  path=result["science"]["path"] == baseline["science"]["path"],
                  objective_replay=result["objective_replay"] == baseline["objective_replay"])
    return dict(checks=checks, clocks=observation, source_read=source_clock, cold_witness_sha256=COLD_PIN,
                dense_baseline_sha256=REPLAY_PIN, input_sha256=evidence["raw_native_sha256"]), attempt


def run(output):
    machine = host()
    setup = {}

    def observer(grid):
        output.mkdir(exist_ok=False)
        start = now()
        setup["binary"] = build(output)
        setup["clock"] = elapsed(start)
        setup["measured"] = Compare(setup["binary"], grid)
        return setup["measured"]

    reconstruction, attempt = reconstruct(observer)
    measured = setup["measured"]
    write(output / "slice.json", dict(rows=measured.rows, clock=reconstruction["clocks"], attempt=attempt))
    empirical = score_rows(measured.rows)
    checks = reconstruction["checks"]
    checks["score_and_factor"] = all(a["archived_stock_exact"] and a["all_checked"] for a in empirical.values())
    paths = (Path(__file__), HERE / "grid_neighbor_gamma.py", HERE / "grid-neighbor-gamma-protocol.md", setup["binary"],
             output / "neighbor.c", output / "stock-build.c", output / "slice.json")
    write(output / "report.json", dict(**reconstruction, measurements=empirical, build=setup["clock"], host=machine,
          files={path.name: file_sha(path) for path in paths}))
    if not all(checks.values()):
        raise ValueError(f"The selected witness failed exact control replay: {checks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
