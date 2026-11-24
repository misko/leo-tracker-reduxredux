"""Change complete measurements only on already matching nonanchor lanes."""

from collections import Counter, defaultdict
from math import remainder, sqrt
from statistics import fmean

import signed_cfo_time_readout as signed
from signed_cfo_time import epoch


FAC_PERIOD = 40_000 / 3
MAX_CFO_HZ = 250
MAX_EPOCH_SAMPLES = 2


def same_carrier(stock, sparse):
    delta = sparse["fractional_tracking_cfo_hz"] - stock["fractional_tracking_cfo_hz"]
    offset = remainder(epoch(sparse)-epoch(stock), FAC_PERIOD)
    return abs(delta) <= MAX_CFO_HZ and abs(offset) <= MAX_EPOCH_SAMPLES


def bind_derived(sparse, probes, recipe):
    detector = signed.canonical(recipe)
    source = sparse["source"]
    analysis = signed.canonical(["cancellation", source["raw_recording_authority_digest"], detector[7:], probes])
    packet = dict(sparse, source=dict(source, probes=probes, analysis_manifest_sha256=analysis),
                 provenance=dict(sparse["provenance"], detector_sha256=detector, run_id="blind-compact-"+analysis[7:39]))
    return packet, dict(recipe=recipe, recipe_sha256=detector, derived_native_sha256=signed.canonical(packet),
                        raw_authority=source["raw_recording_authority_digest"], same_signed_clocks=True)


def derive(stock, sparse):
    left, right = (signed.opportunities(n) for n in (stock, sparse))
    signed.bind_pair(stock, sparse, left, right)
    counts = defaultdict(Counter)
    probes, donations = [], []
    for oid, row in right.items():
        current, donor = row["factor"], left[oid]["factor"]
        aperture = "short" if row["short"] else "anchor"
        count = counts[f"rx{row['radio']}/{aperture}"]
        count["opportunities"] += 1
        original = row["row"]
        if len(original["candidates"]) != int(current is not None):
            raise ValueError("A sparse lane must hold exactly one selected native factor or be empty")
        if current is None or donor is None:
            bucket = "sparse_only" if current else "installed_only" if donor else "both_empty"
            count[bucket] += 1
        elif same_carrier(donor, current):
            count["matches"] += 1
            if row["short"] and current != donor:
                count["substitutions"] += 1
                donations.append(dict(observation_id=oid, visit=original["visit_index"],
                    receiver=row["radio"], channel=original["channel"], rf_hz=original["actual_rf_hz"],
                    counter=row["counter"], original=current, donor=donor))
                original = dict(original, candidates=[donor])
        else:
            count["carrier_disagreement"] += 1
        if bool(original["candidates"]) != (current is not None):
            raise ValueError("Donation changed sparse packet membership")
        probes.append(original)
    if not donations:
        raise ValueError("The planned mechanism has no changed matched short tuples")

    recipe = dict(schema="private-0049-matched-native-donor-v1",
        installed_native_sha256=signed.canonical(stock), sparse_native_sha256=signed.canonical(sparse),
        signed_cfo_hz=MAX_CFO_HZ, no_cfo_alias_rolling=True, wrapped_epoch_samples=MAX_EPOCH_SAMPLES,
        period_samples=[40_000,3], nonanchor_only=True, row_schedule="original stereo stream every eighth admitted visit",
        unchanged_opportunities=True, donation_sha256=signed.canonical(donations))
    packet, custody = bind_derived(sparse, probes, recipe)
    residual = [row["original"]["fractional_tracking_cfo_hz"]-row["donor"]["fractional_tracking_cfo_hz"] for row in donations]
    changes = dict(Counter(field for row in donations for field in row["original"]
                          if row["original"][field] != row["donor"][field]))
    return packet, dict(custody, coverage=counts, donations=donations, feature_changes=changes,
        same_membership=True, substituted=len(donations),
        input_matched_rms_from_installed_hz=sqrt(fmean(x*x for x in residual)))


def owner_counts(ordered, changes, *, label="donated"):
    by_id = {entry["observation_id"] for entry in changes}
    return {arm: {"total": len(values), label: sum(row[0] in by_id for row in values)}
            for arm, values in ordered.items()}
