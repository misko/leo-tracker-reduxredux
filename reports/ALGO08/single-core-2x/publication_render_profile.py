"""Measure the frozen renderer and publication tail on two sealed saved inputs."""

import argparse
import cProfile
import json
import pstats
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from .residual_attribution_trial import RELEASE, saved_native

SPEC = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"


@contextmanager
def residual_scatter(*, skip=False):
    from matplotlib.axes import Axes

    original = Axes.scatter
    counts = Counter()
    initialized = set()

    def scatter(axis, x, y, *args, **kwargs):
        # These are the prescribed residual series. The replay still creates
        # every nonempty collection in its original order with original colors.
        empty = (type(x) is list and not x and type(y) is list and not y
                 and not args and kwargs.keys() == {"s", "c"} and kwargs["s"] == 5)
        counts["empty" if empty else "other"] += 1
        # The first empty collection still initializes autoscaling. An empty
        # lane followed only by axhline has different limits without it.
        if not empty or not skip or axis not in initialized:
            if empty:
                initialized.add(axis)
            return original(axis, x, y, *args, **kwargs)
        counts["omitted"] += 1
        return None

    with patch.object(Axes, "scatter", scatter):
        yield counts


def profile_rows(profile):
    stats = pstats.Stats(profile)
    rows = [dict(source=key[0], line=key[1], name=key[2], calls=row[1],
                 self_s=row[2], inclusive_s=row[3]) for key, row in stats.stats.items()]
    return {name: sorted(rows, key=lambda row: -row[field])[:55] for name, field in
            (("self", "self_s"), ("inclusive", "inclusive_s"))}


