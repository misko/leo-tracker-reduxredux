"""Authenticate and sanitize the archived v5 factors used in an owner oracle."""

import json
import re
from hashlib import sha256
from zipfile import ZipFile

import numpy as np

from leo.contracts.digests import canonical_digest

from ..scoring import ARMS
from ..variants import robust_em as lean
from ..variants.v5_lean import SOURCE_SHA256
from .full_v5_check import BULK, _load_case, _sha
from .robust_orbit_fit_diagnostic import key, published
from .v5_postfit import _map
from .v5_prefix_audit import value

COMPONENT = re.compile(r"SCAN-RX([12])-CH([1-8])-T\d+-RF(\d+\.\d+)")


def _matched_arms(worker):
    arms = worker["arms"]
    for arm in ARMS:
        if canonical_digest(arms[arm]["owners"]) != arms[arm]["owner_sha256"]:
            raise ValueError("archived owner-map digest differs")
    a, b = tuple({r["observation_id"]: r for r in worker["prediction_rows"][arm]} for arm in ARMS)
    fields = ("receiver", "channel", "time_s", "measured_cfo_hz", "component", "norad", "role")
    if len(a) != len(worker["prediction_rows"]["c0"]) or a.keys() != b.keys():
        raise ValueError("archive contains an incomplete or duplicated v5 comparison arm")
    stable = {}
    for identifier, row in a.items():
        other = b[identifier]
        if any(other[field] != row[field] for field in fields):
            continue
        for arm, original in zip(ARMS, (row, other), strict=True):
            if arms[arm]["owners"][identifier] != original["norad"]:
                raise ValueError("publication row disagrees with the authenticated owner")
            if not np.isclose(
                original["measured_cfo_hz"] - original["prediction_hz"],
                original["residual_hz"],
                rtol=0,
                atol=1e-6,
            ):
                raise ValueError("published residual does not reconstruct")
        stable[identifier] = row | {
            "archived_residual_hz": {
                arm: original["residual_hz"]
                for arm, original in zip(ARMS, (row, other), strict=True)
            }
        }
    return stable, len(a) - len(stable)


def row_factors(row, original):
    """Check the independent RF-bearing observation and recover its published alias."""
    parsed = COMPONENT.fullmatch(row["component"])
    if not parsed:
        raise ValueError("unrecognized authenticated track/component")
    rx, channel, carrier = parsed.groups()
    if (
        int(rx) != row["receiver"]
        or int(channel) != row["channel"]
        or not np.isclose(float(carrier), original["actual_rf_hz"], rtol=0, atol=1e-5)
        or key(row["receiver"], row["channel"], row["time_s"], row["measured_cfo_hz"])
        != key(
            original["receiver"],
            original["channel"],
            original["time_s"],
            original["measured_cfo_hz"],
        )
    ):
        raise ValueError("publication component/point differs from native archived observation")
    folded = float(lean.fold(original["measured_cfo_hz"]))
    lift = round((row["measured_cfo_hz"] - folded) / lean.PERIOD)
    if abs(folded + lift * lean.PERIOD - row["measured_cfo_hz"]) > 1e-5:
        raise ValueError("archived CFO is not an integer lift of its folded observation")
    return dict(
        id=row["observation_id"],
        rx=int(rx),
        channel=int(channel),
        rf_hz=float(carrier),
        time_s=row["time_s"],
        folded_hz=folded,
        component=row["component"],
        v5_owner=row["norad"],
        v5_lift=lift,
        role=row["role"],
        archived_residual_hz=row["archived_residual_hz"],
    )


def published_lifts(presentation, factors, archive):
    """Recover the archived integer branch against its calibrated plot, once per component."""
    tracks = {}
    for encoded in presentation["tracks"][1]:
        track = _map(encoded)
        tracks[track["key"]] = dict(
            zip(
                value(track["observation_ids"], archive),
                value(track["values"], archive),
                strict=True,
            )
        )
    peaks, curves = {}, {}
    for encoded in presentation["orbit_lanes"][1]:
        lane = _map(encoded)
        rx, channel = int(lane["receiver"][2:]), int(lane["channel"][2:])
        for item in lane["peaks"][1]:
            row = _map(item)
            peaks[row["peak_id"]] = value(row["frequency_hz"], archive)
        for item in lane["curves"][1]:
            curve = _map(item)
            curves[rx, channel, int(curve["satellite_id"])] = (
                curve["time_s"],
                curve["frequency_hz"],
            )
    groups = {}
    for row in factors:
        if row["role"] == "conditional":
            groups.setdefault((row["component"], row["v5_owner"]), []).append(row)
    for (component, number), rows in groups.items():
        first = rows[0]
        t, f = [
            np.asarray(value(v, archive)) for v in curves[first["rx"], first["channel"], number]
        ]
        frequency = np.interp([r["time_s"] for r in rows], t, f)
        values = np.array([tracks[component][r["id"]] for r in rows])
        raw = np.array([r["folded_hz"] + r["v5_lift"] * lean.PERIOD for r in rows])
        corrected = np.array([peaks[r["id"]] for r in rows])
        residual = np.array([r["archived_residual_hz"]["fitted_c"] for r in rows])
        offset = (frequency + residual - corrected + raw - values) / lean.PERIOD
        finite = offset[np.isfinite(offset)]
        if not len(finite):
            raise ValueError("conditional group lacks an archived orbit curve")
        shift = round(float(np.median(finite)))
        if np.max(abs(finite - shift)) > 0.24:
            raise ValueError("the authenticated conditional curve disagrees with the shared lift")
        for row, observed in zip(rows, values, strict=True):
            intrinsic = (observed - row["folded_hz"]) / lean.PERIOD
            if abs(intrinsic - round(intrinsic)) > 1e-7:
                raise ValueError("archive track value differs from its native observation")
            row["v5_lift"] = round(intrinsic) + shift
            row["v5_whole_track_alias"] = shift


