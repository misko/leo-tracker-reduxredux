"""Cross original simulated receiver packets with a fixed visibility-erasure proxy."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from anchor_cycle_route import BLOCKS, block_calibration, route, select_route, summarize
from anchor_exposure import enroll, positive


SITES = ("north", "south")
VISITS_PER_BLOCK = 16
BLACKOUT_THRESHOLD = 64
NAMESPACE = "anchor-cycle-occupancy-v1:"


def blackout(visit):
    return sha256(f"{NAMESPACE}{visit // VISITS_PER_BLOCK}".encode()).digest()[0] < BLACKOUT_THRESHOLD


def erased(document):
    rows, totals = [], Counter()
    for row, entry in zip(document["source"]["probes"], enroll(document), strict=True):
        visit, _, radio, _, kind, events = entry
        dropped = blackout(visit)
        rows.append(dict(row, candidates=[]) if dropped else row)
        for label, increment in (("opportunities", 1), ("native_positives", events[1]),
                                 ("blackout_opportunities", int(dropped)), ("lost_positives", int(dropped) * events[1])):
            totals[radio, kind, label] += increment
    census = {radio: {kind: {label: value for (r, k, label), value in totals.items() if r == radio and k == kind}
                      for kind in ("anchor", "short")} for radio in (0, 1)}
    # This object exists for the occupancy assay only and cannot pass the native handoff.
    proxy = dict(document, source=dict(document["source"], probes=rows, qualified=False, analysis_manifest_sha256=None),
                 provenance=dict(document["provenance"], detector_sha256=None, scope="diagnostic occupancy erasure"))
    return proxy, census


def reviewed(rows, site):
    values = summarize(rows)
    return dict(route=route(values), radio=values,
                block_calibration={width: block_calibration(rows, site, width) for width in BLOCKS})


def audit(document, site):
    from leo.contracts.digests import canonical_digest

    start = process_time(), perf_counter()
    altered, census = erased(document)
    before, after = [select_route(packet, audit=True) for packet in (document, altered)]
    kept_before, kept_after, differences = [], [], []
    controls = document["source"]["probes"]
    for original, treated in zip(before["cycles"], after["cycles"], strict=True):
        if any(original[key] != treated[key] for key in ("index", "visit", "radio", "stream", "n")):
            raise ValueError("Erasure changed the held denominator or donor schedule")
        if bool(original["outcome"]) != positive(controls[original["index"]]):
            raise ValueError("Original held label is not a native positive decision")
        if blackout(original["visit"]):
            if treated["outcome"]:
                raise ValueError("Synthetic blackout has a retained anchor factor")
            continue
        if original["outcome"] != treated["outcome"]:
            raise ValueError("An untouched native held label changed")
        kept_before.append(original)
        kept_after.append(treated)
        differences.append(dict(visit=original["visit"], radio=original["radio"],
                                delta_log_score=treated["delta_log_score"] - original["delta_log_score"]))
    clocks = dict(selector_pair_cpu_s=process_time()-start[0], selector_pair_elapsed_s=perf_counter()-start[1])
    return dict(native=canonical_digest(document), diagnostic_erasure=canonical_digest(altered),
                erased_stereo_visits=sorted({row["visit_index"] for row in controls if blackout(row["visit_index"])}),
                opportunities=census, control=before, treatment=after,
                all_control_blocks=reviewed(before["cycles"], site)["block_calibration"],
                all_treatment_blocks=reviewed(after["cycles"], site)["block_calibration"],
                independent_native_anchors=dict(control=reviewed(kept_before, site), treatment=reviewed(kept_after, site),
                    treatment_minus_control_blocks={width: block_calibration(differences, site, width) for width in BLOCKS}),
                clocks=clocks)


def main(output):
    from anchor_cycle_route import original
    from aperture_trial import write
    from dense_geographic_trial import host

    machine = host()
    results = {site: audit(original(site), site) for site in SITES}
    if results["north"]["erased_stereo_visits"] != results["south"]["erased_stereo_visits"]:
        raise ValueError("The public simulation crossing requires identical applied blackout schedules")
    write(output, dict(machine=machine, mask=dict(namespace=NAMESPACE, issued_visits_per_block=VISITS_PER_BLOCK,
                                                  sha_first_byte_threshold=BLACKOUT_THRESHOLD), cases=results))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    main(cli.parse_args().output)
