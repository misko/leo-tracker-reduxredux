"""Preregister a new held whole-IQ comparison using the checked iq_compare runner."""

import argparse
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import cavity_runtime, corpus, iq_compare, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release
from .full_v5_check import _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "track-recovery/exact-wide-iq"
RELEASE = Path("/var/tmp/leo-wide-kernel-20261119/release/release.json")
METHOD = "exact-wide-iq"
LIBRARIES = {
    "control": "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66",
    "candidate": "758a0ccc4b61c4c8cc7fc96c23ea34bfea38eeb6e7c34cc225f28129cefae2d3",
}
EARLIER = (
    "acquisition-support/fresh-waveform",
    "acquisition-support/scout-budget",
    "acquisition-support/scout-full",
    "acquisition-support/deadline-repeat",
    "acquisition-support/thinned-capture",
    "detector-origins/whole-band",
    "detector-origins/whole-pressure",
    "detector-origins/paired-epochs-full",
    "receiver-core/full-stride",
    "receiver-core/whole-winner",
    "receiver-core/hinted-whole",
    "integration/whole-memory-chain",
    "integration/whole-memory-chain/ds26",
    "integration/whole-cavity",
    "inference/raw-stream",
    "next/direct-whole",
    "recovery/clock-chain",
    "streamlined/whole-pair",
    "streamlined/iq-schedule",
    "streamlined/whole-fractional",
)
ID = re.compile(r"DS\d{2}-\d{4}")


def scheduled(pins):
    ids = set()
    for name in ("cases", "recording_order", "roster", "inputs", "case"):
        field = pins.get(name, [])
        if isinstance(field, str):
            field = [field]
        if not isinstance(field, (list, tuple, dict)):
            continue
        for item in field:
            ident = item.get("id") if isinstance(item, dict) else item
            if isinstance(ident, str) and ID.fullmatch(ident):
                ids.add(ident)
    return sorted(ids)


def exclusions():
    paths = {SCREEN / name / "source-lock.json" for name in EARLIER}
    for path in SCREEN.rglob("source-lock.json"):
        if path.parent == REPORT:
            continue
        source = whole_iq.read(path)
        if "tools/pipeline_eval/iq_compare.py" in source.get("programs", {}):
            paths.add(path)
    return {
        str(path.relative_to(SCREEN)): dict(cases=scheduled(whole_iq.read(path)), sha256=_sha(path))
        if path.is_file()
        else {"receipt_missing": True}
        for path in sorted(paths)
    }


def ranked(inputs, panel, excluded):
    candidates = []
    for ident in panel:
        row = inputs[ident]
        if not row.get("unavailable") and row.get("recording") and ident not in excluded:
            candidates.append((row["recording"]["segments"][0]["sha256"], ident))
    return sorted(candidates)


def select():
    old = exclusions()
    excluded = {ident for item in old.values() for ident in item.get("cases", [])}
    roster, hashes = corpus._selection("ds26-common127")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    ds29 = [i for i in corpus._selection("roof16")[0] if i.startswith("DS29-")]
    results, ledger = [], {}
    for panel, ids, cpus, first in (
        ("DS26", roster, [16, 17], "control"),
        ("DS29", ds29, [18, 19], "candidate"),
    ):
        pool = ranked(inputs, ids, excluded)
        rows = ledger[panel] = dict(held_candidates=pool, checked=[])
        batches = [(pool, "new-holdout")]
        if panel == "DS29":
            batches.append((ranked(inputs, [i for i in ids if i in excluded], set()), "historical"))
        for batch, cohort in batches:
            for digest, ident in batch:
                try:
                    case, _ = whole_iq.binding(ident)
                    capture = capture_release.read_capture(case)
                except (OSError, ValueError) as error:
                    rows["checked"].append(dict(id=ident, ineligible=str(error)))
                    continue
                rows["selected"] = dict(
                    id=ident,
                    first_segment_sha256=digest,
                    cohort=cohort,
                    recording_authority=capture["input_manifest_sha256"],
                )
                results.append(dict(id=ident, cpus=cpus, first=first, cohort=cohort))
                break
            else:
                continue
            break
        else:
            raise ValueError(f"no supported complete capture remains for {panel}")
    return results, dict(sources=old, exclusions=sorted(excluded), selection=ledger)


def prepare(base):
    if (REPORT / "experiment.json").exists():
        raise FileExistsError("the held wide-IQ protocol already has a frozen experiment")
    release = whole_iq.read(RELEASE)
    base.mkdir(exist_ok=False)
    libraries = {}
    for role, pin in LIBRARIES.items():
        if release[role]["sha256"] != pin:
            raise ValueError("wide release has different signed libraries")
        library = base / f"wide-{role}.so"
        shutil.copyfile(whole_iq.checked(Path(release[role]["path"]), pin), library)
        whole_iq.checked(library, pin)
        libraries[role] = library
    cases, authority = select()
    save_json(REPORT / "selection.json", authority)
    spec = REPORT / "experiment.json"
    save_json(
        spec,
        dict(
            id=METHOD,
            cases=cases,
            limit_s=450,
            title="Exact wide detector on held complete IQ",
            caption=(
                "Fresh same-IQ pairs under 512 MiB and zero swap with unchanged phase release. "
                "Original v5 curves use capture-era observations."
            ),
            control=dict(sha256=LIBRARIES["control"], label="Stock wide detector"),
            candidate=dict(sha256=LIBRARIES["candidate"], label="Exact wide-kernel refactor"),
            selection_sha256=_sha(REPORT / "selection.json"),
            native_release_sha256=_sha(RELEASE),
            launcher_sha256=_sha(Path(__file__)),
        ),
    )
    receiver = cavity_runtime.install(base / "receiver", profile="phase-release")
    iq_compare.prepare(spec, REPORT / "PROTOCOL.md", receiver, libraries, base / "runs")
    print(cases, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "run"))
    p.add_argument("base", type=local_output)
    args = p.parse_args()
    if args.action == "prepare":
        prepare(args.base)
    else:
        work = args.base / "runs"
        plan = whole_iq.read(
            whole_iq.checked(
                work / "source-lock.json",
                (work / "source-lock.sha256").read_text().strip(),
            )
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda ident: iq_compare.run(work, ident), plan["cases"]))


if __name__ == "__main__":
    main()
