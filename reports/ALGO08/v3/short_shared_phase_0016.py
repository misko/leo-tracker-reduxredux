"""Qualify the guarded short callback in the exact charted original reader."""

import argparse
from collections import Counter
from copy import deepcopy
import fcntl
import json
from math import isfinite
import os
from pathlib import Path
import resource
import subprocess
import sys
import tarfile
from io import BytesIO
from time import monotonic
from unittest.mock import patch

from . import short_shared_integer_phase as callback


CASE = "DS30-0016"
OLD_READY = Path("/dev/shm/leo-v3-combined-small-panel-ready09")
CHARTED = OLD_READY / CASE / "charted"
PANEL = Path("/tmp/leo-v3-combined-small-panel/reports/ALGO08/v3")
OLD_NATIVE = "5eea8c0db979ec729e83f56f2cb806823d785fbc65455730ee321cfc9de9a245"
OLD_RECEIPT = "7c206951445522102a3440427cd209a47f94fe53989c4bf5a2eab328fd3a819f"
OLD_SELECTOR = "08b78805c81a8051d429910af1ca77e7c7b89fda66781beb431c8e67c379db97"
OLD_SEAL = "662326f266ccfeb5bbdb1a6096f8d48e33d953e45818aae9a4ff2e62f2685cdb"
OLD_BASE_RECIPE = "c5d73bad038bed7719cb989955e474bb54c802506aadfa4b6d7a006311d0e045"
OLD_HELD_RECIPE = "ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"
OLD_READY_PIN = "4f59e24fe2c8f550b9ee310126601c1a882c040df06c62317f2be1b8dd9ea0b9"
OLD_AUDIT = Path("/tmp/leo-v3-shared-integer-phase.b4hWrS/native")
OLD_AUDIT_PIN = "66864c1e316a4386968709601ede2c64d27eccdb7743207f54438aa13760aee1"
PROTOCOL = Path(__file__).with_name("short-shared-phase-0016-protocol.md")
SCORE_FIELDS = {"fractional_exact_score", "fractional_control_score", "fractional_margin"}
LIMIT = 1e-8


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def pins(short_pin, held):
    base = {key: value for key, value in held.items() if key != "held_native_8ms"}
    if (callback.digest(canonical(base)) != OLD_BASE_RECIPE or callback.digest(canonical(held)) != OLD_HELD_RECIPE
            or base["shortened_sha256"] != callback.ORIGINAL or short_pin == callback.ORIGINAL):
        raise ValueError("Charted 8 ms recipe or held policy differs")
    base = dict(base, shortened_sha256=short_pin)
    return (callback.digest(canonical(base)),
            callback.digest(canonical(dict(held, shortened_sha256=short_pin))))


def sources(panel, build, tree, short_binary, short_pin, held):
    candidate = deepcopy(build)
    basename, heldname = "full_short_run.py", "eight_ms_native_receiver.py"
    before, after = pins(short_pin, held)
    for name, replacements in (
        (basename, [(callback.ORIGINAL, short_pin), (OLD_BASE_RECIPE, before)]),
        (heldname, [(OLD_HELD_RECIPE, after)]),
    ):
        key = f"reports/ALGO08/v3/{name}"
        path = tree / key
        source = panel.check(path, build["sources"][key]).decode()
        for old, new in replacements:
            source = callback.one(source, old, new)
        path.write_text(source)
        candidate["sources"][key] = "sha256:" + callback.digest(path.read_bytes())
    if build["native"]["--short-binary"]["sha256"] != callback.ORIGINAL:
        raise ValueError("The charted worker did not use the measured sparse verifier")
    candidate["native"]["--short-binary"] = dict(path=str(short_binary), sha256=short_pin)
    return candidate, dict(base=before, held=after, short=short_pin)