def render_tail(pair_path, bundle, arm, pair_pin, legacy_archive=None):
    from tools.pipeline_eval.variants.experimental.lean_startup import install

    install()

    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore, immutable_json
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools import algo08_scan
    from tools.pipeline_eval import qualification
    from tools.pipeline_eval.qualification import experimental_publication

    from .raster_layout_trial import compare

    helper_path = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/qualification"
    with patch.object(qualification, "__path__", [*qualification.__path__, str(helper_path)]):
        from tools.pipeline_eval.qualification.paired_publication import (
            archive_identity,
            verify_sources,
        )

    raw_pair = pair_path.read_bytes()
    if sha256(raw_pair).hexdigest() != pair_pin:
        raise ValueError("The saved paired receipt differs")
    pair = json.loads(raw_pair)
    specification = json.loads((bundle / "spec.json").read_bytes())
    if (canonical_digest(specification) != SPEC or
            not Path(experimental_publication.__file__).is_relative_to(bundle)):
        raise ValueError("Expected the original frozen launcher")
    verify_sources(bundle / "reports/ALGO08/single-core-2x/run-candidate", specification["sources"])
    row = pair["runs"][arm]
    # The frozen deployment's workspace port predates its create=False form.
    # Require the existing saved terminal before adapting the port signature.
    run_id = row["receipt"]["run_id"]
    terminal = pair_path.parent / arm / "fast-scan-automatic-work" / run_id / "terminal.json"
    if not terminal.is_file():
        raise ValueError("Expected an existing terminal receipt")
    workspace = FastScanStore.automatic_workspace
    with patch.object(FastScanStore, "automatic_workspace",
                      lambda store, name, create=True: workspace(store, name)):
        native = saved_native(pair_path, arm, row)
    detector = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    if arm == "candidate" and pair["candidate_specification_digest"] != SPEC:
        raise ValueError("Expected detections from the chosen frozen receiver")
    if arm == "baseline":
        # The older physical packet already binds the deployed detector. Keep
        # its acquisition pin, and leave the frozen solver and renderer intact.
        library = RELEASE / "assets/cancellation-factors.so"
        if sha256(library.read_bytes()).hexdigest() != detector:
            raise ValueError("Physical input differs from the pinned deployed detector")
        specification.update(detector=str(library), detector_sha256=detector)
    # The startup hook is installed above and the trial has no raw ingress.
    specification.update(ingress="stock", member_lookahead=False, startup="stock")
    specification.pop("paired_sha256", None)
    if "archive" in pair:
        archive = Path(pair["archive"]["root"])
        if archive_identity(archive) != pair["archive"]:
            raise ValueError("Saved causal archive has changed")
    elif arm == "baseline" and legacy_archive is not None:
        archive = legacy_archive
    else:
        raise ValueError("A legacy physical pair needs the archive used by its publication")
    region = Path(pair["region"])
    recording = Path(pair["recording"])
    caller = algo08_scan.analyze
    recorded = {}

    def prepared(recording, root, assets, causal_archive, offer):
        if offer.document() != row["receipt"]["region"]:
            raise ValueError("Unexpected offer in the render replay")
        prediction, packet, _ = result = algo08_scan.solve(
            native, TleArchiveReader(causal_archive), assets, offer)
        if prediction["status"] != "ok" or packet is None:
            raise ValueError("Expected a renderable saved packet")
        if {name: slot["endpoint_latlon"] for name, slot in packet["arms"].items()} != {
                name: slot["latlon"] for name, slot in row["arms"].items()}:
            raise ValueError("Saved position endpoints differ")
        render, publish, artifact = (algo08_scan.render, FastStandardAnalysisStore.publish,
                                     FastStandardAnalysisStore.artifact)
        detector_id = "algo08-v2-" + canonical_digest([
            algo08_scan.ALGO08V2, native["source"]["input_manifest_sha256"]])[7:39]
        profile = cProfile.Profile()
        images, timings, counts = {}, [], {}

        def prohibit_raw(*args, **kwargs):
            raise RuntimeError("The saved-publication trial cannot acquire raw I/Q")

        for index, mode in enumerate(("profile", "frozen", "skip", "skip", "frozen")):
            fresh = root / f"trial-{index}"
            fresh.mkdir()
            saved = FastScanStore(fresh).automatic_workspace(detector_id) / "detections.json"
            immutable_json(saved, native)
            elapsed = {}

            def time(name, fn, elapsed=elapsed):
                def timed(*args, **kwargs):
                    cpu, wall = process_time(), perf_counter()
                    out = fn(*args, **kwargs)
                    elapsed[name+"_cpu_s"] = elapsed.get(name+"_cpu_s", 0) + process_time() - cpu
                    elapsed[name+"_wall_s"] = elapsed.get(name+"_wall_s", 0) + perf_counter() - wall
                    return out

                return timed

            def draw(*args, mode=mode, **kwargs):
                count = residual_scatter(skip=mode == "skip")
                with count as calls, profile if mode == "profile" else nullcontext():
                    out = render(*args, **kwargs)
                counts[mode] = calls
                if mode in images and images[mode] != out:
                    raise ValueError("Repeated rendering changed the publication bytes")
                images[mode] = out
                return out

            original_reference = pair.get("evaluation_reference")
            with ExitStack() as stack:
                stack.enter_context(patch.object(algo08_scan, "acquire", prohibit_raw))
                stack.enter_context(patch.object(algo08_scan, "solve", lambda *_: result))
                stack.enter_context(patch.object(algo08_scan, "render", time("render", draw)))
                stack.enter_context(patch.object(FastStandardAnalysisStore, "publish",
                                                 time("publish", publish)))
                stack.enter_context(patch.object(FastStandardAnalysisStore, "artifact",
                                                 time("verify", artifact)))
                report = time("analyze", caller)(recording, fresh, assets, causal_archive, offer,
                                                 reference=original_reference)
            if report["decision"] != "complete" or report["run_id"] != row["receipt"]["run_id"]:
                raise ValueError("Saved caller returned another publication identity")
            timings.append(dict(mode=mode, **elapsed))

        store = FastStandardAnalysisStore(pair_path.parent / arm)
        published = {entry["name"]: store.artifact(row["receipt"]["run_id"], entry["name"],
                                                    entry["sha256"]) for entry in row["artifacts"]}
        figures = compare(images["frozen"], images["skip"])
        try:
            original = compare(published, images["frozen"])
        except ValueError as error:
            if arm == "candidate":
                raise
            original = dict(archived_panel_mismatch=str(error))
        medians = {mode: median(t["render_cpu_s"] for t in timings if t["mode"] == mode)
                   for mode in ("frozen", "skip")}
        recorded.update(
            profile=profile_rows(profile), counts=counts, timings=timings, figures=figures,
            control=original, observations=len(packet["observations"]),
            fitted_rows=len(packet["rows"]["fitted_c"]),
            satellites=len({r["norad"] for r in packet["rows"]["fitted_c"]}),
            region=offer.document(), raw_authority=row["raw_authority"], render_cpu_s=medians,
        )
        return report

    with TemporaryDirectory(prefix="leo-frozen-render-") as directory:
        args = SimpleNamespace(recording=recording, bulk_root=Path(directory),
                               archive=archive, region=region)
        with patch.object(algo08_scan, "analyze", prepared):
            experimental_publication.run(args, specification)
    return dict(recorded, pair_sha256=pair_pin, arm=arm, frozen=SPEC, recording=str(recording))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pair_path", "bundle"):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    parser.add_argument("arm", choices=("baseline", "candidate"))
    parser.add_argument("pair_pin")
    parser.add_argument("--legacy-archive", type=Path)
    print(json.dumps(render_tail(**vars(parser.parse_args())), indent=2, allow_nan=False))
