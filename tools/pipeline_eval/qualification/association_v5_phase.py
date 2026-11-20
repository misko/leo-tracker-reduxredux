"""Audit one archived v5 owner using the original nominal selector and RF geometry.

Run with the authenticated frozen v5 source and runner first on PYTHONPATH.
The paired projection holds the published position, hardware and alias fixed.
It evaluates orbit phase only, without the full conditional orbital model.
"""

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from sgp4.api import Satrec
from sgp4.exporter import export_tle

from ..__main__ import save_json
from ..variants.v5_lean import SOURCE, bound_request
from . import association_evidence as audit
from .association_orbit_diagnostic import elements, rms
from .v5_postfit import _map
from .v5_prefix_audit import value

CASE = "DS26-0223"
NORAD = 67315
COMPONENT = "SCAN-RX2-CH7-T000-RF12440312500.000000"
PERIOD = 1 / 4.4e-6


def radio_residual(y, doppler, alias, hardware, train, held):
    residual = y + alias * PERIOD - hardware - doppler
    intercept = residual[train].mean()
    return dict(
        fixed_rms_hz=rms(residual),
        fixed_held_rms_hz=rms(residual[held]),
        train_intercept_hz=float(intercept),
        held_rms_after_train_intercept_hz=rms((residual - intercept)[held]),
        predicted_hz=doppler.tolist(),
        raw_residual_hz=residual.tolist(),
    )