def _archive_fields(archive, expected_request, stable):
    root = _map(json.loads(archive.read("values.json"))["tree"])
    if root["request_sha256"] != expected_request:
        raise ValueError("signed v5 numerical archive holds a different request")
    signed = _map(_map(root["audit"])["signed_policy"])
    ledger = {
        row["observation_id"]: {
            k: value(v, archive)
            for k, v in row.items()
            if k in ("receiver", "channel", "time_s", "measured_cfo_hz", "actual_rf_hz")
        }
        for encoded in signed["observations"][1]
        if (row := _map(encoded))["observation_id"] in stable
    }
    factors = [
        row_factors(r, ledger[identifier])
        for identifier, r in stable.items()
        if identifier in ledger
    ]
    published_lifts(_map(root["presentation"]), factors, archive)
    node = _map(signed["node"])
    seeds = _map(node["seed"])
    labels = value(_map(signed["base"])["labels"], archive)
    means = dict(zip(labels, value(signed["means"], archive), strict=True))
    widths = value(signed["widths"], archive)
    model = {k: value(v, archive) for k, v in _map(signed["model"]).items()}
    priors = {}
    for encoded in (*seeds["rows"][1], *signed["entries"][1]):
        row = _map(encoded)
        candidate = row.get("candidate_index")
        norad = row.get("candidate_norad", row.get("norad"))
        if norad is None or candidate is None:
            continue
        item = [means.get(candidate, 0.0), widths[candidate]]
        if item[1] <= 0:
            continue
        if str(norad) in priors and priors[str(norad)] != item:
            raise ValueError("conflicting causal phase prior for same published NORAD")
        priors[str(norad)] = item
    return factors, priors, model


def load_archive(case):
    authority = _load_case(case)
    req = BULK / authority["request"]["path"]
    receipt = req.parent.parent / "baseline-execution.json"
    publication = json.loads(receipt.read_bytes())
    receipt_sha = _sha(receipt)
    # Existing authority checker revalidates the complete request and native binding.
    _, witness = published(case)
    if witness != receipt_sha:
        raise ValueError("publication changed during archive validation")
    worker = publication["worker"]
    request = json.loads(req.read_bytes())
    if publication["role"] != "baseline" or worker["source_sha256"] != SOURCE_SHA256:
        raise ValueError("the stored v5 worker is outside the original release")
    native = request["job"]["native_input"]["sha256"]
    native_path = BULK / authority["native"]["path"]
    if native != "sha256:" + _sha(native_path):
        raise ValueError("native detector input changed")
    path = req.parent / "experimental-evidence.zip"
    if worker["artifact"]["sha256"] != "sha256:" + _sha(path):
        raise ValueError("v5 numerical evidence archive changed")
    stable, mismatched = _matched_arms(worker)
    with ZipFile(path) as evidence:
        factors, priors, model = _archive_fields(evidence, publication["request_sha256"], stable)
    artefact = dict(
        receipt_sha256=receipt_sha,
        request_sha256=authority["request"]["sha256"],
        archive_sha256=worker["artifact"]["sha256"],
        native_sha256=authority["native"]["sha256"],
        owner_sha256={a: worker["arms"][a]["owner_sha256"] for a in ARMS},
        archive_rows=len(stable) + mismatched,
        unstable_rows=mismatched,
        missing_native_observation=len(stable) - len(factors),
        history_snapshot_count=len(request["causal_snapshots"]),
        catalog_in_v5_history=authority["catalog"]["sha256"]
        in request["causal_snapshots"].values(),
        archive_digest=sha256(receipt.read_bytes()).hexdigest(),
    )
    outputs = {
        arm: {k: worker["arms"][arm][k] for k in ("endpoint_latlon", "residual_rms_hz")}
        for arm in ARMS
    }
    return factors, priors, model, artefact, outputs
