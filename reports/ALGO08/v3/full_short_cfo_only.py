"""One synthetic CFO-only perturbation of the sealed mixed DS30-0016 input."""

import argparse
from hashlib import sha256
from math import isfinite
from pathlib import Path
import subprocess
from unittest.mock import patch

from aperture_trial import ARMS, RELEASE, archive_identity, read, write
from dense_geographic_trial import host
import full_short_factor_contrast as contrast


HERE = Path(__file__).resolve().parent
REFERENCES = Path("/dev/shm/leo-v3-0016-factor-contrast-result04")
NUMERICAL_SHA = "2e1017bc72b18843bec41e304134f5a53637d1a98e6420558e115d5617791f87"
SCORED_SHA = "ca032171a4994ceaca13639476db9f40f651d2c86839bc562ecabbf9ebf6b9b4"
OWNER_SHA = "5526927737375a150a8efd72df634c26ce08a111dc60add62d36983c596772d8"
INPUT_SHA = "1f3ba13ff9f701faf10a46e7706c9a875c057b31aff5eeec931cd9f5f7299038"
CFO = "fractional_tracking_cfo_hz"
CELL = "synthetic-cfo-only"
TRACKS_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"


def substitute_cfo(rows):
    changed, probes = [], []
    for lane, stock, mixed, kind, anchor in rows:
        factor = mixed
        if kind == "matched" and not anchor:
            original, short = stock[CFO], mixed[CFO]
            if not (isfinite(original) and isfinite(short)):
                raise ValueError("Matched signed CFO must be finite")
            factor = dict(mixed, **{CFO: original})
            if original != short:
                changed.append(dict(visit=lane["visit_index"], radio=lane["receiver_id"],
                                    channel=lane["channel"], original_hz=original, mixed_hz=short))
        probes.append(dict(lane, candidates=[] if factor is None else [factor]))
    return probes, changed


def worker(saved, digest, output, inventory_path):
    import joint_publication

    publication = joint_publication.run
    noise = []

    def observe_run(args, **options):
        graph = args.observe_prepared

        def observed(prepared):
            estimate = prepared["noise"]
            noise.append({k: v for k, v in estimate.items() if k != "per_observation_noise_sigma_hz"})
            return graph(prepared)

        args.observe_prepared = observed
        return publication(args, **options)

    with patch.object(joint_publication, "run", observe_run):
        contrast.worker(saved, digest, output, inventory_path)
    if len(noise) != 1:
        raise ValueError("Expected one original radio noise model")
    write(output / "noise-observed.json", noise[0])


def run(root):
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from north_factor_swap import rebound
    from weak_combined_raw import measure

    machine = host()
    if root.resolve() != root or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use fresh canonical tmpfs output")
    setup = contrast.enrolled()
    controls = setup["controls"]
    stock, mixed = (controls[label]["packet"] for label in contrast.CONTROLS)
    pairs = contrast.strata(stock, mixed)
    enrolled = contrast.verified(REFERENCES / "inputs.json", INPUT_SHA)
    if contrast.census(pairs) != enrolled["census"]:
        raise ValueError("The original frozen signed join changed")
    probes, changed = substitute_cfo(pairs)
    by_radio = {radio: sum(row["radio"] == radio for row in changed) for radio in (0, 1)}
    if by_radio != {0: 207, 1: 99} or sum(len(row["candidates"]) for row in probes) != 475:
        raise ValueError("Synthetic scope must preserve all original mixed membership")
    packet = rebound(mixed, probes, ["synthetic signed CFO sensitivity on mixed 0016 v1", contrast.CONTROLS, INPUT_SHA])
    digest = canonical_digest(packet)
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=20)
    saved = root / "synthetic-cfo-only-input.json"
    write(saved, packet)
    inputs = dict(synthetic_parameter_probe=True, source_packets=contrast.CONTROLS, original_join_sha256=INPUT_SHA,
                  saved=digest, changed=changed, by_radio=by_radio, kept=475, shared_frequency_field=CFO)
    write(root / "input-seal.json", inputs)
    output = root / CELL
    measure([python, "-BPs", str(Path(__file__).resolve()), "worker", str(saved), digest, str(output),
             controls["stock"]["inventory"]], env, root, CELL)
    science = contrast.bind_publication(output, packet, setup["offer"])
    if archive_identity(contrast.ARCHIVE) != setup["archive"]:
        raise ValueError("Staged causal archive changed during the saved solve")
    write(root / "numerical-seal.json", dict(machine=machine, science=science, input=inputs, archive=setup["archive"],
          process=read(root / f"{CELL}-clock.json"), noise=read(output / "noise-observed.json"),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "full-short-cfo-only-protocol.md").read_bytes()).hexdigest(), raw_waveform_reads=0))


