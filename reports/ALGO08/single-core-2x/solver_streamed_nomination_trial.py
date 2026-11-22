"""Isolate moment proposal discrepancies and time exact full-data nomination."""

import argparse
import json
from collections import Counter
from contextlib import nullcontext
from functools import partial
from hashlib import sha256
from itertools import product
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import discovery, position
from leo.analysis.research.retained_track_likelihood import profile
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, algo08_track_moments, v5_core
from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
from tools.pipeline_eval.variants.algo08_streamed_nomination import streamed_nomination


def receipt(path, native_digest):
    saved = json.loads(path.read_bytes())
    if saved["native_sha256"].removeprefix("sha256:") != native_digest:
        raise ValueError("Saved assignments are from a different detector input")
    return {row[0]: tuple(row[1:]) for row in saved["initial"]["selected_signature"]}


def audit_moments(scan, stock, moments):
    changed = {key for key in stock if stock[key] != moments[key]}
    radius = scan.search_region.half_width_km
    details = []
    for anchor in [(0., 0.), *product((-radius, radius), repeat=2)]:
        frequency, elevation, _ = discovery.phase_linear_frequency(
            scan.geometry, *scan.search_region.latlon(anchor)
        )
        for i in scan.curved:
            track, indexes = scan.tracks[i], scan.index[i]
            key = track["key"]
            if key not in changed:
                continue
            time, y = track["times"], track["values"]
            q = track["rf_hz"] / discovery.REFERENCE_RF
            layout = algo08_track_moments.track_moments(time)
            nodes = np.searchsorted(time, layout.nodes)
            full = q * frequency[:, indexes]
            node = full[:, nodes]
            predicted = node @ (layout.basis @ layout.transfer).T
            exact_visible = elevation[:, indexes].min(axis=1) >= 0
            node_visible = elevation[:, indexes[nodes]].min(axis=1) >= 0
            stock_terms = profile(y, full, *scan.white[i])
            interpolated = profile(y, predicted, *scan.white[i])
            compressed = algo08_track_moments.profile(layout, y, node)

            def pick(terms, visible):
                index = int(np.argmin(np.where(visible, terms["cost"], np.inf)))
                return int(scan.norads[index])

            details.append(dict(
                anchor=anchor, track=key, saved_stock_label=stock[key][1],
                saved_moment_label=moments[key][1],
                stock=pick(stock_terms, exact_visible),
                interpolation=pick(interpolated, exact_visible),
                visibility=pick(stock_terms, node_visible),
                jointly=pick(interpolated, node_visible),
                moment=pick(compressed, node_visible),
                changed_visibility=int(np.count_nonzero(exact_visible != node_visible)),
                changed_alias_after_interpolation=int(np.count_nonzero(
                    stock_terms["alias"] != interpolated["alias"]
                )),
                maximum_moment_algebra_score_difference=float(np.max(
                    np.abs(interpolated["cost"] - compressed["cost"])
                )),
            ))
    return dict(changed_components=len(changed), conditional_nomination_rows=details)


def timed_rank(scan, method):
    clock = process_time()
    counters = Counter()
    scores = []
    residual = position.NormalPosition.residual

    def record(problem, point):
        values = residual(problem, point)
        scores.append(float(values @ values))
        return values

    scope = streamed_nomination(scan, counters) if method == "streamed" else nullcontext()
    with (
        scope,
        dense_discovery(scan, reuse_associations=True) as reuse,
        patch.object(position.NormalPosition, "residual", record),
    ):
        ranked = v5_core.ranked_initial_nodes(scan)
    elapsed = process_time() - clock
    c0, _ = v5_core.fit_initial_nodes(scan, ranked[:3])
    selected = c0["choices"][0]
    _, fitted, _ = position.refreshed(scan, scan.radio_sigma_hz, selected["node"], "fitted_c")
    return dict(
        cpu_s=elapsed, scores=scores, reuse=reuse, work=counters,
        ranked=[discovery.signature(node) for node in ranked],
        nominees=[[(row["cost"], row["rms_hz"], row["bias_hz"], row["compatible"])
                   for row in node["seed"]["rows"]] for node in ranked],
        c0_gate_sha256=sha256(json.dumps(selected["arms"], default=_json_value,
                                        sort_keys=True).encode()).hexdigest(),
        fitted=fitted,
    )


def run(native, archive, assets, region, mode, first, stock=None, moments=None):
    results = {}
    prepare = partial(
        algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={}
    )

    def infer(prepared, search, bound, stages, **options):
        if prepared["status"] != "inputs_prepared":
            raise ValueError(prepared["status"])
        noise = sha256((json.dumps(prepared["noise"], sort_keys=True) + "\n").encode()).hexdigest()

        def context():
            return v5_core.scan_context(prepared, search, noise, bound, "previous")

        if mode == "audit":
            results.update(audit_moments(context(), stock, moments))
        else:
            second = "control" if first == "streamed" else "streamed"
            for method in (first, second, second, first):
                results.setdefault(method, []).append(timed_rank(context(), method))
            reference = results["control"][0]
            for trial in [*results["control"], *results["streamed"]]:
                for key in ("scores", "ranked", "nominees", "c0_gate_sha256"):
                    if trial[key] != reference[key]:
                        raise ValueError(f"Full-data discovery changed {key}")
                if json.dumps(trial["fitted"], default=_json_value) != json.dumps(
                    reference["fitted"], default=_json_value
                ):
                    raise ValueError("Exact fitted-c initial refinement changed")
        return dict(status="initial_trial_complete")

    with (
        patch.object(algo08_position, "prepare_native_scan", prepare),
        patch.object(v5_core, "infer", infer),
    ):
        _, _, results["orbit_policy"] = algo08_position.solve(native, archive, assets, region)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("audit", "rank"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--stock", type=Path)
    parser.add_argument("--moments", type=Path)
    parser.add_argument("--first", choices=("control", "streamed"), default="control")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    stock = receipt(args.stock, digest) if args.mode == "audit" else None
    moments = receipt(args.moments, digest) if args.mode == "audit" else None
    report = run(json.loads(raw), TleArchiveReader(args.archive), args.assets,
                 offer, args.mode, args.first, stock, moments)
    print(json.dumps(dict(report, native_sha256=digest, region=offer.document()),
                     default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