def build_short(root):
    from . import sparse8_native_profile as native

    qualified = json.loads(native.checked(OLD_AUDIT/"build.json", OLD_AUDIT_PIN))
    if qualified["experimental_source_sha256"] != native.digest(Path(callback.__file__).read_bytes()):
        raise ValueError("The proven phase overlay changed")
    for arm, pin in qualified["binaries"].items():
        native.checked(OLD_AUDIT/(arm+".so"), pin)
    srcdir, closure = callback.SOURCE, callback.RECIPE_SOURCE/"tools/pipeline_eval/variants/experimental"
    outputs = {name: native.checked(directory/name, callback.SOURCE_PINS[name]) for name, directory in (
        ("portable_verifier.c", srcdir), ("receiver_stencil_verify.inc", srcdir),
        ("receiver_phase_free_verify.inc", closure), ("receiver_fractional_exact.inc", closure))}
    raw = outputs.pop("portable_verifier.c").decode()
    audited = native.one(raw, '#include "receiver_phase_free_verify.inc"', '#include "frozen_phase_free.inc"')
    if callback.instrument(raw, True).encode() != (OLD_AUDIT/"shared/portable_verifier.c").read_bytes():
        raise ValueError("As-run trial source differs")
    ordinary = """int portable_verifier_factor(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {
    return verify_glrt(w, epoch, out, 0, 0);
}"""
    source = "#include <fenv.h>\n" + native.one(audited, ordinary, ordinary.replace("out, 0, 0)", "out, 0, 1)"))
    phase = callback.share_table(outputs.pop("receiver_phase_free_verify.inc").decode())
    if phase.encode() != (OLD_AUDIT/"shared/frozen_phase_free.inc").read_bytes():
        raise ValueError("As-run guarded phase source differs")
    outputs.update({"portable_verifier.c": source.encode(), "frozen_phase_free.inc": phase.encode()})
    for name, value in outputs.items():
        (root/name).write_bytes(value)
    recipe = json.loads(native.checked(native.BASE/"build-receipt.json", native.STOCK["build-receipt.json"]))
    native.checked(native.SPARSE/"timing_first_receiver.o", native.STOCK["timing_first_receiver.o"])
    for arg in recipe["relink"]:
        if arg.endswith(".o"):
            name = Path(arg).name
            digest = native.STOCK[name] if name == "two_carrier_receiver.o" else recipe["short_object_sha256"][name]
            native.checked(Path(arg), digest)
    target, obj = root/"shared.so", root/"portable_verifier.o"
    args = recipe["relink"]
    objects = {"timing_first_receiver.o": native.SPARSE/"timing_first_receiver.o", "portable_verifier.o": obj}
    commands = [[*recipe["compile"][:-4], "-c", root/"portable_verifier.c", "-o", obj],
                [args[0], *[objects.get(Path(arg).name, arg) for arg in args[3:-1]], target]]
    commands = [list(map(str, command)) for command in commands]
    for command in commands:
        subprocess.run(command, cwd=callback.RECIPE_SOURCE/"native/algo08v2", check=True)
    from .short_shared_integer_phase_smoke import main as synthetic

    return target, dict(commands=commands, sources={name: native.digest(body) for name, body in outputs.items()},
                        sha256=native.digest(target.read_bytes()), audited_manifest_sha256=OLD_AUDIT_PIN,
                        synthetic=synthetic(OLD_AUDIT, unaudited=target))


def load_panel():
    old = json.loads(callback.checked(OLD_READY/"ready.json", OLD_READY_PIN))
    for key, pin in old["sources"].items():
        callback.checked(PANEL/key, pin)
    sys.path.insert(0, str(PANEL))
    import combined_small_panel as panel

    return panel, old


def worker_command(panel, root, work, inputs, pin, *, preflight=False):
    extra = ("--preflight",) if preflight else ()
    argv = panel.command(root, CASE, work, inputs, "charted", extra, meter=True)
    argv[argv.index("--build-sha256") + 1] = pin
    return argv


def prepare(root):
    panel, old = load_panel()
    inputs = old["cases"][CASE]
    assert_source(panel, inputs)
    root.mkdir(mode=0o700)
    target, binary = build_short(root)
    tree, manifest = panel.runtime_paths(root, "charted")
    tree.mkdir()
    archive = panel.check(panel.FROZEN/"source-archive.tar.gz", panel.ARCHIVE_PIN)
    with tarfile.open(fileobj=BytesIO(archive)) as body:
        body.extractall(tree, filter="data")
    build = json.loads(panel.check(OLD_READY/"charted-build.json", panel.CONTROL))
    held = json.loads(panel.check(CHARTED/"publication-held-anchor-route.json", OLD_SELECTOR))["receiver_recipe"]
    new, identities = sources(panel, build, tree, target, binary["sha256"], held)
    pin = panel.write(manifest, new)
    authority = panel.check(OLD_READY/(CASE+"-authority.json"), inputs["authority_sha256"])
    (root/(CASE+"-authority.json")).write_bytes(authority)
    work = panel.new_work(root/"preflight")
    dry = panel.check_command(worker_command(panel, root, work, inputs, pin, preflight=True))
    if dry != inputs["preflight"]["charted"] or dry["waveform_opens"] != 0:
        raise ValueError("Original inventory preflight differs")
    panel.controller_preflight()
    return panel.write(root/"ready.json", dict(input=inputs, charted_ready=OLD_READY_PIN, charted_build=panel.CONTROL,
                preflight=dry, preflight_meter=json.loads((work/"numeric-process.json").read_bytes()),
                before=panel.source_before(inputs, True), cap_s=panel.CAP_SECONDS[CASE], identities=identities,
                build=pin, binary=binary, protocol=callback.digest(PROTOCOL.read_bytes()),
                controller=callback.digest(Path(__file__).read_bytes())))


