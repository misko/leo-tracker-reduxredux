"""Exercise the frozen publication entry on named 128-visit acquisition prefixes."""

import argparse
import json
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from tools.pipeline_eval.qualification import experimental_publication
from tools.pipeline_eval.variants.experimental import lean_startup

VISITS = 128
PHYSICAL_BINDINGS = {
    "DS30-0016": "c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c",
    "DS30-0008": "a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a",
}
SOUTH = "6bd1f26bfa0bedfcf3f100f8"
PANEL_SHA = "af81b50868cf70c519e64301c2831889ad851ae2509ae997a42315b15d00a17f"
SOUTH_MANIFEST = "d0ae1fee11210fff03da39c2f8ea2bbd1715cfa2bf78622d70e5977127b3eee2"
PARENT = "sha256:445744b4401d14d42a62130dca85882fd9062eb32627a9046e62205650dddb28"
ALL = "sha256:a546069457b70491949d3b500f65cffd26939e693d9079ddc6b37a55d26e2afa"
SELECTED = "sha256:e819d432e87d84f9f03e6df8e147fc7d2894e776c1db9e23e9b84113cb1e9e71"
PARENT_LIBRARY = "b63cf5b0b70e142a246fefd40b7ceb8ba2a24ecf0b4e8d0a05c6901cdef5dd94"
ALL_LIBRARY = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
DEPLOYED_LIBRARY = "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809"
SCORE_FIELDS = ("fractional_exact_score", "fractional_control_score", "fractional_margin")
ARCHIVED_PROBE_PREFIXES = {
    "DS30-0008": {
        "deployed": "sha256:3cee5442affabf0c7ad6f8d17281bc5f0ebfdec465e1a4238261fd45d3217c6e",
        "selected": "sha256:3cee5442affabf0c7ad6f8d17281bc5f0ebfdec465e1a4238261fd45d3217c6e",
    },
    "public-south": {
        "deployed": "sha256:29c3bdd22920e397cbc0350122b3c7475f7afb0f4eb4a3ca2a1ac93e1dafb344",
        "parent": "sha256:0a6c8f0e1cd66a4222bd7bd1d3cc0d9a8d910d4f4fac1ef7846dec4621b69182",
    },
}


@dataclass(frozen=True)
class Prefix:
    name: str
    entry: dict
    archive: Path
    edge: str | None
    input_sha256: str


def prefix_plan(name, binding, bulk):
    content = binding.read_bytes()
    expected = PANEL_SHA if name == "public-south" else PHYSICAL_BINDINGS[name]
    if sha256(content).hexdigest() != expected:
        raise ValueError("Input document differs from the declared acquisition prefix")
    authority = json.loads(content)
    if name == "public-south":
        if SOUTH not in {row["recording"] for row in authority["jobs"]}:
            raise ValueError("The declared southern simulation is absent from the panel")
        entry = dict(path=str(binding.parent / SOUTH), manifest_digest="sha256:" + SOUTH_MANIFEST)
        return Prefix(name, entry, binding.parent / "tle", "upper", expected)
    case = authority["case"]
    if case["id"] != name:
        raise ValueError("Physical binding identifies a different recording")
    member = case["recording"]["segments"][0]
    entry = dict(path=str((bulk / member["path"]).parent),
                 manifest_digest="sha256:" + member["sha256"])
    archive = bulk / "leo-dev/ds30-full-20261121/snapshot/inputs" / name / "tle"
    return Prefix(name, entry, archive, "lower" if name == "DS30-0008" else None, expected)


