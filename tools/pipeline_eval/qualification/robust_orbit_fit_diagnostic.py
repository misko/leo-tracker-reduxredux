"""Post-fit ownership and range-rate audit for the locked anonymous-track receiver."""

import argparse
import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.variants import robust_em

DIAGNOSTIC = Path(__file__)
ARM = "fitted_c"


def key(rx, channel, sample_s, hz):
    return int(rx), int(channel), round(float(sample_s), 6), round(float(robust_em.fold(hz)), 3)


def exact_orbit(tile, track, orbit, phase, site):
    one = slice(orbit, orbit + 1)
    one_satellite = replace(
        tile, positions_km=tile.positions_km[one], velocities_km_s=tile.velocities_km_s[one]
    )
    position, velocity, _ = grid._interpolated_states(one_satellite, track.t + phase)
    # A phase changes the satellite epoch while the terrestrial clock remains fixed.
    angle = 7.29211514670698e-5 * phase
    turn = np.array(
        [[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]]
    )
    delta = position[0] @ turn.T - site
    vel = velocity[0] @ turn.T
    radial = (delta * vel).sum(axis=1) / np.linalg.norm(delta, axis=-1)
    return -track.rf / grid.LIGHT_SPEED_KM_S * radial


def inferred_trace(packet):
    from tools.pipeline_eval.variants.projected_fit import Region

    observation, offer = packet["observation"], packet["offer"]
    final = {}
    capture = {}
    original_fit = robust_em.fit
    original_valid = grid._valid_states
    original_make_tile = grid.make_tile

    def fitted(rows, n_orbits, half, arm):
        outcome = original_fit(rows, n_orbits, half, arm)
        if arm == ARM:
            final.update(rows=rows, outcome=outcome)
        return outcome

    def captured_valid(*args):
        result = original_valid(*args)
        capture["satellites"] = result[0]
        return result

    def captured_tile(*args):
        tile = original_make_tile(*args)
        capture["tile"] = tile
        return tile

    with (
        patch.object(robust_em, "fit", fitted),
        patch.object(grid, "_valid_states", captured_valid),
        patch.object(grid, "make_tile", captured_tile),
    ):
        result = robust_em.infer(observation, offer, packet["catalogue"])
    if not final.get("outcome"):
        return dict(result=result, rows=[])

    source = {}
    for i, row in enumerate(observation["tracks"]):
        lane = 2 * (row["receiver"] - 1) + int(row["channel"] > 4)
        for t, y in zip(row["times"], row["values"], strict=True):
            source.setdefault((lane, row["rf_hz"], t, y), (i, row["receiver"], row["channel"]))
    state = final["outcome"].state
    tile = capture["tile"]
    region = Region(offer["id"], tuple(offer["center"]), tile.ecef_center_km, tile.enu_frame)
    site = region.site(state.xy)[0]
    rows = []
    for row in final["rows"]:
        arc = row.arc
        tr = arc.track
        phase = state.phase[row.orbit]
        j = row.winner
        linear = tr.hz - arc.residual[j] + arc.xy[j] @ state.xy + arc.phase[j] * phase
        exact = exact_orbit(tile, tr, row.orbit, phase, site)
        radio = (
            state.bias[tr.lane]
            + tr.drift * state.drift[tr.lane]
            + (tr.rf / 1e9 - 11.5) * state.c_hz_per_ghz
            + row.alias * robust_em.PERIOD
        )
        n = capture["satellites"][row.orbit].satnum
        for t, y, before, after, gain in zip(tr.t, tr.hz, linear, exact, radio, strict=True):
            i, rx, channel = source[tr.lane, tr.rf, t, y]
            rows.append(
                dict(
                    track=i,
                    receiver=rx,
                    channel=channel,
                    time_s=t,
                    measured_cfo_hz=y,
                    norad=n,
                    fitted_phase_s=phase,
                    residual_hz=y - before - gain,
                    exact_residual_hz=y - after - gain,
                    geometry_delta_hz=after - before,
                )
            )
    return dict(result=result, rows=rows)


