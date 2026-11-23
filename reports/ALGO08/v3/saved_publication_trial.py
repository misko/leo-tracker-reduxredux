"""Compare the eight genuine publication figures on one restored saved fit."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, machine, write
from joint_publication import full_catalogue_route
from saved_publication_layout import layout_only_prepass


RECEIPT_SHA = "b1aa36bba0f476dc4539e10f105138daa268b1b486d9dc04ca2141a9f03dedfd"
REQUEST_SHA = "d58723098826fc7e1478f92880dffdb500bcb3f5225b4d64a4b2949cfbceab06"
NATIVE_SHA = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
ORDER = ("installed", "layout", "layout", "installed")
REVERSED_ORDER = ("layout", "installed", "installed", "layout")


def sealed(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Saved file differs from its pin at {path}")
    return json.loads(data)


def clocks():
    return process_time_ns(), perf_counter_ns()


def since(start):
    return dict(cpu_ns=process_time_ns()-start[0], wall_ns=perf_counter_ns()-start[1])


def image_evidence(payload):
    from PIL import Image

    with Image.open(BytesIO(payload)) as png:
        png.load()
        return dict(size=list(png.size), mode=png.mode, metadata=png.info,
                    sha256="sha256:" + sha256(payload).hexdigest(),
                    rgba_sha256=sha256(png.convert("RGBA").tobytes()).hexdigest())


def render_trial(packet, native, title, original, output, renderer, order):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.algo08_scan import scan_report
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng

    run = original["manifest"]["run_id"]
    if original["evidence"]["images"].keys() != set(PLOTS):
        raise ValueError("Expected complete eight-plot physical evidence")
    attempts = []
    original_encoder = LosslessPng._encode
    for index, arm in enumerate(order):
        encode_ns = encodes = 0

        def encode(*args, **options):
            nonlocal encode_ns, encodes
            start = process_time_ns()
            result = original_encoder(*args, **options)
            encode_ns += process_time_ns()-start
            encodes += 1
            return result

        with (layout_only_prepass(enabled=arm == "layout") as prepasses,
              patch.object(LosslessPng, "_encode", encode)):
            start = clocks()
            images = renderer(packet, title=title, evaluation_reference=None)
            render = since(start)
        if set(images) != set(PLOTS):
            raise ValueError("A rendered bundle omitted original figures")
        root = output / f"render-{index}"
        root.mkdir()
        store, scan = FastStandardAnalysisStore(root), FastScanStore(root)
        manifest = {name: value for name, value in original["manifest"].items() if name != "artifacts"}
        start = clocks()
        store.publish(run, manifest, images, position_grid=original["grid"], position_path=original["path"])
        for entry in original["manifest"]["artifacts"]:
            _ = store.artifact(run, entry["name"])
        store_time = since(start)
        start = clocks()
        report = scan_report(title, run, native)
        scan.publish(run, report)
        report_time = since(start)
        figures = {name: image_evidence(images[name]) for name in PLOTS}
        matches = {name: figures[name] == original["figures"][name] for name in PLOTS}
        official = json.loads((store.folder(run) / "manifest.json").read_bytes())
        science = dict(manifest=official == original["manifest"],
                       path=canonical_digest(store.position_path(run)) == original["evidence"]["path"],
                       grid=canonical_digest(store.position_grid(run)) == original["evidence"]["grid"],
                       scan_report=canonical_digest(report) == original["report_sha256"])
        attempts.append(dict(arm=arm, render=render, store=store_time, scan_report=report_time,
                             prepasses=dict(prepasses), encode=dict(cpu_ns=encode_ns, images=encodes),
                             archive_exact=matches, official=science, figures=figures))
    return attempts


def verify_packet(packet, original, saved_receipt):
    from leo.contracts.digests import canonical_digest
    from leo.application.localization_v3_engine import _json_value

    def normalized(value):
        return canonical_digest(json.loads(json.dumps(value, default=_json_value)))

    rows = {arm: [[row["observation_id"], row["norad"], row["role"]] for row in owned]
            for arm, owned in packet["rows"].items()}
    matches = dict(owners=rows == saved_receipt["selected_rows"],
                   arms=normalized(packet["arms"]) == normalized(original["manifest"]["arms"]))
    for key in ("path", "grid"):
        fields = ("binding", "elapsed_seconds")
        left, right = ({k: v for k, v in document.items() if k not in fields}
                       for document in (packet["position_" + key], original[key]))
        matches[key] = normalized(left) == normalized(right)
    return matches


def run(pair, output, *, reverse=False):
    publication, spec = configuration()
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    state = machine()
    if (state["cpu"] != [2] or state["nice"] < 15 or "prio 7" not in state["ionice"]
            or any(v != "1" for v in state["threads"].values())):
        raise ValueError("Expected the shared low-priority one-core trial")
    request = sealed(pair / "request.json", REQUEST_SHA)
    root = pair / "candidate"
    prior = sealed(root / "joint-research-receipt.json", RECEIPT_SHA)
    receipt = prior["receipt"]
    run_id = receipt["run_id"]
    packet_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = sealed(packet_path, NATIVE_SHA)
    store = FastStandardAnalysisStore(root)
    manifest = json.loads((store.folder(run_id) / "manifest.json").read_bytes())
    terminal = sealed(root / "fast-scan-automatic-work" / run_id / "terminal.json", receipt["terminal_sha256"])
    archive = Path(request["archive"]["root"])
    if (prior["route"] != "complete" or receipt["decision"] != "complete" or manifest["terminal_sha256"] != receipt["terminal_sha256"]
            or terminal["native_sha256"] != canonical_digest(native) or archive_identity(archive) != request["archive"]):
        raise ValueError("The saved full-short publication or its original archive differs")
    figures = {entry["name"]: image_evidence(store.artifact(run_id, entry["name"], entry["sha256"]))
               for entry in manifest["artifacts"]}
    evidence = prior["evidence"]
    if any(any(figure[k] != value for k, value in evidence["images"][name].items())
           for name, figure in figures.items()):
        raise ValueError("The archived PNG bytes or decoded pixels changed")
    original = dict(manifest=manifest, figures=figures, evidence=evidence,
                    grid=store.position_grid(run_id), path=store.position_path(run_id),
                    report_sha256=canonical_digest(json.loads((root / "fast-scan-reports" / (run_id+".json")).read_bytes())))
    if any(canonical_digest(original[key]) != evidence[key] for key in ("grid", "path")):
        raise ValueError("Original official numerical result differs")
    if spec["rendering"] != "lossless-raster":
        raise ValueError("Expected the installed full raster encoder and layout")
    from early_region import before_fit
    from leo.operations.tle_archive import TleArchiveReader
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from full_short_raw import graph_config

    recovered = {}

    def analyze(recording, work, assets, archive_root, offer):
        if offer.document() != receipt["region"]:
            raise ValueError("The plotting packet offer changed")
        attempts, regional = [], []
        reader = TleArchiveReader(archive_root)
        original_config = algo08_position.TrackConfig
        start = clocks()
        with ExitStack() as context:
            prepared, _, _ = context.enter_context(handoff(reader))
            context.enter_context(reduced_grid())
            infer = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            infer = before_fit(infer, reader, regional_bound_guard.causal_probes, regional, prepared.match)
            context.enter_context(patch.object(v5_core, "infer", infer))
            context.enter_context(patch.object(algo08_position, "TrackConfig", lambda **cfg: graph_config(original_config(**cfg))))
            decision, packet, policy = algo08_scan.solve(native, reader, assets, offer)
        recovered["restore"] = since(start)
        if decision["status"] != terminal["decision"] or policy != terminal["orbit_policy"] or len(attempts) != 1:
            raise ValueError("The saved physical solve did not reproduce the raw terminal choice")
        matched = verify_packet(packet, original, prior)
        if not all(matched.values()):
            raise ValueError(f"Recovered numerical packet differs: {matched}")
        recovered.update(numerical=matched, comparisons=render_trial(packet, native, recording.name, original,
                                                                      work, algo08_scan.render, REVERSED_ORDER if reverse else ORDER))
        return {}

    with TemporaryDirectory(dir=pair.parent, prefix="leo-saved-publication-") as temp:
        scratch = Path(temp)
        args = SimpleNamespace(recording=scratch / Path(request["recording"]).name,
                               archive=archive, bulk_root=scratch, region=Path(request["region_file"]))
        with patch.object(algo08_scan, "analyze", analyze):
            publication.run(args, spec)
    write(output, dict(host=state, source=dict(receipt_sha256=RECEIPT_SHA, request_sha256=REQUEST_SHA,
                native_sha256=NATIVE_SHA, physical_cpu_s=prior["publication_cpu_s"],
                physical_solve_cpu_s=prior["solve"]["cpu_s"]), **recovered))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pair", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--reverse", action="store_true")
    run(**vars(parser.parse_args()))
