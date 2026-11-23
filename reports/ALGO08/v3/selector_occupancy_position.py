"""Compare two routes on one private derived North occupancy roster."""

import argparse
from collections import Counter
from contextlib import contextmanager
from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from anchor_holds import history_rows
from aperture_trial import RELEASE, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from discovery_margin_trial import verified_input
from full_short_physical import environment
from full_short_run import GEOGRAPHIC_SHA, RECIPE_SHA, TRACK_SCORES_SHA, geographic_projection
from selector_occupancy import blackout, erased
from weak_combined_raw import measure


HERE = Path(__file__).resolve().parent
ORDER = ("unfiltered", "history")
ARMS = ("c0", "fitted_c")
OCCUPANCY_SHA = "591f7357cb0903b47850f5f4c4b5e51da7fc20edf2ff890f79128ed6ece96151"
HISTORY_SHA = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"
REFERENCE_SHA = {"north-combined.json": "871105154ab79679308cf7455ee10c236094d8735a02c17ed11bb2412283172e",
                 "north-causal-transfer.json": "049c47ff95d0a6d306ce4e5d2f0d10c0b8faf49a66a2b3022c8828113e32853c"}
REFERENCE_ROOTS = {"unfiltered": Path("/var/tmp/leo-north-short-regional-nov23/containing"),
                   "history": Path("/var/tmp/leo-north-short-causal-raw-nov23/containing")}


def projection(native, mode):
    from tools.pipeline_eval.variants import carrier_continuation

    if mode not in ORDER or sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != HISTORY_SHA:
        raise ValueError("Expected the frozen unfiltered or released carrier-history route")
    mask, _ = erased(native)
    training = mask["source"]["probes"]
    used = training if mode == "unfiltered" else history_rows(training)
    projected = dict(mask, source=dict(mask["source"], probes=used),
                     provenance=dict(mask["provenance"], scope=f"diagnostic occupancy erasure {mode}"))
    ledger = {}
    for original, available, final in zip(native["source"]["probes"], training, used, strict=True):
        if (dict(original, candidates=[]) != dict(final, candidates=[])
                or final["candidates"] not in ([], available["candidates"])):
            raise ValueError("Diagnostic projection changed an opportunity or a measured candidate")
        visit, radio = original["visit_index"], original["receiver_id"]
        oid = "sha256:" + sha256(f"{native['source']['session_id']}:{radio}:{original['valid_start_counter']}".encode()).hexdigest()
        if blackout(visit):
            if final["candidates"]:
                raise ValueError("Measured factor survives the frozen blackout")
            state = "erased_positive" if original["candidates"] else "erased_empty"
        elif not original["candidates"]:
            state = "native_empty"
        else:
            state = "observed" if final["candidates"] else "history_rejected"
            if state == "history_rejected" and mode != "history":
                raise ValueError("Unfiltered solve dropped a surviving native factor")
        if oid in ledger:
            raise ValueError("Duplicate observation identity")
        ledger[oid] = dict(visit=visit, radio=radio, state=state)
    return mask, projected, ledger


def input_receipt(native):
    from leo.contracts.digests import canonical_digest

    path = checked(HERE / "measurements/selector-occupancy.json.gz", OCCUPANCY_SHA)
    previous = json.loads(decompress(path.read_bytes()))["cases"]["north"]
    arms = {}
    for mode in ORDER:
        masked, projected, ledger = projection(native, mode)
        if (canonical_digest(masked) != previous["diagnostic_erasure"] or canonical_digest(native) != previous["native"]
                or previous["treatment"]["route"] != ORDER[0] or len(previous["erased_stereo_visits"]) != 224):
            raise ValueError("Different occupancy intervention or source")
        arms[mode] = dict(projection=canonical_digest(projected), states=dict(Counter(row["state"] for row in ledger.values())),
                          ledger=ledger)
    return dict(native=previous["native"], mask=previous["diagnostic_erasure"], chosen=previous["treatment"]["route"],
                erased_stereo_visits=previous["erased_stereo_visits"], arms=arms)