def assert_source(panel, inputs):
    if any(inputs[name] != value for name, value in panel.source_case(CASE).items()):
        raise ValueError("Original private sample custody changed")


def exact(a, b):
    return canonical(a) == canonical(b)


def compare_factors(a, b, anchor):
    if len(a) != len(b):
        raise ValueError("Ordered candidates changed count")
    scores = dict.fromkeys(sorted(SCORE_FIELDS), 0.)
    for left, right in zip(a, b, strict=True):
        keep = lambda row: row if anchor else {key: value for key, value in row.items() if key not in SCORE_FIELDS}
        if not exact(keep(left), keep(right)) or left.keys() != right.keys() or not SCORE_FIELDS <= left.keys():
            raise ValueError("Anchor values or signed short factor fields changed")
        for name in scores:
            delta = abs(left[name]-right[name])
            if not isfinite(delta) or delta > LIMIT:
                raise ValueError(f"The short score drift exceeded tolerance for {name}")
            scores[name] = max(delta, scores[name])
    return scores


def packet_delta(old, new, enroll):
    native_ids = {"analysis_manifest_sha256", "detector_sha256", "run_id", "probes"}

    def stable(doc):
        return {key: ({k:v for k,v in value.items() if k not in native_ids}
                      if key in ("source", "provenance") else value) for key, value in doc.items()}

    if not exact(stable(old), stable(new)):
        raise ValueError("Signed packet delivery, timing or source metadata changed")
    lanes, positives, changed, scores = (Counter() for _ in range(4))
    for left, right, mode in zip(old["source"]["probes"], new["source"]["probes"], enroll(new, old), strict=True):
        a, b = (row["candidates"] for row in (left, right))
        kind = mode[4]
        error = compare_factors(a, b, kind == "anchor")
        lanes[kind] += 1
        positives[kind] += bool(a)
        changed[kind] += not exact(a, b)
        for name, delta in error.items():
            scores[name] = max(scores[name], delta)
    return dict(lanes=dict(lanes), positives=dict(positives), changed_factor_rows=dict(changed), score_drift=dict(scores))


def numerical_delta(a, b):
    if type(a) is not type(b):
        raise ValueError("Scientific product numeric type changed")
    if isinstance(a, dict) and a.keys() == b.keys():
        return max((numerical_delta(a[key], b[key]) for key in a), default=0.)
    if isinstance(a, list) and len(a) == len(b):
        return max((numerical_delta(x, y) for x, y in zip(a, b, strict=True)), default=0.)
    if isinstance(a, float) and isfinite(a) and isfinite(b):
        return abs(a-b)
    if not exact(a, b):
        raise ValueError("Scientific product structure or discrete values changed")
    return 0.


def science(ctl, trial):
    info = ("chunk_index", "first_sequence", "encoded", "decoded", "windows", "member_sha256", "raw_sha256",
            "index_sha256", "manifest_sha256")
    stable = lambda row: [tuple(scope[key] for key in info) for scope in row["verified_member_scopes"]]
    if stable(ctl) != stable(trial) or len(stable(ctl)) != 13:
        raise ValueError("Ordered original member authenticity differs")
    for key in ("ordered_owners", "outcome", "raw_identity", "detector_route"):
        if not exact(ctl[key], trial[key]):
            raise ValueError(f"Standard publication changed {key}")
    identity = {"binding", "elapsed_seconds"}
    paired = lambda name, keys: numerical_delta(*({key:value for key,value in arm[name].items() if key not in keys}
                                                   for arm in (ctl, trial)))
    changes = dict(grid=paired("grid", identity), path=paired("path", identity),
                   detail=paired("publication_arms", {}), arms=numerical_delta(ctl["evidence"]["arms"], trial["evidence"]["arms"]))
    if max(changes.values()) > LIMIT:
        raise ValueError(f"The checked numerical products drifted: {changes}")
    figures = []
    for a, b in zip(ctl["figures"], trial["figures"], strict=True):
        if any(a[k] != b[k] for k in ("name", "size", "rgba_sha256")):
            raise ValueError(f"Expected identical decoded pixels for {a['name']}")
        figures.append(dict(name=a["name"], bytes_identical=a["sha256"] == b["sha256"], identical_pixels=True))
    return dict(numeric_max_abs_delta=changes, media=figures, owners={key:len(rows) for key, rows in trial["ordered_owners"].items()})


