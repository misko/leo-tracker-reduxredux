"""Measure three existing exact ports in the complete combined saved worker."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import resource
from shutil import copytree
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

BASE = Path("/dev/shm/leo-v3-combined-0359-blind01")
READY = BASE.with_name(BASE.name + "-ready")
PRIOR_PIN = "f226ee36a27b16fcd0b99b375a9a9fe22e56fa34531eec5e3fb1253173bd08da"
SEAL_PIN = "0f7fac1871530a19a67dd2a6a425d290f1354c6cff51211a8635dedcab3f2763"
READY_PIN = "f962e62ae745c53b9831d87944de90fa60a30d245b2daadfb9e5cea7a8f92712"
JOB_PIN = "f23695ff5869ccf9e553f844d2637e6f69355a11aa7fb18d7ada8531cb502dff"
INTEGRATED = Path("/dev/shm/leo-v3-integrated-original-02/DS30-0016/admission.json")
INTEGRATED_PIN = "35d027c8a515882b87e15de2a3921506fa2f0543ae4d206cb7d883557b0ac77b"
SCENE = "accepted-orbit-lanes.pickle"
PROTOCOL = HERE / "ds30-0359-cairo-saved-protocol.md"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def presentation_pins():
    from empty_bootstrap import checked
    from history_cairo_render import SOURCES
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA

    physical = json.loads(checked(INTEGRATED, INTEGRATED_PIN))
    names = (*SOURCES, "verified_rgba.py", "verified_rgba_rows.c", "verified_png_reads.py",
             "single_rank_refusal.py", "integrated_original_entry.py")
    pins = {str((HERE / name).relative_to(ROOT)): digest(HERE / name) for name in names}
    if any(physical["sources"][name] != pin for name, pin in pins.items()):
        raise ValueError("The current presentation ports differ from the verified integrated entry")
    checked(PNG_LIBRARY, PNG_SHA)
    return pins


@contextmanager
def orbit_capture(binding, scan, audit, scene_calls):
    from direct_orbit_figures import scene
    import direct_orbit_figures

    def capture(lanes, **options):
        if scene_calls:
            raise ValueError("Expected one live orbit scene for the standard views")
        scene_calls.append((tuple(lanes), options))
        return scene(lanes, **options)

    with binding(scan, audit, orbit_sheets=True), patch.object(direct_orbit_figures, "scene", capture):
        yield


def worker(root):
    from aperture_trial import write
    import history_cairo_render as layout
    from integrated_original_entry import verification_factory
    from single_rank_refusal import single_rank_refusal
    import verified_png_reads as png
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from empty_bootstrap import clock, now

    book = read(root / "admission.json")
    if book["presentation_sources"] != presentation_pins() or book["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("The candidate presentation or protocol changed")
    calls, native = [], {}
    render = layout.binding

    def six(scan, audit, *, orbit_sheets):
        if orbit_sheets:
            raise ValueError("The original saved entry no longer uses the matched ordinary orbit views")
        return orbit_capture(render, scan, audit, calls)

    with (patch.object(layout, "binding", six), single_rank_refusal(),
          patch.object(png, "VerifiedPngReads", verification_factory(png.VerifiedPngReads, native))):
        original.worker(root, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    started = now()
    if len(calls) == 1:
        with (root / SCENE).open("xb") as stream:
            pickle.dump(calls[0], stream, protocol=5)
    write(root / "publication-ports.json", dict(native_png=native, live_orbit_calls=len(calls), scene_export=clock(started)))


def probe():
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from verified_rgba import RgbaEvidence

    result = original.probe(job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    presentation_pins()
    if not RgbaEvidence(PNG_LIBRARY, PNG_SHA, None, {}).ready or "leo" in sys.modules:
        raise ValueError("The exact isolated entry or native PNG ABI is unavailable")
    print(json.dumps(result | {"verified_native_png": True}))


def launch(root, *, entry=None, extra_sources=None, protocol=PROTOCOL):
    import combined_successor_0289 as combined
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, checked, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    started = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    previous = json.loads(checked(resident_path(BASE / "result.json"), PRIOR_PIN))
    sealed = json.loads(checked(resident_path(BASE / "prediction-seal.json"), SEAL_PIN))
    old, machine, release = previous["admission"], host(), verified_v3(NAMED_V3)
    pins, libs = original.pinned_sources(), combined.admitted_libraries()
    extras = {"presentation_sources": presentation_pins()} if extra_sources is None else extra_sources()
    original.ready(check_assignment=False, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    if (old["machine"] != machine or old["installed_release"] != release or old["job_sha256"] != JOB_PIN
            or old["ready_admission_sha256"] != READY_PIN or old["sources"] != pins or old["libraries"] != libs
            or sealed != output_seal(BASE) or previous["prediction_seal_sha256"] != SEAL_PIN):
        raise ValueError("The original paid controls or identical declared input changed")
    bound, req = load_job(resident_path(READY / "job.json"), JOB_PIN)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    if len(refs) != 47 or sum(ref.byte_size for ref in refs) != 83_998_561:
        raise ValueError("The original causal scope changed")
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libs)])
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    (root / "routed").mkdir()
    copytree(BASE / "fonts", root / "fonts")
    write(root / "routed/binding.json", {"input": bound})
    argv = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve() if entry is None else entry)]
    prefix = ["/usr/bin/timeout", "--kill-after=2s"]
    command = [*prefix, "115s", *argv, "worker", str(root)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    setup = clock(started)
    smoke_started, usage = now(), resource.getrusage(resource.RUSAGE_CHILDREN)
    isolated = subprocess.run([*prefix, "15s", *argv, "probe"], env=env, capture_output=True, text=True, check=False)
    smoke = clock(smoke_started)
    end_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke["cpu_s"] += end_usage.ru_stime + end_usage.ru_utime - usage.ru_stime - usage.ru_utime
    write(root / "admission.json", dict(case="DS30-0359", command=command, sources=pins, libraries=libs,
          protocol_sha256=digest(protocol), machine=machine, job_sha256=JOB_PIN, commit=revision, setup=setup,
          original_controls_sha256=PRIOR_PIN, original_prediction_sha256=SEAL_PIN, **extras,
          resident=cache, archive_members=len(refs), installed_release=release, planned_candidate_children=1,
          smoke=dict(clock=smoke, exit_code=isolated.returncode, stdout=isolated.stdout, stderr=isolated.stderr),
          waveform_reads=0, backing_archive_reads=0))
    isolated.check_returncode()
    marker = "verified_native_png" if entry is None else "paired_grid_ready"
    if not json.loads(isolated.stdout)[marker]:
        raise ValueError("The isolated entry smoke did not verify the experimental port")
    write(root / "routed/clock.json", measure(command, env, root / "routed/candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "probe"))
    cli.add_argument("root", type=Path, nargs="?")
    args = cli.parse_args()
    if args.action == "probe":
        probe()
    else:
        {"launch": launch, "worker": worker}[args.action](args.root)