def main(out):
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.analysis.localization_v3.orbits import ecef_states, regional_bank
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import ElementSetCatalogue

    if not Path(prepare_tracks.__code__.co_filename).is_relative_to(SOURCE):
        raise ValueError("Forensic replay requires the original v5 implementation")
    folder = audit.phase.ARCHIVE / (CASE + "-r0") / "baseline"
    _, request, job = bound_request(folder / "experimental-request.json")
    prepared = prepare_tracks(
        read_bound(job["native_input"]), TrackConfig(**read_bound(job["track_config"])["config"])
    )
    track = next(t for t in prepared["tracks"] if t["key"] == COMPONENT)
    t, y, rf = track["times"], track["values"], track["rf_hz"]
    support = json.loads((out.parent / f"{CASE}-candidate-fits.json").read_bytes())
    if not np.allclose(t, support["t"], rtol=0.0, atol=2e-6):
        raise ValueError("Historical component and Graph track use different time support")
    train, held = np.array(support["train"]), np.array(support["held"])
    meta = prepared["metadata"]
    origin, cutoff = meta["anchor_utc_ns"], meta["causal_cutoff_utc_ns"]
    reader = TleArchiveReader(Path(job["tle_root"]))
    parser = ElementParser()
    nominal = causal_catalogue(reader, cutoff, element_parser=parser)
    recovery72 = causal_catalogue(reader, cutoff, maximum_age_s=72 * 3600, element_parser=parser)
    regional = regional_bank(
        nominal.catalogue,
        origin,
        max(float(t["times"][-1]) for t in prepared["tracks"]),
        screen_latitude_deg=job["screen_center"][0],
        screen_longitude_deg=job["screen_center"][1],
    )
    index = regional["catalogue"].satellite_numbers.index(NORAD)
    prepared_count = len(regional["catalogue"])
    orbit_bank = regional["bank"]
    best = nominal.catalogue.satellite_numbers.index(NORAD)
    selected_lines = export_tle(nominal.catalogue.satellites[best])
    chosen72 = recovery72.catalogue.satellite_numbers.index(NORAD)
    lines72 = export_tle(recovery72.catalogue.satellites[chosen72])

    def pair(regime):
        return next(
            row["element"]
            for row in support["fits"]
            if row["regime"] == regime and row["norad"] == NORAD
        )

    current, later = pair("causal"), pair("later")
    previous = []
    for snapshot in reader.list_snapshots("space-track"):
        if not cutoff - 72 * 3600 * 10**9 <= snapshot.collected_utc_ns <= cutoff:
            continue
        text = reader.read(snapshot)
        for number, row in elements(text.encode(), snapshot.collected_utc_ns, snapshot.sha256):
            if number == NORAD and row["epoch_ns"] <= cutoff:
                previous.append(row)
    recent = {}
    for row in reversed(previous):
        recent[row["sha256"]] = row
    best_previous = max(
        (row for row in previous if current["epoch_ns"] - row["epoch_ns"] >= 10**9),
        key=lambda row: (row["epoch_ns"], row["collected_ns"]),
        default=None,
    )
    ph = {"current": current, "later": later}
    if best_previous:
        ph["previous"] = best_previous
    banks = {}
    for key, record in ph.items():
        if key == "current" and list(selected_lines) == record["lines"]:
            banks[key] = dict(
                time_s=orbit_bank["time_s"],
                position_km=orbit_bank["position_km"][index : index + 1],
                velocity_km_s=orbit_bank["velocity_km_s"][index : index + 1],
            )
            continue
        catalogue = ElementSetCatalogue(
            (str(NORAD),), (NORAD,), (Satrec.twoline2rv(*record["lines"]),)
        )
        knots = orbit_bank["time_s"]
        p, v, valid = ecef_states(catalogue, origin, knots)
        if not valid.all():
            raise ValueError("Invalid audit orbit state")
        banks[key] = dict(time_s=knots, position_km=p, velocity_km_s=v)

    package = folder / "experimental-evidence.zip"
    publication = audit.original(CASE, audit.phase.frozen_inputs()[CASE])
    if not set(track["observation_ids"]) <= {
        o for o, n in publication["owners"]["c0"].items() if n == NORAD
    }:
        raise ValueError("Historical component is not the published owner support")
    arms = {}
    with ZipFile(package) as z:
        tree = _map(json.loads(z.read("values.json"))["tree"])
        evidence = _map(tree["audit"])
        cavity = _map(evidence["cavity_policy"])
        node = _map(cavity["baseline_node"])
        seed = _map(node["seed"])
        component = [_map(row) for row in seed["rows"][1]]
        (alias,) = [
            a
            for r, a in zip(component, node["aliases"][1], strict=True)
            if r["component"] == COMPONENT and r["candidate_index"] == index
        ]
        reassociation = _map(_map(evidence["reassociation_complete"])["recovery"])
        addition = _map(_map(evidence["additional_position"])["recovery"])
        decision72 = _map(_map(addition["decisions"])["72h_30s"])
        if (
            cavity["accepted"]
            or reassociation["selected"]
            or decision72["eligible_proposals"]
            or decision72["status"] != "no_qualified_new_family"
            or list(selected_lines) != current["lines"]
        ):
            raise ValueError("The owner does not have the audited nominal provenance")
        for arm, row in _map(_map(tree["selected"])["arms"]).items():
            selected = _map(row)
            state = _map(selected["state"])
            phases = value(state["phases"], z)
            if len(phases) != prepared_count:
                raise ValueError("Frozen bank did not reconstruct the archived candidate indexing")
            (gate,) = [
                g
                for row in _map(selected["gates"])["tracks"][1]
                if (g := _map(row))["component"] == COMPONENT
            ]
            if (
                gate["candidate_index"] != index
                or gate["aliases_changed"]
                or gate["points"] != len(t)
            ):
                raise ValueError("Published geometry differs from reconstructed component or alias")
            beta, smooth = (value(state[k], z) for k in ("beta", "smooth"))
            lane = 2 * (track["receiver"] - 1) + int(track["channel"] > 4)
            hardware = beta[lane] + beta[lane + 4] * (t - 150) / 150
            if len(beta) == 9:
                hardware += beta[8] * (rf / 1e9 - 11.5)
            hardware += rf / 11.5e9 * projected_receiver_basis(t) @ smooth[track["receiver"] - 1]
            site = value(selected["endpoint_latlon"], z)
            rows = {}
            for regime, bank in banks.items():
                for phase_label, phase in (("zero", 0.0), ("saved", phases[index])):
                    f, el = phase_frequency_grid(bank, t, *site, phase_seconds=phase, rf_hz=rf)
                    rows[regime + "_" + phase_label] = dict(
                        phase_s=phase,
                        min_elevation_deg=float(el.min()),
                        **radio_residual(y, f[0], alias, hardware, train, held),
                    )
            arms[arm] = dict(
                site=site,
                alias=alias,
                saved_phase_s=phases[index],
                saved_gate=dict(
                    conditional_rms_hz=value(_map(gate["conditional_residual_gate"])["rms_hz"], z),
                    **{
                        key: value(gate[key], z)
                        for key in ("profile_rms_hz", "profile_bias_hz", "aliases_changed")
                    },
                ),
                hardware_hz=hardware.tolist(),
                projections=rows,
            )
    save_json(
        out,
        dict(
            case=CASE,
            norad=NORAD,
            component=COMPONENT,
            archive=publication["artifact_sha256"],
            request_sha256=publication["request_sha256"],
            cutoff_utc_ns=cutoff,
            source_sha256=request["source"]["sha256"],
            candidate_index=index,
            candidate_count=prepared_count,
            nominal_provenance=nominal.provenance[best],
            recovery72_provenance=recovery72.provenance[chosen72],
            recovery72_exported_lines=list(lines72),
            new_family_status=decision72["status"],
            new_family_eligible_proposals=decision72["eligible_proposals"],
            reassociation_selected=reassociation["selected"],
            versions=ph,
            distinct_causal_versions=list(recent.values()),
            times_s=t.tolist(),
            recorded_unwrapped_hz=y.tolist(),
            train=train.tolist(),
            held=held.tolist(),
            arms=arms,
            boundary=__doc__.split("\n\n")[1].replace("\n", " "),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