def score(panel, root, ready, process):
    import combined_small_panel_score as original
    from anchor_exposure import enroll

    t = monotonic()
    work = root/"run"
    with patch.object(original, "CONTROL", ready["build"]):
        candidate = original.checked_publication(work, "charted", CASE, ready["input"], process)
    panel.write(work/"verified.json", candidate)
    ctl = json.loads(panel.check(CHARTED/"verified.json", OLD_RECEIPT))
    if json.loads(panel.check(CHARTED/"cell-seal.json", OLD_SEAL))["result_sha256"] != OLD_RECEIPT:
        raise ValueError("The charted result is not the independently sealed control")
    output = work/"publication"
    a, b = (next((path/"fast-scan-automatic-work").glob("*/detections.json"))
            for path in (CHARTED/"publication", output))
    old = json.loads(panel.check(a, OLD_NATIVE))
    new = json.loads(panel.check(b, candidate["native_sha256"]))
    held_before = json.loads(panel.check(CHARTED/"publication-held-anchor-route.json", OLD_SELECTOR))
    held_after = json.loads((work/"publication-held-anchor-route.json").read_bytes())
    ids = ready["identities"]
    native_before, native_after = (item["receiver_audit"]["native"] for item in (ctl, candidate))
    unchanged = {"native_cpu_ns", "native_wall_ns", "short_primary_sha256"}
    if (held_after["choice"]["route"] != "unfiltered" or held_after["choice"]["route"] != held_before["choice"]["route"]
            or held_after["parent_detector_sha256"] != "sha256:"+ids["base"]
            or held_after["detector_recipe_sha256"] != "sha256:"+ids["held"]
            or ready["identities"]["short"] != candidate["receiver_audit"]["native"]["short_primary_sha256"]
            or dict(ctl["recipe"], shortened_sha256=ids["short"]) != candidate["recipe"]
            or any(native_before[key] != native_after[key] for key in native_before if key not in unchanged)
            or any(candidate["prefetch"][key] != ctl["prefetch"][key] for key in ("submitted", "submitted_bytes"))):
        raise ValueError("The normal chronology, held recipe or scheduled transport changed")
    for key in ("observed", "selected", "refinement_calls", "would_refine", "would_refine_by_radio", "would_refine_stereo_visits"):
        if held_after[key] != held_before[key]:
            raise ValueError(f"The held history changed {key}")
    return dict(packet=packet_delta(old, new, enroll), science=science(ctl, candidate),
                selector_gain_abs_delta=numerical_delta(held_before["choice"], held_after["choice"]),
                historical_control=ctl, candidate=candidate, compare_elapsed_s=monotonic()-t)


def watch(root, pin, pid):
    from .profiled_grid_export_admission import observe

    panel, old = load_panel()
    ready = json.loads(panel.check(root/"ready.json", pin))
    inputs = ready["input"]
    if (inputs != old["cases"][CASE] or ready["controller"] != callback.digest(Path(__file__).read_bytes())
            or ready["protocol"] != callback.digest(PROTOCOL.read_bytes()) or ready["cap_s"] != panel.CAP_SECONDS[CASE]):
        raise ValueError("The frozen run changed after qualification")
    assert_source(panel, inputs)
    panel.source_before(inputs, True)
    panel.check(panel.DRIVER, panel.DRIVER_PIN)
    panel.check(root/"charted-build.json", ready["build"])

    def launch(event):
        work = root/"run"
        with panel.LOCK.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = panel.source_before(inputs, True)
            panel.driver_window(event, pid, 0, CASE, pending_0218=False)
            panel.new_work(work)
            argv = ["/usr/bin/taskset", "-c", "2", "/usr/bin/ionice", "-c2", "-n7",
                    *worker_command(panel, root, work, inputs, ready["build"])]
            panel.write(work/"launch.json", dict(command=argv, event=event, before=before, ready_sha256=pin))
            faults = resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt
            process = panel.paired.child(argv, work, ready["cap_s"], lock.fileno())
            process["minor_faults"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_minflt-faults
            panel.write(work/"process.json", process)
            after = panel.residency(inputs["files"])
            panel.write(work/"source-after.json", after)
        return dict(status="completed_one_child", process=process, event=event, before=before, after=after)

    result = observe(launch, None)
    panel.write(root/"watch.json", result)
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "watch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--pin")
    cli.add_argument("--pid", type=int)
    a = cli.parse_args()
    if os.sched_getaffinity(0) != {3} or os.nice(0) < 15:
        cli.error("Run the controller on low-priority CPU3")
    if a.action == "prepare":
        print(prepare(a.root))
    elif a.action == "watch":
        print(json.dumps(watch(a.root, a.pin, a.pid)))
    else:
        panel, _ = load_panel()
        ready = json.loads(panel.check(a.root/"ready.json", a.pin))
        process = json.loads((a.root/"run/process.json").read_bytes())
        print(panel.write(a.root/"score.json", score(panel, a.root, ready, process)))


if __name__ == "__main__":
    main()
