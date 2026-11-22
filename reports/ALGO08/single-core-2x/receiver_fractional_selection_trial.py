"""Exercise the frozen publication entry on the existing 128-visit acquisition prefix."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from tools.pipeline_eval.qualification import experimental_publication
from tools.pipeline_eval.variants.experimental import lean_startup


VISITS = 128
BINDING = "sha256:c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c"
PARENT = "sha256:445744b4401d14d42a62130dca85882fd9062eb32627a9046e62205650dddb28"
ALL = "sha256:a546069457b70491949d3b500f65cffd26939e693d9079ddc6b37a55d26e2afa"
PARENT_LIBRARY = "b63cf5b0b70e142a246fefd40b7ceb8ba2a24ecf0b4e8d0a05c6901cdef5dd94"
ALL_LIBRARY = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
DEPLOYED_LIBRARY = "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809"


def acquire_prefix(bundle, parent, exact, binding, bulk):
    release = experimental_publication.RELEASE
    selected = json.loads((bundle / "spec.json").read_bytes())
    if not selected.get("fractional_score_selection"):
        raise ValueError("Expected a frozen selected-score receiver")
    if "sha256:" + sha256(binding.read_bytes()).hexdigest() != BINDING:
        raise ValueError("Physical input binding differs from the historical prefix")
    case = json.loads(binding.read_bytes())["case"]
    member = case["recording"]["segments"][0]
    entry = dict(path=str((bulk / member["path"]).parent), manifest_digest="sha256:" + member["sha256"])
    stock = release / "assets"
    paths = dict(parent=parent / "receiver.so", exact=exact / "receiver.so",
                 deployed=stock / "cancellation-factors.so")
    with TemporaryDirectory(prefix="fractional-prefix-") as temporary, ExitStack() as stack:
        scratch = Path(temporary)
        output = scratch / "publication"
        output.mkdir()
        for name, path in paths.items():
            directory = scratch / name
            directory.mkdir()
            (directory / "cancellation-factors.so").symlink_to(path)
            for edge in ("lower", "upper"):
                pilot = f"{edge}.f32"
                (directory / pilot).symlink_to(stock / pilot)

        def capture(recording, root, assets, archive, offer):
            from leo.contracts.digests import canonical_digest
            from leo.storage.fast_scan import FastSegmentSource
            from tools import algo08_scan
            from tools.pipeline_eval.qualification.blind_compact_run import detector as released

            if root != output or recording != Path(entry["path"]).parent:
                raise ValueError("Prefix trial must intercept the research acquisition boundary")
            for path, pin in ((parent, PARENT), (exact, ALL)):
                identity = canonical_digest(json.loads((path / "spec.json").read_bytes()))
                if identity != pin:
                    raise ValueError("Unexpected exact or spectral comparison bundle")
            pins = dict(parent=PARENT_LIBRARY, exact=ALL_LIBRARY,
                        deployed=DEPLOYED_LIBRARY, selected=selected["detector_sha256"])
            for name, path in paths.items():
                if sha256(path.read_bytes()).hexdigest() != pins[name]:
                    raise ValueError("Receiver timing control differs from its pin")
            original = FastSegmentSource(entry, stop_sequence=VISITS)
            windows = list(original.windows())
            if len(windows) != VISITS:
                raise ValueError("Historical prefix is incomplete")
            prefix = SimpleNamespace(receiver_ids=original.receiver_ids, reader=original.reader,
                                     radio=original.radio, windows=lambda: iter(windows))
            inventory = dict(segments=[entry], window_count=VISITS)
            inventory_sha = canonical_digest(["historical-prefix", entry["manifest_digest"], VISITS])

            def bound_prefix(request):
                if request != entry:
                    raise ValueError("Unexpected segment outside the 128-visit prefix")
                return prefix

            detectors = dict.fromkeys(paths, released) | {"selected": algo08_scan.detector}
            directories = {name: scratch / name for name in paths} | {"selected": assets}
            args = ("DS30-0016-prefix", inventory_sha, inventory)
            timing = []
            documents = {}
            order = ("parent", "exact", "selected", "deployed")
            with patch.object(algo08_scan, "FastSegmentSource", bound_prefix):
                for repeat in range(len(order)):
                    elapsed = {}
                    for arm in order[repeat:] + order[:repeat]:
                        with (patch.object(algo08_scan, "detector", detectors[arm]),
                              patch.dict(algo08_scan.PINS, {"cancellation-factors.so": pins[arm]})):
                            start = process_time_ns()
                            document = algo08_scan.acquire(*args, directories[arm])
                            elapsed[arm] = process_time_ns() - start
                        if documents.setdefault(arm, document) != document:
                            raise ValueError("A fresh acquisition context produced different evidence")
                    timing.append(elapsed)
            return dict(prefix=compare(documents, timing) | dict(
                specification=canonical_digest(selected), binaries=pins,
                inputs=inventory_sha, visit_count=VISITS,
            ))

        install = lean_startup.install

        def intercept_acquisition():
            install()
            from tools import algo08_scan

            stack.enter_context(patch.object(algo08_scan, "analyze", capture))

        stack.enter_context(patch.object(lean_startup, "install", intercept_acquisition))
        result = experimental_publication.run(SimpleNamespace(
            recording=Path(entry["path"]).parent, bulk_root=output,
            archive=bulk / "leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0016/tle",
            region=release / "station/region.json",
        ), selected)
        if any(output.iterdir()):
            raise ValueError("The bounded trial unexpectedly published an artifact")
    counts = result["fractional_score_selection"]
    repeats = len(result["prefix"]["cpu_ns"])
    if any(count % repeats for count in counts.values()):
        raise ValueError("Fractional recovery counts differ across acquisition repeats")
    return result["prefix"] | dict(repairs_per_repeat={key: count // repeats
                                                       for key, count in counts.items()})


def compare(documents, timing):
    from leo.contracts.digests import canonical_digest

    stock = documents["deployed"]
    original = stock["source"]["probes"]
    fixed = ("clock_anchor", "delivery_clocks", "last_sample_counter")
    fields = ("window_count", "processed_windows", "invalid_capture", "excluded_windows", "skipped_fast_score")
    raw = stock["source"]["raw_recording_authority_digest"]
    for name, document in documents.items():
        if (document["source"]["raw_recording_authority_digest"] != raw
                or any(document[key] != stock[key] for key in fixed)
                or any(document["provenance"][key] != stock["provenance"][key] for key in fields)):
            raise ValueError(f"{name} acquisition changed capture eligibility or authority")
    digests = {name: canonical_digest(doc["source"]["probes"]) for name, doc in documents.items()}
    if len({digests[key] for key in ("deployed", "exact", "selected")}) != 1:
        raise ValueError("Selected repair did not restore the exact production acquisition rows")
    if any(len(row["candidates"]) > 1 for row in original):
        raise ValueError("Acquisition published an unselected factor")
    accepted = [row for row in original if row["candidates"]]
    if len(accepted) != 53 or sum(row["candidates"][0]["candidate_rank"] == 1 for row in accepted) != 1:
        raise ValueError("Expected 53 retained factors and one retained residual")
    return dict(raw_authority=raw, probe_sha256=digests, lane_rows=len(original), selected=len(accepted),
                selection_sha256=canonical_digest(accepted), cpu_ns=timing,
                median_cpu_ns={arm: median(row[arm] for row in timing) for arm in documents},
                paired_change={arm: median(row[arm] / row["parent"] - 1 for row in timing)
                               for arm in ("exact", "selected")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bundle", "parent", "exact", "binding", "bulk"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    print(json.dumps(acquire_prefix(**vars(parser.parse_args())), indent=2))