def worker(binding_path, mode, output, geo, regional):
    from joint_publication import run

    binding = read(binding_path)
    path = Path(binding["packet"])
    original = read(path)
    _, projected, ledger = projection(original, mode)
    roster = binding["study"]["arms"][mode]
    identity = binding["study"]["native"]
    calls, observed = [], []
    if ledger != roster["ledger"] or not original["source"]["qualified"]:
        raise ValueError("Worker cannot bind its original source and distinct research view")

    @contextmanager
    def scope():
        from leo.contracts.digests import canonical_digest
        from tools import algo08_position

        if canonical_digest(projected) != roster["projection"] or canonical_digest(original) != identity:
            raise ValueError("Research view or original source differs from the frozen digests")
        prepare = algo08_position.prepare_native_scan

        def projected_prepare(native, *args, **kwargs):
            if canonical_digest(native) != identity or not native["source"]["qualified"]:
                raise ValueError("Projected preparation requires the exact original verified handoff")
            calls.append(roster["projection"])
            return prepare(projected, *args, **kwargs)

        marker = dict(kind="private counterfactual inference on a simulated detector-output roster", production=False,
                      raw_reads=0, native_input=identity, analysis_projection=roster["projection"],
                      mask=binding["study"]["mask"], route_requested=mode, states=roster["states"])
        write(output / "RESEARCH-ONLY.json", marker)
        with geographic_projection(geo, regional) as counts, patch.object(algo08_position, "prepare_native_scan", projected_prepare):
            yield counts

    def observe(prepared):
        from leo.contracts.digests import canonical_digest

        tracks = prepared["tracks"]
        identities = {row["observation_id"] for row in tracks["observations"]}
        retained = {oid for oid, row in ledger.items() if row["state"] == "observed"}
        if identities != retained or len(identities) != len(tracks["observations"]):
            raise ValueError("Prepared graph does not contain the exact retained original detections")
        observed.append(canonical_digest(sorted(identities)))
        return dict(points=tracks["graph_points"], tracks=len(tracks["tracks"]), curved=len(tracks["curved_indices"]))

    request = binding["request"]
    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                           region=Path(request["region_file"]), saved=path, saved_digest=identity, output=output,
                           optimized_full_catalogue=True, verify_images=True, observe_prepared=observe)
    result = run(args, early_regional=True, keep_selected_rows=True, saved_receiver=RECIPE_SHA,
                 geographic_projector=scope, reuse_cold_rows=True, reuse_grid_phase_states=True)
    if calls != [roster["projection"]] or len(observed) != 1:
        raise ValueError("Expected one verified research projection and one observed graph")
    write(output / "occupancy-analysis.json", dict(projection=calls[0], observed_ids=observed[0],
        original_handoff=result["saved_digest"], terminal=result["receipt"]["terminal_sha256"], evidence=result["evidence"]))


def run(output, geo, regional):
    system = host()
    checked(geo, GEOGRAPHIC_SHA)
    checked(regional, TRACK_SCORES_SHA)
    binding, path, original = verified_input("north", "12ms")
    study = input_receipt(original)
    output.mkdir(mode=0o700, exist_ok=False)
    env = environment(output)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    bound = output / "binding.json"
    commands = {mode: [str(python), "-BPs", str(Path(__file__)), "worker", str(bound), mode,
                       str(output / mode), str(geo), str(regional)] for mode in ORDER}
    write(bound, dict(machine=system, packet=str(path), request=binding["request"], inventory=binding["inventory"],
                      study=study, order=ORDER, commands=commands, geographic_sha256=GEOGRAPHIC_SHA,
                      regional_sha256=TRACK_SCORES_SHA,
                      protocol_sha256=sha256((HERE / "selector-occupancy-position-protocol.md").read_bytes()).hexdigest()))
    for mode, command in commands.items():
        measure(command, env, output, mode)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="action", required=True)
    outer = subs.add_parser("run")
    inner = subs.add_parser("worker")
    inner.add_argument("binding_path", type=Path)
    inner.add_argument("mode", choices=ORDER)
    for command in (outer, inner):
        for key in ("output", "geo", "regional"):
            command.add_argument(key, type=Path)
    args = vars(cli.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)


if __name__ == "__main__":
    main()
