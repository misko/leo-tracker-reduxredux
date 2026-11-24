"""Apply the released carrier history to genuine complete saved 8 ms observations."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_route_screen import archived
from preloaded_saved_worker import read, write


MEASUREMENTS = HERE / "measurements"
RECEIPT = "publication.json"
PROTOCOL = HERE / "eight-ms-held-fit-protocol.md"
RECEIVER_RECIPE_PINS = {
    "weak": "d15bc26414cefa92961932e4106d662676b013df52b146cd53d917ee45ee81dd",
    "north": "f2506d84408fbc3191a864baa7a5d7f44cc1a599ac2906c2a1cea973f1a73dec",
}
OMITTED = {
    "north": (Path("/dev/shm/leo-v3-north-cfo-final-03/mirror-offer.json"),
              "eacc9fd6b5da3e9e38a7b13edee43aad63e229622c9973aa401a2dbb8c7f20d7"),
    "weak": (Path("/dev/shm/leo-v3-portable-repaired-0016-translated-01/offer.json"),
             "063764d149b15b5a61c86a7f02b2a639a564327afdb3dbb32f1ff236e4f5ca6c"),
}
ORDER = {"weak": ("continued12", "history8"), "north": ("history8", "continued12")}


def select(original, recipe):
    """Rebind a measured 8 ms packet with chronological and held EOF claims."""
    from anchor_cycle_route import select_route
    from anchor_exposure import bind, enroll
    from anchor_holds import history_rows
    from continued_cfo import ContinuedChanges
    from continued_cfo_trial import rebinding
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES, bind_native, checked, clock, now
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS
    from leo.contracts.digests import canonical_digest

    start = now()
    for name, pin in SELECTOR_SOURCES.items():
        checked(HERE/name, pin)
    if recipe["aperture_samples"] != [200_000, 80_000] or "fixed_epoch_cfo_refinement" in recipe:
        raise ValueError("Expected the original unrefined measured 20/8 ms aperture")
    probes = original["source"]["probes"]
    session, inventory = (original["source"][k] for k in ("session_id", "input_manifest_sha256"))
    pin = canonical_digest(recipe)
    bind_native(original, session, inventory, pin[7:])
    live = ContinuedChanges()
    paid = Counter()
    for row, event in zip(probes, enroll(original), strict=True):
        radio, aperture = event[2], event[4]
        paid[radio] += live.consider(row, aperture == "short")
    history = live.projected_history(probes)
    if history != history_rows(probes):
        raise ValueError("Online original probe history differs from independent replay")
    choice = select_route(original)
    chosen = history if choice["route"] == "history" else probes
    policy = dict(wrapper_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), held_selector=SETTINGS,
                  selector_sources=SELECTOR_SOURCES, continuation=EXTRA_SOURCES[CONTINUATION],
                  measurement="original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement")
    detector_recipe = dict(recipe, held_native_8ms=policy)
    packet = rebinding(original, chosen, detector_recipe)
    bind(original, packet)
    detector, native = canonical_digest(detector_recipe), canonical_digest(packet)
    bind_native(packet, session, inventory, detector[7:], expected=native)
    evidence = dict(native_sha256=native, detector_recipe_sha256=detector, receiver_recipe=detector_recipe,
                    parent_native_sha256=canonical_digest(original), parent_detector_sha256=pin,
                    choice=choice, observed=sum(len(row["candidates"]) for row in probes),
                    selected=sum(len(row["candidates"]) for row in chosen),
                    would_refine_by_radio=paid, would_refine=len(live.paid), refinement_calls=0,
                    would_refine_stereo_visits=len({visit for visit, _ in live.paid}),
                    selector=clock(start))
    return packet, evidence


def source8(case):
    from aperture_route_screen import native_from_saved
    from empty_bootstrap import checked

    run = archived(f"eight-ms-{'physical' if case == 'weak' else 'north'}.json")["runs"]["8ms"]
    receipt_file = Path(run["output_root"])/"full-short-recipe.json"
    receipt = json.loads(checked(receipt_file, RECEIVER_RECIPE_PINS[case]))
    if receipt["saved_digest"] is not None:
        raise ValueError("8 ms input must be a complete genuine acquisition")
    return native_from_saved(run), receipt["recipe"]


def worker(case, mode, offer_kind, root):
    from empty_bootstrap import checked, load_runtime, now

    started = now()
    runtime = load_runtime()
    from anchor_exposure import bind
    from leo.storage.fast_scan import immutable_json
    from preloaded_saved_worker import enrolled
    from raw_cfo_north_trial import ORDER as RAW_ORDER, PUBLICATION_FLAGS, publish_saved

    root.mkdir()
    witness = None
    if mode == "history8":
        original, original_recipe = source8(case)
        packet8, witness = select(original, original_recipe)
    request, archive, offer, libraries, source_packet, selected, identity = enrolled(case)
    if witness is not None:
        bind(original, selected)
        selected = packet8
        identity = identity | dict(native_sha256=witness["native_sha256"], detector=witness["detector_recipe_sha256"],
                                   route=witness["choice"]["route"], selected=witness["selected"])
        source_packet = root/"derived-detections.json"
        immutable_json(source_packet, packet8)
        checked(source_packet, witness["native_sha256"][7:])
        write(root/"selector.json", witness)
    if offer_kind == "omitted":
        offer, offer_sha = OMITTED[case]
        identity = identity | dict(original_offer=json.loads(checked(offer, offer_sha)), offer_sha256=offer_sha)
    request = dict(request, archive={"root": str(archive)}, libraries=libraries,
                   offer_sha256={RAW_ORDER[1]: identity["offer_sha256"]})
    raw = dict(detector_recipe_sha256=identity["detector"], native_sha256=identity["native_sha256"])
    write(root/"request.json", dict(identity, recording=request["recording"],
          flags=[*PUBLICATION_FLAGS, "--withhold-empty-family-calibration"]))
    publish_saved(request, root/"published", offer, source_packet, selected, raw, started=started, runtime=runtime,
                  receipt_name=RECEIPT, flags=(*PUBLICATION_FLAGS, "--withhold-empty-family-calibration"))


def admit_omitted(root):
    sealed = read(root/"containing-seal.json")
    scored = read(root/"containing-score.json")
    if scored["sealed_sha256"] != sha256((root/"containing-seal.json").read_bytes()).hexdigest():
        raise ValueError("Original containing outcomes must seal before omitted admission")
    if sealed["binding_sha256"] != sha256((root/"binding.json").read_bytes()).hexdigest():
        raise ValueError("The original protocol changed before omitted admission")
    return next((case for case in ("north", "weak") if scored["cases"][case]["eligible_omitted"]), None)


def run(root, offer_kind):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    machine = host()
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the candidate before a timed launch")
    if offer_kind == "containing":
        tmpfs(root.parent)
        root.mkdir()
        cases = tuple(ORDER)
        paths = [Path(__file__), PROTOCOL, HERE/"eight_ms_held_score.py", HERE/"raw_cfo_north_trial.py",
                 HERE/"unified_short_bootstrap.py", HERE/"preloaded_saved_worker.py"]
        write(root/"binding.json", dict(machine=machine, order=ORDER, recipe_pins=RECEIVER_RECIPE_PINS,
              sources={p.name: sha256(p.read_bytes()).hexdigest() for p in paths},
              commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()))
    else:
        case = admit_omitted(root)
        if case is None:
            raise ValueError("No containing pair qualifies the single omitted replay")
        cases = (case,)
        write(root/"omitted-admission.json", dict(case=case, score_sha256=sha256((root/"containing-score.json").read_bytes()).hexdigest()))
    batch = root/offer_kind
    batch.mkdir()
    for d in ("fonts", "tmp"):
        (batch/d).mkdir()
    env = environment(batch)
    env.update(TMPDIR=str(batch/"tmp"), XDG_CACHE_HOME=str(batch/"tmp"))
    python = RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    for case in cases:
        for mode in ORDER[case]:
            output = batch/f"{case}-{mode}"
            command = ["/usr/bin/timeout", "--kill-after=2s", "45s", python, "-IB", Path(__file__),
                       "worker", output, offer_kind, case, mode]
            clock = measure(command, env, output)
            write(batch/(output.name+"-clock.json"), dict(clock=clock, command=list(map(str, command))))
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("offer", choices=("containing", "omitted"))
    parser.add_argument("case", nargs="?", choices=tuple(ORDER))
    parser.add_argument("mode", nargs="?", choices=("history8", "continued12"))
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.case, args.mode, args.offer, args.root)
    else:
        run(args.root, args.offer)
