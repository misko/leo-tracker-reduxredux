"""Time the guarded Cairo option on the authenticated physical DS30-0016 handoff."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PRIOR = Path("/dev/shm/leo-v3-history-risk-weak-physical02")
PINS = {"binding.json": "c7cd208136e0186fb8511b139ad81b83fd6a9ec89711feaa98c550a5b1bd4f32",
        "selected-detections.json": "aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac",
        "held.json": "d508015dac355c923ceb6685ee27d990fb62fbe31ecc93071a699478a5576552",
        "graph-proof.json": "d73459d91ad38fccfa33f0ecf6312647bd7d029524352cd6fc936a45781c4498",
        "verified-result.json": "27a6c002b1a91d55acd0d877d0a850f731a7246c0adaec01eeebcc2e647ec190"}
MODES = ("standard", "cairo")


def read(file):
    return json.loads(file.read_bytes())


def write(file, data):
    with file.open("x") as stream:
        json.dump(data, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


def source_pins():
    from history_cairo_render import SOURCES

    names = (*SOURCES, "history_cairo_artists.py", "exact_named_raw.py", "history_risk_route.py",
             "history_risk_weak_physical.py", "history_risk_cairo_physical.py", "history-risk-cairo-physical-protocol.md")
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in names}


def worker(root):
    import exact_named_raw as raw
    import history_risk_weak_physical as old
    from history_cairo_artists import capture

    spec = read(root/"binding.json")
    if spec["mode"] not in MODES or spec["sources"] != source_pins():
        raise ValueError("The paired physical publication differs from its signed launch")
    is_cairo = spec["mode"] == "cairo"
    artists = {}
    publish, observe = raw.publish_active, raw.observe

    def configured(args, *pos, **options):
        args.cairo_six_sheets = is_cairo
        return publish(args, *pos, **options)

    def audited(scan, position, stack, timings, owners, *, active, timed_acquire):
        @contextmanager
        def scope():
            with active():
                render = scan.render

                def measure(packet, **options):
                    with capture(artists, is_cairo):
                        return render(packet, **options)

                with patch.object(scan, "render", measure):
                    yield

        return observe(scan, position, stack, timings, owners, active=scope, timed_acquire=timed_acquire)

    with (patch.object(raw, "publish_active", configured), patch.object(raw, "observe", audited),
          patch.object(old, "source_pins", source_pins)):
        old.worker(root)
    if is_cairo:
        from exact_named_cairo_media import act

        witness = read(root/"candidate/exact-named-raw-witness.json")
        audit = witness["ports"]["cairo_layout"]
        act(audit)
        if (audit.get("position_figures"), audit.get("track_figures")) != (1, 1):
            raise ValueError("The actual publication did not take the explicit layout for both standard figures")
    write(root/"artist-evidence.json", artists)


def launch(root):
    from empty_bootstrap import RELEASE, checked
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from history_risk_weak_physical import controls, deny_original
    from portable_orbit_index_trial import local_launcher_tools

    sys.addaudithook(deny_original)
    local_launcher_tools()
    from dense_geographic_trial import host
    from exact_named_route import checked_catalogue
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    if staged_path(root.parent) != Path("/dev/shm"):
        raise ValueError("The physical saved pair must publish under a fresh tmpfs path")
    pinned = {name: checked(staged_path(PRIOR/name), digest) for name, digest in PINS.items()}
    prior = json.loads(pinned["binding.json"])
    request = prior["request"]
    study, _, _ = controls()
    expected = json.loads(pinned["verified-result.json"])
    if (request != study["request"] or not expected["parity"]["all_ordered_grid_values"]
            or len(expected["parity"]["figures"]) != 8 or expected["route"]["route"] != "lean"
            or json.loads(pinned["graph-proof.json"])["proven"]):
        raise ValueError("Expected the authentic complete frozen physical 20/8 handoff")
    for key, pin in (("region", request["offer_sha256"]), ("saved_inventory", request["inventory"][7:])):
        checked(staged_path(Path(request[key])), pin)
    archive = staged_path(Path(request["archive"]["root"]))
    _, refs = checked_catalogue(dict(archive=str(archive)), study["catalogue"], TleArchiveReader, canonical_digest)
    resident = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE",
                                                  *(r.path for r in refs)]))["fincore"]
    if len(resident) != len(refs) or any(r["res"] < r["size"] for r in resident):
        raise ValueError("The original causal snapshots must remain fully resident")
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"fonts", root/"fonts")
    env = environment_for(root)
    write(root/"pair.json", dict(machine=machine, enrollment=PINS, order=MODES, resident_snapshots=len(resident),
                                  resident_bytes=sum(r["size"] for r in resident), sources=source_pins()))
    for mode in MODES:
        arm = root/mode
        arm.mkdir()
        for file in ("held.json", "selected-detections.json", "graph-proof.json"):
            (arm/file).write_bytes(pinned[file])
        command = ["/usr/bin/timeout", "--kill-after=2s", "35s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", str(arm)]
        write(arm/"binding.json", prior | {"sources": source_pins(), "mode": mode, "command": list(map(str, command))})
        result = measure(command, env, arm/"candidate")
        write(arm/"clock.json", result)
        if result["exit_code"]:
            raise RuntimeError(result["stderr_tail"])


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not k.startswith(("cpu_", "elapsed_", "wall_"))}
    if isinstance(value, list):
        return [clean(x) for x in value]
    return value


def compare_artists(left, right):
    from leo.contracts.digests import canonical_digest

    def fixed(sheet):
        return {k: v for k, v in sheet.items() if k != "ticks"}

    shape = {"orbit": 2, "residual": 2, "standard": 2}
    if any({k: len(data[k]) for k in shape} != shape for data in (left, right)):
        raise ValueError("The rendered worker did not expose all six actual sheet witnesses")
    sheets = (("ch1-4-orbit", "ch5-8-orbit", "ch1-4-residuals", "ch5-8-residuals", "track-rms", "position"),
              [*left["orbit"], *left["residual"], *(left["standard"][n] for n in ("track-rms", "position"))],
              [*right["orbit"], *right["residual"], *(right["standard"][n] for n in ("track-rms", "position"))])
    evidence = {}
    for name, a, b in zip(*sheets, strict=True):
        if fixed(a) != fixed(b):
            for label, u, v in zip(range(len(a["axes"])), a["axes"], b["axes"], strict=True):
                if u != v:
                    raise ValueError(f"{name}: axis {label} changed {sorted(k for k in u if u[k] != v[k])}")
            raise ValueError(f"The title, footer or legend differs on {name}")
        differences = sum(x != y for axy, bxy in zip(a["ticks"], b["ticks"], strict=True) for x, y in zip(axy, bxy, strict=True))
        if name.endswith("-orbit") and differences:
            raise ValueError(f"The original visible orbit tick labels changed on {name}")
        evidence[name] = dict(axes=len(a["axes"]), sha256=canonical_digest(fixed(a)), changed_tick_sets=differences,
                              marks=sum(l[1]["shape"][0] for ax in a["axes"] for l in ax["offsets"]),
                              line_points=sum(l[1]["shape"][0] for ax in a["axes"] for l in ax.get("lines", [])))
    return evidence


def score(root):
    from empty_bootstrap import checked
    from direct_residual_figures_trial import pixels
    from history_risk_weak_physical import deny_original
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from publication_media_checks import verify_position_sidecars

    sys.addaudithook(deny_original)
    known = json.loads(checked(PRIOR/"verified-result.json", PINS["verified-result.json"]))
    runs = {}
    for mode in MODES:
        arm = root/mode
        previous = arm/"verified-result.json"
        if not previous.is_file():
            subprocess.run([sys.executable, "-IB", HERE/"history_risk_weak_physical.py", "score", arm],
                           check=True, timeout=30)
        result = read(previous)
        scientific = result["scientific"]
        evidence, ports = scientific["evidence"], scientific["ports"]
        if (result["terminal"] != known["terminal"] or result["arms"] != known["arms"]
                or any(evidence[key] != known["scientific"]["evidence"][key] for key in ("owner_rows", "owner_observations", "owner_maps"))
                or any(clean(ports[k]) != clean(known["scientific"]["ports"][k]) for k in
                       ("graph", "gates", "grid", "history_risk"))
                or ports["png"]["verified"] != 8 or ports["png"]["reused"] != 8 or ports["png"]["fallbacks"]
                or scientific["solver_recipe"]["orbit_index"] != "cold" or not result["parity"]["all_ordered_grid_values"]):
            raise ValueError("The original numerical route, masks, late check, ordered output or image verification changed")
        runs[mode] = result
    a, b = (runs[mode]["scientific"]["evidence"]["images"] for mode in MODES)
    if a != known["scientific"]["evidence"]["images"] or set(a) != set(PLOTS) or set(b) != set(PLOTS):
        raise ValueError("The two workers must write all standard figures and the standard control must replay exactly")
    folders = [root/mode/"candidate" for mode in MODES]
    receipt = read(root/"standard/publication.json")["receipt"]
    run = receipt["run_id"]
    sidecars = verify_position_sidecars(*folders, run, a, b)
    stores = [FastStandardAnalysisStore(path) for path in folders]
    media = {}
    for name in PLOTS:
        data = [store.artifact(run, name, info[name]["sha256"]) for store, info in zip(stores, (a, b), strict=True)]
        media[name] = pixels(*data) | {"stock_file_sha256": a[name]["sha256"], "cairo_file_sha256": b[name]["sha256"]}
    artist_inputs = [read(root/mode/"artist-evidence.json") for mode in MODES]
    artists = compare_artists(*artist_inputs)
    write(root/"result.json", dict(runs=runs, timing={mode: result["clock"] for mode, result in runs.items()},
        media=media, sidecars=sidecars, artists=artists, audit_cpu_ns={mode: value["cpu_ns"] for mode, value in
                                                                 zip(MODES, artist_inputs, strict=True)}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.root)
