"""Observe actual installed Graph and fitted Doppler geometry during a dwell solve."""

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch


def run(root: Path):
    sys.path.insert(0, str(root))
    import numpy as np
    from leo.analysis.localization_v3 import family_cavity, signed_context

    from leo.application import localization_v3
    from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

    observed = {}

    def store():
        Path("geometry.json").write_text(json.dumps(observed, allow_nan=False) + "\n")

    def capture_graph(operation):
        def wrapped(*args, **kwargs):
            prepared = operation(*args, **kwargs)
            tracks = prepared["tracks"]
            spans = [float(np.ptp(t["times"])) for t in tracks["tracks"]]
            observed.update(
                graph_status=tracks["status"],
                winning=len(tracks["observations"]),
                assigned=tracks["graph_points"],
                tracks=len(spans),
                active_curvature=len(tracks["curved_indices"]),
                longest_s=max(spans, default=None),
                sky_catalogue_candidates=len(prepared["sky"]["bank"]["norad"])
                if prepared["status"] == "inputs_prepared"
                else None,
            )
            store()
            return prepared

        return wrapped

    def geometry(scan, arms, label):
        by_key = {t["key"]: t for t in scan.tracks}
        bank = scan.sky
        measures = {}
        for arm, saved in arms.items():
            lat, lon = saved["endpoint_latlon"]
            observer = geodetic_to_ecef_km(lat, lon, 0)
            horizontal = ecef_to_enu_matrix(lat, lon)[:2].T
            ordered = []
            satellites = set()
            for match in saved["gates"]["tracks"]:
                if not match["compatible"]:
                    continue
                t = by_key[match["component"]]
                valid = set(match["observation_ids"])
                times = [
                    s for i, s in zip(t["observation_ids"], t["times"], strict=True) if i in valid
                ]
                if not times:
                    continue
                j = match["candidate_index"]
                satellites.add(int(match["norad"]))
                coords = [
                    np.stack(
                        [
                            np.interp(times, bank["time_s"], bank[k][j, :, axis])
                            for axis in range(3)
                        ],
                        axis=1,
                    )
                    for k in ("position_km", "velocity_km_s")
                ]
                dp = coords[0] - observer
                distances = np.linalg.norm(dp, axis=1)
                los = dp / distances[:, None]
                v = coords[1] - np.sum(coords[1] * los, axis=1)[:, None] * los
                sensitivity = (v / distances[:, None]) @ horizontal * t["rf_hz"] / 299792.458
                ordered.append(sensitivity - sensitivity.mean(axis=0))
            singular = (
                np.linalg.svd(np.vstack(ordered), compute_uv=False).tolist() if ordered else []
            )
            measures[arm] = dict(
                norads=sorted(satellites),
                compatible_tracks=len(ordered),
                centered_doppler_singular_hz_km=singular,
            )
        observed.update(geometry_stage=label, arms=measures)
        store()

    def capture_signed(operation):
        def wrapped(*args, **kwargs):
            result = operation(*args, **kwargs)
            geometry(result["scan"], result["arms"], "signed")
            return result

        return wrapped

    def capture_cavity(operation):
        def wrapped(context, nominations):
            result = operation(context, nominations)
            if result["status"] == "complete":
                geometry(context["scan"], result["policy_arms"], "cavity")
            return result

        return wrapped

    with (
        patch.object(
            localization_v3,
            "prepare_native_scan",
            capture_graph(localization_v3.prepare_native_scan),
        ),
        patch.object(
            signed_context, "signed_context", capture_signed(signed_context.signed_context)
        ),
        patch.object(family_cavity, "cavity_policy", capture_cavity(family_cavity.cavity_policy)),
    ):
        runpy.run_path(str(root / "__main__.py"), run_name="__main__")


if __name__ == "__main__":
    run(Path(Path("receiver-path.txt").read_text().strip()))
