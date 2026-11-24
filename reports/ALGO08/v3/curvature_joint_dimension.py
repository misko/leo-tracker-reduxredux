"""Price the shared smooth nullspace using already sealed signed curve rows."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curvature_filter import independent_bound
from curvature_filter_trial import CONTROLS, DENSE, DENSE_COLD, HERE, SOUTH_RAW, write_seal


SEALS = (
    "b67bdeb8fa5c2bf9cbfba26fc4722b4bee7716c927204da5194212ffc343c967",
    "390d01b2dc8130814a002c2b2e647583369fb0cb304fd584fa12a923935a4145",
)


def nullspace_size(matrix):
    """The column count gives an exact floor, SVD gives numerical rank."""
    singular = np.linalg.svd(matrix, compute_uv=False)
    tolerance = singular[0] * max(matrix.shape) * np.finfo(matrix.dtype).eps
    rank = int(np.count_nonzero(singular > tolerance))
    return dict(smooth_columns=matrix.shape[1], numerical_rank=rank,
                exact_nullity_floor=max(0, matrix.shape[0]-matrix.shape[1]),
                numerical_nullity=matrix.shape[0]-rank,
                smallest_over_largest=float(singular[-1]/singular[0]) if singular[0] else 0.)


def receiver_tracks(tracks, by_id, projected_receiver_basis):
    matrix, extents, samples, smallest = [], [], 0, []
    for track in tracks:
        times = np.asarray([by_id[oid]["time_s"] for oid in track["observation_ids"]])
        basis = projected_receiver_basis(times)
        contrast = independent_bound(times, basis)
        projection = (track["rf_hz"]/11.5e9)*(contrast["weights"] @ basis[list(contrast["indices"])])
        matrix.append(projection)
        extents.extend(((times[0], -1), (times[-1], 1)))
        samples += len(times)
        smallest.append(contrast["strongest_normalized_projection"])
    events = np.array(sorted(extents))[:, 1]
    return dict(triples=len(matrix), native_rows=samples, max_overlapping_spans=int(np.max(np.cumsum(-events))),
                same_basis_min_witness=min(smallest), **nullspace_size(np.array(matrix)))


def account(rx, phase_counts):
    rows = sum(r["native_rows"] for r in rx.values())
    curves = sum(r["triples"] for r in rx.values())
    smooth = sum(r["smooth_columns"] for r in rx.values())
    paired_phase = sum(phase_counts)
    return dict(paired_distinct_phase_counts=phase_counts,
                triple_floor_if_both_phase_tangents_eliminated=max(0, sum(r["exact_nullity_floor"] for r in rx.values())-paired_phase),
                full_row_floor_with_two_local_affine_pieces_and_both_phase_tangents=max(0, rows-4*curves-smooth-paired_phase))


def run(root):
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from held_spatial_start_trial import PINS, json_pin
    from leo.analysis.localization_v3.tracks import winning_observations

    start = process_time()
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    import_cpu_s = process_time()-start
    receipts = {}
    for case, pin in zip(("dense", "south"), SEALS, strict=True):
        seal = json.loads(gzip.decompress(checked(root/f"{case}.json.gz", pin)))
        if case == "dense":
            job = json_pin(DENSE/"binding.json", PINS["dense_binding"])
            native = json_pin(job["packet"], seal["input"]["detector"])
            work = json.loads(checked_gzip(HERE/"measurements/cold-exact-budget-dense-control.json.gz", DENSE_COLD))["stages"]["work"]
            phase_counts = [len({norad for _, _, norad, _ in p}) for p in work["ordered"][:2]]
        else:
            path, = SOUTH_RAW.glob("fast-scan-automatic-work/*/detections.json")
            native = json_pin(path, seal["input"]["detector"])
            stock = json_pin(*CONTROLS[case])
            phase_counts = [len(c["labels"]) for c in stock["route_details"]["cold"]["completed"][:2]]
        start = process_time()
        observed, _ = winning_observations(native)
        by_id = {row["observation_id"]: row for row in observed}
        join_time = process_time()-start
        start = process_time()
        rx = {str(r): receiver_tracks([t for t in seal["sampled"]["tracks"] if t["receiver"] == r],
                                      by_id, projected_receiver_basis)
              for r in (1, 2)}
        assert min(r["same_basis_min_witness"] for r in rx.values()) == seal["filter"]["min_strongest_smooth_projection"]
        receipts[case] = dict(signed_row_join_cpu_s=join_time, build_and_rank_cpu_s=process_time()-start, per_radio=rx,
                              candidate_seal_sha256=pin, **account(rx, phase_counts))
    write_seal(root/"joint-dimension.json.gz", dict(cases=receipts, machine=host(), geometry_evaluations=0,
               first_research_import_cpu_s=import_cpu_s,
               complete_solves=0), {Path(__file__).name: Path(__file__).read_bytes()})


def checked_gzip(path, expected):
    result = gzip.decompress(path.read_bytes())
    if sha256(result).hexdigest() != expected:
        raise ValueError("The paired dense cold ledger changed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
