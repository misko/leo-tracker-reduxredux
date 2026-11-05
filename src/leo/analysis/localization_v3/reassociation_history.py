"""Complete final-stage causal priors through an explicit read-only value port.

The caller invokes this only after predictive admission. Existing valid prior
epochs are retained; a failed proposal never mutates the incumbent likelihood.
"""

from copy import copy, deepcopy
from hashlib import sha256

import numpy as np
from sgp4.api import Satrec

from leo.analysis.localization_v3.history_position import forecast_phase_mean
from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.reassociation_context import build
from leo.analysis.localization_v3.residual_position import prediction_scan
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.sky.propagation import parse_element_set_records


def eligible_previous(number, current, sources, text_ids, cutoff):
    old = sources.get(str(number))
    return bool(
        old
        and number in text_ids
        and old["collected_utc_ns"] <= cutoff
        and current - old["epoch_utc_ns"] >= 1_000_000_000
    )


def select_history(bank, request):
    """Original newest genuinely earlier epoch, preserving archive tie order."""
    if request["cutoff"] != bank["cutoff_utc_ns"]:
        raise ValueError("Causal history cutoff mismatch")
    chosen = {}
    for number, latest in request["latest"].items():
        rows = bank["versions"].get(str(number), [])
        valid = [row for row in rows if latest - row["epoch_utc_ns"] >= 1_000_000_000]
        if valid:
            row = max(valid, key=lambda r: r["epoch_utc_ns"])
            if (
                not request["cutoff"] - int(72 * 3.6e12)
                <= row["collected_utc_ns"]
                <= request["cutoff"]
            ):
                raise ValueError("Noncausal private history member")
            chosen[str(number)] = deepcopy(row)
    return dict(chosen=chosen, snapshot_count=bank["snapshot_count"])


def complete_history(context, identities, ledger, scan_receipt, collect_history):
    """Refresh owned uncertainty caches without paths, earlier workers or GPS."""
    scan = context["scan"]
    text = scan.previous_tle
    if text is None or sha256(text.encode()).hexdigest() != scan.previous_tle_sha256:
        raise ValueError("Previous history bytes differ from prior receipt")
    if scan.previous_sources is None:
        raise ValueError("Explicit previous-epoch provenance required")
    sources = deepcopy(scan.previous_sources)
    old_records = {int(r.satellite_number): r for r in parse_element_set_records(text)}
    cutoff = scan_receipt["cutoff_utc_ns"]
    latest = {}
    for number in sorted(set(map(int, identities))):
        element = scan.elements.get(str(number), ledger.get(str(number)))
        if element is None:
            raise ValueError(f"Missing nominal element {number}")
        satellite = Satrec.twoline2rv(*element["lines"])
        epoch = int(round((satellite.jdsatepoch - 2440587.5 + satellite.jdsatepochF) * 86400e9))
        provenance = element.get("provenance", element)
        if epoch > cutoff or provenance.get("collected_utc_ns", cutoff + 1) > cutoff:
            raise ValueError(f"Unverified causal nominal {number}")
        if not eligible_previous(number, epoch, sources, old_records, cutoff):
            latest[str(number)] = epoch
    if not latest:
        return context, dict(requested=[], available=[], missing=[], changed=False)
    exported = collect_history(dict(cutoff=cutoff, latest=deepcopy(latest)))
    chosen = {int(n): r for n, r in exported["chosen"].items()}
    for number, row in chosen.items():
        if str(number) not in latest or not (
            cutoff - int(72 * 3.6e12) <= row["collected_utc_ns"] <= cutoff
            and latest[str(number)] - row["epoch_utc_ns"] >= 1e9
        ):
            raise ValueError("Invalid causal history export")
    info = dict(
        requested=list(latest),
        available=sorted(chosen),
        missing=sorted(set(map(int, latest)) - set(chosen)),
        changed=bool(chosen),
        old_sha256=scan.previous_tle_sha256,
    )
    if not chosen:
        return context, info
    lines = [r.text.strip() for n, r in old_records.items() if n not in chosen]
    for number, row in chosen.items():
        lines.append("\n".join(row["lines"]))
        sources[str(number)] = {k: deepcopy(v) for k, v in row.items() if k != "lines"}
    updated = copy(scan)
    updated.previous_tle = "\n".join(lines) + "\n"
    updated.previous_tle_sha256 = sha256(updated.previous_tle.encode()).hexdigest()
    updated.previous_sources = sources
    for attr in (
        "previous_shape_cache",
        "diagnostic_phase_width_cache",
        "causal_uncertainty_modes",
        "reference_motion_derivatives",
        "mean_motion_derivatives",
    ):
        if hasattr(updated, attr):
            delattr(updated, attr)
    result = dict(context, scan=updated, problems=dict(context["problems"]))
    result["families"] = [
        NewFamily(
            prediction_scan(updated, f.phase_limit_s),
            f.entries,
            context["model"],
            phase_step=f.receipt["phase_step_s"],
            phase_limit_s=f.phase_limit_s,
            allow_uncalibrated_label=True,
        )
        for f in context["families"]
    ]
    labels = context["problems"]["fitted_c"][0].labels
    _, receipts = phase_widths(updated, labels)
    forecast = forecast_phase_mean(receipts, context["model"]["shrinkage"])
    result["means"] = np.array(
        [
            forecast[k] if int(updated.norads[j]) in chosen else context["means"][k]
            for k, j in enumerate(labels)
        ]
    )
    for arm, (problem, x) in context["problems"].items():
        result["problems"][arm] = build(result, arm, problem.reference)[0], x
    info["new_sha256"] = updated.previous_tle_sha256
    return result, info