def score(root):
    from mixture_score import section
    from tools.pipeline_eval.scoring import distance_km

    path = root / "numerical-seal.json"
    result = read(path)
    old = contrast.verified(REFERENCES / "numerical-seal.json", NUMERICAL_SHA)
    archived = contrast.verified(REFERENCES / "scored.json", SCORED_SHA)
    owner_reference = contrast.verified(REFERENCES / "ownership.json", OWNER_SHA)
    key = "mixed-stock-matches -> candidate"
    restored = old["trials"]["mixed-stock-matches"]
    previous_arms = {"original mixed": old["controls"]["candidate"]["terminal"]["arms"], "restored complete tuples": restored["arms"]}
    survey = contrast.verified(HERE / "measurements/eight-ms-physical.json", contrast.EIGHT_MS_REFERENCE)["survey"]
    for name, data in zip(("candidate", "mixed-stock-matches"), previous_arms.values(), strict=True):
        if any(section(data, survey, data)["arms"][arm]["error_km"] != archived["fits"][name]["arms"][arm]["error_km"] for arm in ARMS):
            raise ValueError("Archived score changed")
    final_arms = result["science"]["arms"]
    results = {name: dict(comparison=section(final_arms, survey, reference),
                         endpoint_shift_m={arm: 1000*distance_km(final_arms[arm]["latlon"], reference[arm]["latlon"]) for arm in ARMS})
               for name, reference in previous_arms.items()}
    if not all(owner_reference["changes"][key][arm]["exact_ordered_rows"] for arm in ARMS):
        raise ValueError("Prior mixed and restored owner lists did not agree exactly")
    owners = {arm: result["science"]["owners"][arm] == restored["owners"][arm] for arm in ARMS}
    write(root / "scored.json", dict(against=results, exact_ordered_owners_against_both=owners,
         restored_graph=restored["solve"]["preparation"], numerical_sha256=sha256(path.read_bytes()).hexdigest(),
         reference_numerical_sha256=NUMERICAL_SHA, reference_score_sha256=SCORED_SHA, reference_owner_sha256=OWNER_SHA))


def audit_noise(root):
    """Replay graph/noise inputs only, without orbit preparation or a position solve."""
    from leo.analysis.localization_v3.noise import estimate_noise
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    import json

    result = read(root / "numerical-seal.json")
    archival = contrast.verified(REFERENCES / "numerical-seal.json", NUMERICAL_SHA)
    restored = "mixed-stock-matches"
    paths = {CELL: (root / "synthetic-cfo-only-input.json", result["input"]["saved"]),
             restored: (REFERENCES / f"{restored}-detections.json", archival["trials"][restored]["native"])}
    config = contrast.verified(RELEASE / "assets/tracks.json", TRACKS_SHA)["config"]
    graphs, estimates = {}, {}
    for name, (path, expected) in paths.items():
        document = read(path)
        if canonical_digest(document) != expected:
            raise ValueError("Noise audit requires the same synthetic and tuple-restoration input bytes")
        prepared = prepare_tracks(document, TrackConfig(**config))
        tracks = prepared["tracks"]
        graphs[name] = canonical_digest(json.loads(json.dumps(tracks, default=_json_value, allow_nan=False)))
        estimates[name] = {k: v for k, v in estimate_noise(tracks, prepared["observations"]).items()
                           if k != "per_observation_noise_sigma_hz"}
    write(root / "noise-audit.json", dict(graph_sha256=graphs, estimate=estimates,
         synthetic_model_matches_solve=estimates[CELL] == result["noise"], scope="tracks and radio noise only"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for command in ("run", "score", "audit-noise"):
        sub.add_parser(command).add_argument("root", type=Path)
    replay = sub.add_parser("worker")
    replay.add_argument("saved", type=Path)
    replay.add_argument("digest")
    replay.add_argument("output", type=Path)
    replay.add_argument("inventory_path", type=Path)
    values = vars(parser.parse_args())
    {"run": run, "worker": worker, "score": score, "audit-noise": audit_noise}[values.pop("action")](**values)