def published(case):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.full_v5_check import BULK, _load_case

    binding = _load_case(case)
    request = BULK / binding["request"]["path"]
    raw = request.read_bytes()
    digest = sha256(raw).hexdigest()
    expected_native = "sha256:" + binding["native"]["sha256"]
    request_data = json.loads(raw)
    if (
        digest != binding["request"]["sha256"]
        or request_data["job"]["native_input"]["sha256"] != expected_native
    ):
        raise ValueError("original v5 request is not bound to the matched native capture")
    receipt = request.parent.parent / "baseline-execution.json"
    raw_receipt = receipt.read_bytes()
    document = json.loads(raw_receipt)
    worker = document["worker"]
    if (
        document["request_sha256"] != canonical_digest(request_data)
        or worker["request_sha256"] != document["request_sha256"]
        or document["status"] != "complete"
    ):
        raise ValueError("original v5 execution certificate differs from the matched input")
    owners = worker["arms"][ARM]["owners"]
    result = {}
    for row in worker["prediction_rows"][ARM]:
        if owners[row["observation_id"]] != row["norad"]:
            raise ValueError("published prediction does not match its owner")
        k = key(row["receiver"], row["channel"], row["time_s"], row["measured_cfo_hz"])
        result.setdefault(k, set()).add(row["norad"])
    return result, sha256(raw_receipt).hexdigest()


def audit(case, cache, cpu):
    from tools.pipeline_eval.__main__ import encoded
    from tools.pipeline_eval.qualification.robust_em_trials import WORKER, load, sandbox

    packet, bindings = load(case, "matched-tile", cache)
    command = sandbox(cpu)
    command[command.index(str(WORKER))] = str(DIAGNOSTIC)
    raw = encoded(packet)
    result = json.loads(
        subprocess.run(command, input=raw, capture_output=True, check=True, timeout=30).stdout
    )
    # Scientific ownership and reference reading happens only after inference has completed.
    owners, receipt_hash = published(case)
    rows = result["rows"]
    for row in rows:
        k = key(row["receiver"], row["channel"], row["time_s"], row["measured_cfo_hz"])
        row["v5_norad"] = next(iter(owners[k])) if len(owners.get(k, ())) == 1 else None
        row["agrees"] = row["v5_norad"] == row["norad"] if row["v5_norad"] is not None else None
    groups = {
        "same": [r for r in rows if r["agrees"] is True],
        "different": [r for r in rows if r["agrees"] is False],
        "not_comparable": [r for r in rows if r["agrees"] is None],
    }

    def summary(values):
        def rms(field):
            return float(np.sqrt(np.mean([r[field] ** 2 for r in values]))) if values else None

        return dict(
            points=len(values),
            linear_residual_rms_hz=rms("residual_hz"),
            exact_residual_rms_hz=rms("exact_residual_hz"),
            geometry_rms_hz=rms("geometry_delta_hz"),
        )

    return dict(
        case=case,
        input_sha256=sha256(raw).hexdigest(),
        v5_receipt_sha256=receipt_hash,
        bindings=bindings,
        audit={k: summary(v) for k, v in groups.items()},
        rows=rows,
    )


def main():
    from tools.pipeline_eval.__main__ import encoded, local_output, save_json, write
    from tools.pipeline_eval.qualification.robust_em_trials import TIMING_IDS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out, cache = local_output(args.out), local_output(args.cache)

    def lane(i):
        return [audit(case, cache, 10 + i) for case in TIMING_IDS[i::2]]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [r for lane_result in pool.map(lane, (0, 1)) for r in lane_result]
    results.sort(key=lambda r: TIMING_IDS.index(r["case"]))
    write(
        out / "ownership-trace.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in results), mtime=0),
    )
    save_json(
        out / "ownership-audit.json", [{k: v for k, v in r.items() if k != "rows"} for r in results]
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Namespace imports only the data-path functions. Archive loading and matching
        # remain in the supervisor outside this worker.
        json.dump(inferred_trace(json.load(sys.stdin)), sys.stdout, allow_nan=False)
    else:
        main()