def acquire_prefix(bundle, parent, exact, binding, bulk, case="DS30-0016"):
    release = experimental_publication.RELEASE
    selected = json.loads((bundle / "spec.json").read_bytes())
    if not selected.get("fractional_score_selection"):
        raise ValueError("Expected a frozen selected-score receiver")
    plan = prefix_plan(case, binding, bulk)
    entry = plan.entry
    segment = Path(entry["path"])
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

            if root != output or recording != segment:
                raise ValueError("Prefix trial must intercept the research acquisition boundary")
            for path, pin in ((parent, PARENT), (exact, ALL), (bundle, SELECTED)):
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
            if [window.acquisition["global_visit"] for window in windows] != list(range(VISITS)):
                raise ValueError("Historical prefix is incomplete")
            edges = {window.target["edge"] for window in windows}
            if len(edges) != 1 or (plan.edge is not None and edges != {plan.edge}):
                raise ValueError("The sealed prefix uses a different pilot edge")
            prefix = SimpleNamespace(receiver_ids=original.receiver_ids, reader=original.reader,
                                     radio=original.radio, windows=lambda: iter(windows))
            inventory = dict(segments=[entry], window_count=VISITS)
            inventory_sha = canonical_digest([
                "historical-prefix", entry["manifest_digest"], VISITS,
            ])

            def bound_prefix(request):
                if request != entry:
                    raise ValueError("Unexpected segment outside the 128-visit prefix")
                return prefix

            detectors = dict.fromkeys(paths, released) | {"selected": algo08_scan.detector}
            directories = {name: scratch / name for name in paths} | {"selected": assets}
            args = (f"{plan.name}-prefix", inventory_sha, inventory)
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
                            raise ValueError("A fresh acquisition changed the probe evidence")
                    timing.append(elapsed)
            report = compare(documents, timing)
            archived = ARCHIVED_PROBE_PREFIXES.get(plan.name, {})
            if any(report["probe_sha256"][arm] != pin for arm, pin in archived.items()):
                raise ValueError("Replayed prefix differs from the archived publication probes")
            if plan.name == "DS30-0016" and report["selected_rank_counts"]["deployed"] != {
                0: 52, 1: 1,
            }:
                raise ValueError("Expected 53 retained factors and one retained residual")
            return dict(prefix=report | dict(
                specification=canonical_digest(selected), binaries=pins,
                inputs=inventory_sha, visit_count=VISITS, case=plan.name,
                pilot_edge=next(iter(edges)),
                input_document_sha256=plan.input_sha256, segment_sha256=entry["manifest_digest"],
                iq_sha256=canonical_digest([window.iq_sha256 for window in windows]),
                archived_probe_sha256=archived,
            ))

        install = lean_startup.install

        def intercept_acquisition():
            install()
            from tools import algo08_scan

            stack.enter_context(patch.object(algo08_scan, "analyze", capture))

        stack.enter_context(patch.object(lean_startup, "install", intercept_acquisition))
        result = experimental_publication.run(SimpleNamespace(
            recording=segment, bulk_root=output, archive=plan.archive,
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


def parent_differences(deployed, parent):
    from leo.contracts.digests import canonical_digest

    counts = Counter(changed_availability=0, changed_selected_identity_or_gate=0,
                     changed_score_rows=0)
    maximum = dict.fromkeys(SCORE_FIELDS, 0.)
    for original, candidate in zip(deployed, parent, strict=True):
        if dict(original, candidates=[]) != dict(candidate, candidates=[]):
            raise ValueError("The spectral parent changed probe ordering or metadata")
        a, b = original["candidates"], candidate["candidates"]
        if len(a) != len(b):
            counts["changed_availability"] += 1
            continue
        if not a:
            continue
        a, b = a[0], b[0]
        left, right = ({key: value for key, value in row.items() if key not in SCORE_FIELDS}
                       for row in (a, b))
        if canonical_digest(left) != canonical_digest(right):
            counts["changed_selected_identity_or_gate"] += 1
        changed = False
        for key in SCORE_FIELDS:
            if float(a[key]).hex() != float(b[key]).hex():
                changed = True
                maximum[key] = max(maximum[key], abs(a[key] - b[key]))
        counts["changed_score_rows"] += changed
    return dict(counts=counts, max_abs_score_delta=maximum)


def compare(documents, timing):
    from leo.contracts.digests import canonical_digest

    stock = documents["deployed"]
    original = stock["source"]["probes"]
    fixed = ("clock_anchor", "delivery_clocks", "last_sample_counter")
    fields = ("window_count", "processed_windows", "invalid_capture", "excluded_windows",
              "skipped_fast_score")
    raw = stock["source"]["raw_recording_authority_digest"]
    for name, document in documents.items():
        if (document["source"]["raw_recording_authority_digest"] != raw
                or any(document[key] != stock[key] for key in fixed)
                or any(document["provenance"][key] != stock["provenance"][key] for key in fields)):
            raise ValueError(f"{name} acquisition changed capture eligibility or authority")
    probes = {name: doc["source"]["probes"] for name, doc in documents.items()}
    digests = {name: canonical_digest(rows) for name, rows in probes.items()}
    if len({digests[key] for key in ("deployed", "exact", "selected")}) != 1:
        raise ValueError("Selected repair did not restore the exact production acquisition rows")
    if any(len(row["candidates"]) > 1 for rows in probes.values() for row in rows):
        raise ValueError("Acquisition published an unselected factor")
    accepted = [row for row in original if row["candidates"]]
    ranks = {name: Counter(row["candidates"][0]["candidate_rank"]
                           for row in rows if row["candidates"]) for name, rows in probes.items()}
    return dict(raw_authority=raw, probe_sha256=digests, lane_rows=len(original),
                selected=len(accepted),
                selected_rank_counts=ranks, invalid_capture=stock["provenance"]["invalid_capture"],
                parent_differences=parent_differences(original, probes["parent"]),
                selection_sha256=canonical_digest(accepted), cpu_ns=timing,
                median_cpu_ns={arm: median(row[arm] for row in timing) for arm in documents},
                paired_change={arm: median(row[arm] / row["parent"] - 1 for row in timing)
                               for arm in ("exact", "selected")},
                selected_vs_exact=median(row["selected"] / row["exact"] - 1 for row in timing))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bundle", "parent", "exact", "binding", "bulk"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    parser.add_argument("--case", choices=(*PHYSICAL_BINDINGS, "public-south"), default="DS30-0016")
    print(json.dumps(acquire_prefix(**vars(parser.parse_args())), indent=2))
