"""Seal training-only center nominations before opening the enrolment decision."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path

from dense_family_refit import checked, clock, spent


HERE = Path(__file__).resolve().parent
JOB = Path("/dev/shm/leo-dense-8ms-prefix-fit01/binding.json")
TRANSFER = Path("/dev/shm/leo-exact-solver-0057-result01")
PLAN = Path("/dev/shm/leo-dense-8ms-prefix-plan01")
EARLIER = Path("/dev/shm/leo-held-anchor-selected-dense-01/original-detections.json")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PACKET = "candidate/fast-scan-automatic-work/algo08-v2-0d2bfca844b3cb7a93b66d42591991d5/detections.json"
PROTOCOL_SHA = "a62591b466b9ba8115ccd65ff37ed5875cf14857d2fc6d5a89de05fa3f5b3e3e"
GRAPH_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
BUDGET_CPU_S = 8.
FOLDS = {"DS30-0008": 11459687500.0, "DS30-0057": 11690312500.0}
NOMINAL = ("visit_index", "receiver_id", "channel", "actual_rf_hz", "valid_start_counter")


def read(path, pin):
    return json.loads(checked(path, pin.removeprefix("sha256:")))


def prehistory(native, ledger):
    """Build the dense preselector evidence from recorded callbacks and 8 ms measurements."""
    start = native["source"]["probes"]
    if len(ledger) != 384:
        raise ValueError("Expected the original 192 stereo intervention visits")
    combined = []
    for row, entry in zip(start[:len(ledger)], ledger, strict=True):
        other = entry["after"]
        if (row != entry["before"] or any(other[key] != row[key] for key in NOMINAL)
                or entry["aperture"] not in ("anchor", "short")
                or (entry["aperture"] == "anchor" and row != other)):
            raise ValueError("Signed prehistory does not retain the original opportunity")
        combined.append(other)
    return dict(native, source=dict(native["source"], probes=combined + start[len(ledger):]))


def input_case(case):
    if case == "DS30-0008":
        req = read(JOB, "4c74d02b61a428ef87ffbaba45b950188b7fd2e33f0dae9e5eda64d5b3e8a30f")
        original = read(EARLIER, "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85")
        ledger = read(PLAN / "prefix-ledger.json",
                      "bdb455b908819dfc2266486499bd5cb757fe4561d6fb78908bebc8ef7af4164d")
        native = prehistory(original, ledger)
        sealed = read(PLAN / "detections.json", req["native"])
        if native["source"]["probes"] != sealed["source"]["probes"]:
            raise ValueError("Unfiltered prehistory must reproduce the archived selected rows")
        return native, req, req["native"], 47, "regenerated unfiltered signed prefix"
    req = read(TRANSFER / "binding.json",
               "761d1b75c58d5949d3da8a880b925f1968ef3ba10ef4f7a8fc611c4699f4d072")
    pin = req["native"]["candidate"]
    native = read(TRANSFER / PACKET, pin)
    if native["provenance"]["detector_sha256"] != (
            "sha256:13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"):
        raise ValueError("Transfer packet must have the unfiltered full-short receiver recipe")
    return native, dict(req, cutoff_utc_ns=req["clock_cutoff_utc_ns"],
                        offer_sha256=req["region_sha256"], authority=req["raw_authority"]), pin, 49, "unfiltered full-short"


def fold(native, rf):
    train, held = [], []
    rows = native["source"]["probes"]
    for first, second in zip(rows[::2], rows[1::2], strict=True):
        key = (first["visit_index"], first["channel"], first["actual_rf_hz"])
        if (key != (second["visit_index"], second["channel"], second["actual_rf_hz"])
                or first["receiver_id"] == second["receiver_id"]):
            raise ValueError("Expected unique signed stereo observations on one RF")
        use = first["actual_rf_hz"] == rf
        if use != (first["channel"] == 4):
            raise ValueError("The predeclared held channel must have one exact actual RF")
        (held if use else train).extend((first, second))
    if not held or not train:
        raise ValueError("The RF fold requires training and held opportunities")
    return dict(native, source=dict(native["source"], probes=train)), held


def rivals(ratios, labels, catalogue_size):
    """Take the two individually credible orbits after charging their catalogue prior."""
    import numpy as np

    score = np.asarray(ratios) - np.log(catalogue_size)
    return [dict(norad=int(labels[j]), log_odds=float(score[j]))
            for j in np.lexsort((labels, -score))[:2] if score[j] > 0]


def nominate(tracks, sky, center):
    import numpy as np

    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from tools.pipeline_eval.variants.experimental.regional_reassignment import contrast_log_ratio

    bank = sky["bank"]
    labels = bank["norad"]
    curved = [tracks["tracks"][i] for i in tracks["curved_indices"]]
    if not curved:
        return []
    times = np.unique(np.concatenate([track["times"] for track in curved]))
    f, e, d = phase_linear_frequency(prepare_phase_geometry(bank, times), *center)
    result = []
    for track in curved:
        indices = np.searchsorted(times, track["times"])
        visible = np.all(e[:, indices] >= 0, axis=1)
        q = track["rf_hz"] / 11.5e9
        contrasts = contrast_log_ratio(track["values"], q * f[visible][:, indices], q * d[visible][:, indices])
        result.append(dict(track=track["key"], rf=track["rf_hz"], visible=int(visible.sum()),
                           points=len(indices), shortlist=rivals(contrasts, labels[visible], len(labels))))
    return result


def gate(case, config):
    from aperture_trial import archive_identity

    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.operations.localization_v3_inputs import prepare_initial_sky
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser

    when = clock()
    native, req, pin, count, receiver = input_case(case)
    rf = FOLDS[case]
    train, held = fold(native, rf)
    archive = Path(req["archive"]["root"])
    if not archive.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("The full orbit archive must already be staged")
    reader = TleArchiveReader(archive)
    refs = reader.list_snapshots("space-track")
    identity = archive_identity(archive)
    if (len(refs) != count or any(req["archive"].get(key) != value for key, value in identity.items())
            or not all(ref.collected_utc_ns < req["cutoff_utc_ns"] for ref in refs)
            or train["source"]["raw_recording_authority_digest"] != req["authority"]
            or train["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]):
        raise ValueError("The assigned causal archive or packet scope changed")
    center = read(Path(req["region"]), req["offer_sha256"])["center"]
    clocks = dict(binding=spent(when))
    start = clock()
    tracks = prepare_tracks(train, config)
    clocks["graph"] = spent(start)
    population = dict(held=len(held), training=len(train["source"]["probes"]),
                      training_winners=len(tracks["observations"]), graph_points=tracks["graph_points"],
                      graph_tracks=len(tracks["tracks"]), curved=len(tracks["curved_indices"]))
    start = clock()
    parser = CausalPreparationParser()
    sky = prepare_initial_sky(reader, tracks["tracks"], tracks["metadata"], screen_latitude_deg=center[0],
                              screen_longitude_deg=center[1], element_parser=parser)
    clocks["orbit"] = spent(start)
    start = clock()
    nominated = nominate(tracks, sky, center)
    clocks["nomination"] = spent(start)
    return dict(case=case, packet=pin, archive=req["archive"], receiver=receiver, rf=rf,
                center=center, population=population, catalogue=sky["metadata"], parser=parser.stats,
                nominations=nominated, clocks=clocks, total=spent(when))


def enroll(records, total_cpu_s, dense_pair):
    if total_cpu_s > BUDGET_CPU_S or set(records) != set(FOLDS):
        return dict(status="budget_exhausted", dense={}, transfer=None)
    dense = records["DS30-0008"]["nominations"]
    candidates = Counter(item["norad"] for row in dense for item in row["shortlist"])
    support = {str(label): candidates[label] for label in dense_pair}
    qualifying = [row for row in records["DS30-0057"]["nominations"] if len(row["shortlist"]) == 2]
    transfer = min(qualifying, key=lambda row: (-row["shortlist"][1]["log_odds"], row["track"]), default=None)
    return dict(status="qualified" if all(support.values()) and transfer else "inconclusive",
                dense=support, transfer=transfer)


def worker(output):
    import sys

    from aperture_trial import THREADS, write
    from dense_geographic_trial import host

    from leo.analysis.polynomial_tracklets import TrackConfig

    start = clock()
    machine = host()
    if any(os.environ.get(key) != "1" for key in (*THREADS, "OMP_THREAD_LIMIT")):
        raise ValueError("Expected the six single-thread numerical settings")
    checked(HERE / "dense-family-holdout-protocol.md", PROTOCOL_SHA)
    config = TrackConfig(**read(RELEASE / "assets/tracks.json", GRAPH_SHA)["config"])

    def no_raw(event, info):
        if event == "open" and isinstance(info[0], (str, bytes)) and (
                "fast-scan-recordings" in Path(os.fsdecode(info[0])).parts):
            raise RuntimeError("The worker accepts saved native packets only")

    sys.addaudithook(no_raw)
    records = {}
    for case in FOLDS:
        if spent(start)["cpu_s"] > BUDGET_CPU_S:
            break
        records[case] = gate(case, config)
        write(output / f"{case}-training.json", records[case])
    write(output / "sealed.json", dict(protocol=PROTOCOL_SHA, records=records, machine=machine,
                                      elapsed=spent(start), position_fits=0, raw_reads=0))


def decision(output):
    from hashlib import sha256

    from aperture_trial import write

    source = output / "sealed.json"
    loaded = source.read_bytes()
    trial = json.loads(loaded)
    if (trial["protocol"], trial["position_fits"], trial["raw_reads"]) != (PROTOCOL_SHA, 0, 0):
        raise ValueError("Unexpected first-stage status before revealing the dense rival names")
    result = enroll(trial["records"], trial["elapsed"]["cpu_s"], (63478, 67511))
    write(output / "gate.json", dict(result, seal_sha256=sha256(loaded).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("worker", "decision"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"worker": worker, "decision": decision}[args.stage](args.output)
