"""Seal causal prefix choices and authenticate the normal mixed native inputs."""

import argparse
import csv
import gzip
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from .. import whole_iq
from ..__main__ import ROOT, save_json
from ..variants import coherent_peak_filter
from ..variants import prefix_evidence as prefix
from . import complete_timing, receiver_choice_panel
from .complete_detector_roster import FIVE, FOUR
from .full_v5_check import _sha

SCREEN = complete_timing.SCREEN
REPORT = SCREEN / "receiver-choice/prefix-evidence"
WORK = Path("/var/tmp/leo-prefix-evidence-20261119")
OFFICIAL = complete_timing.roster.REPORT
BRANCHES = {"stock": FOUR, "fifth": FIVE}
FRESH = ("DS26-0144", "DS29-0491")


def identity(document):
    return (
        document["schema_version"],
        document["clock_anchor"],
        document["delivery_clocks"],
        document["last_sample_counter"],
        {
            k: v
            for k, v in document["source"].items()
            if k not in ("probes", "analysis_manifest_sha256")
        },
        {k: v for k, v in document["provenance"].items() if k not in ("detector_sha256", "run_id")},
    )


def meta(row):
    return {k: v for k, v in row.items() if k != "candidates"}


def paired_support(stock, fifth):
    if identity(stock) != identity(fifth):
        raise ValueError("Four- and five-region waveforms do not share their complete identity")
    left, right = (d["source"]["probes"] for d in (stock, fifth))
    if len(left) != len(right) or any(meta(a) != meta(b) for a, b in zip(left, right, strict=True)):
        raise ValueError("Physical probe coordinates or ordering changed")


def available(document, rate, dwell, cutoff):
    return [p for p in document["source"]["probes"] if prefix.counter(p, rate) + dwell <= cutoff]


def score_prefix(stock, fifth):
    paired_support(stock, fifth)
    rate, dwell, anchor, cutoff = prefix.geometry(stock)
    a, b = [available(d, rate, dwell, cutoff) for d in (stock, fifth)]
    walls, cpus, choice = [], [], None
    for _ in range(3):
        wall, cpu = perf_counter_ns(), process_time_ns()
        tested = prefix.decide(a, b, rate, dwell, anchor, cutoff)
        cpus.append(process_time_ns() - cpu)
        walls.append(perf_counter_ns() - wall)
        if choice is not None and choice != tested:
            raise ValueError("Prefix choice changed on identical completed visits")
        choice = tested
    choice.update(
        rate=rate,
        dwell=dwell,
        anchor=anchor,
        cutoff=cutoff,
        last_evidence_counter=max((prefix.counter(p, rate) for p in a), default=None),
        warmup_probes=len(a),
        warmup_visits=len({p["visit_index"] for p in a}),
        cpu_ns=cpus,
        wall_ns=walls,
    )
    return choice


def materialize(stock, fifth, choice, sources):
    paired_support(stock, fifth)
    rate, _, anchor, cutoff = prefix.geometry(stock)
    if choice["anchor"] != anchor or choice["cutoff"] != cutoff:
        raise ValueError("Mixed output does not share the measured waveform prefix")
    before, after = (d["source"]["probes"] for d in (stock, fifth))
    flags = [choice["chosen"] == "fifth" and prefix.counter(a, rate) >= cutoff for a in before]
    chosen = [b if flag else a for a, b, flag in zip(before, after, flags, strict=True)]
    counts = dict(
        stock_probes=len(chosen) - sum(flags),
        fifth_probes=sum(flags),
        changed_probes=sum(a != b for a, b in zip(before, chosen, strict=True)),
        fifth_visits=len({p["visit_index"] for p, flag in zip(chosen, flags, strict=True) if flag}),
    )
    if not any(flags):
        return stock, counts
    parent_digests = {key: value["sha256"] for key, value in sources.items()}
    lineage = whole_iq.recording.digest([prefix.METHOD, cutoff, parent_digests, chosen])
    provenance = dict(
        stock["provenance"],
        run_id="prefix-evidence-" + lineage[7:29],
        scope="Complete saved-IQ factors with four-region warmup and fifth thereafter",
    )
    provenance.pop("detector_sha256")
    return dict(
        stock,
        provenance=provenance,
        source=dict(stock["source"], probes=chosen, analysis_manifest_sha256=lineage),
    ), counts


def native(path, expected):
    with path.open("rb") as stream:
        data = gzip.decompress(stream.read()) if path.suffix == ".gz" else stream.read()
    digest = sha256(data).hexdigest()
    if digest != expected.removeprefix("sha256:"):
        raise ValueError(f"Measured native factor bytes changed: {path}")
    return json.loads(data)


def old_parents():
    bindings = whole_iq.read(OFFICIAL / "inputs.json")
    folder = complete_timing.REPORT
    key = str((folder / "prediction-lock.json").relative_to(SCREEN))
    seal = whole_iq.read(whole_iq.checked(folder / "prediction-lock.json", bindings[key]))
    registered = whole_iq.read(OFFICIAL / "roster.json")
    if registered != complete_timing.roster.frozen_roster():
        raise ValueError("Official decision roster changed")
    path = whole_iq.checked(folder / "resources.csv", seal["files"]["resources.csv"])
    with path.open() as f:
        data = {(r["id"], r["method"]): r for r in csv.DictReader(f)}
    ordered = registered["all"]
    if len(ordered) != 20 or set(data) != {(c, m) for c in ordered for m in BRANCHES.values()}:
        raise ValueError("Exact official twenty waveform pairs are required")
    return ordered, data, bindings[key]


def native_path(entry):
    folder = SCREEN / entry["source"]
    ident, method = entry["id"], entry["method"]
    if folder == complete_timing.CROSS:
        if method == FIVE:
            return folder / "native" / f"{ident}.json.gz"
        receipt = whole_iq.read(folder / "historical-authority.json")
        old = receipt["native"][f"{ident}/control"]
        if old["native_sha256"] != entry["native_sha256"]:
            raise ValueError("Crossover used another historical stock factor source")
        return Path(old["archive"])
    role = "control" if method == FOUR else "candidate"
    path = folder / "native" / role / f"{ident}.json.gz"
    if path.is_file():
        return path
    if method == FOUR:
        return complete_timing.roster.TEN / "native/stock" / f"{ident}.json.gz"
    raise FileNotFoundError(path)


def old_case(ident, rows):
    entries = {key: rows[ident, method] for key, method in BRANCHES.items()}
    sources = {
        key: dict(path=str(native_path(r)), sha256=r["native_sha256"]) for key, r in entries.items()
    }
    docs = {k: native(Path(r["path"]), r["sha256"]) for k, r in sources.items()}
    for branch, r in entries.items():
        d = docs[branch]
        if (
            d["source"]["input_manifest_sha256"] != r["clock_authority"]
            or d["source"]["raw_recording_authority_digest"] != r["raw_authority"]
            or d["provenance"]["detector_sha256"] != "sha256:" + r["detector_sha256"]
        ):
            raise ValueError("Old recording or active detector identity changed")
    return docs, sources


def source_hashes():
    files = (
        Path(__file__),
        Path(prefix.__file__),
        Path(coherent_peak_filter.__file__),
        REPORT / "PROTOCOL.md",
        OFFICIAL / "roster.json",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in files}


def freeze(work):
    ids, entries, parent = old_parents()
    work.mkdir(exist_ok=False)
    bind = dict(files=source_hashes(), complete_timing_sha256=parent, cases=ids, fresh=FRESH)
    save_json(REPORT / "source-lock.json", bind)
    save_json(work / "source-lock.json", dict(receipt_sha256=_sha(REPORT / "source-lock.json")))
    choices = {}
    for ident in ids:
        docs, paths = old_case(ident, entries)
        choice = score_prefix(docs["stock"], docs["fifth"])
        choices[ident] = dict(choice, sources=paths)
        print(ident, choice["chosen"], choice["net"], choice["net_by_half"], flush=True)
    chosen = next((i for i in ids if choices[i]["chosen"] == "fifth"), ids[0])
    save_json(
        REPORT / "choices.json",
        dict(
            cases=choices,
            actual_old_case=chosen,
            source_lock_sha256=_sha(REPORT / "source-lock.json"),
        ),
    )
    save_json(work / "choices-lock.json", dict(choices_sha256=_sha(REPORT / "choices.json")))


def verified(work):
    pin = whole_iq.read(work / "source-lock.json")["receipt_sha256"]
    source = whole_iq.read(whole_iq.checked(REPORT / "source-lock.json", pin))
    if source["files"] != source_hashes():
        raise ValueError("Prefix rule changed after the decision seal")
    expected = whole_iq.read(work / "choices-lock.json")["choices_sha256"]
    choices = whole_iq.read(whole_iq.checked(REPORT / "choices.json", expected))
    if choices["source_lock_sha256"] != pin:
        raise ValueError("Choice seal and protocol seal differ")
    return source, choices


def fresh_case(ident):
    folder = receiver_choice_panel.REPORT
    plan = whole_iq.read(folder / "source-lock.json")
    seal = whole_iq.read(folder / "raw-prediction-lock.json")
    whole_iq.checked(folder / "source-lock.json", seal["files"]["source-lock.json"])
    trust = whole_iq.read(
        whole_iq.checked(folder / "raw-authority.json", seal["files"]["raw-authority.json"])
    )[ident]
    sources = {}
    for name, role in (("stock", "control"), ("fifth", "candidate")):
        rel = f"native/{role}/{ident}.json.gz"
        sources[name] = dict(
            path=str(whole_iq.checked(folder / rel, seal["files"][rel])),
            sha256=trust[role]["native_sha256"],
        )
        if not trust[role]["complete"]:
            raise ValueError("Fresh replay lacks verified complete admitted waveform")
    docs = {k: native(Path(row["path"]), row["sha256"]) for k, row in sources.items()}
    for d in docs.values():
        if d["source"]["input_manifest_sha256"] != plan["cases"][ident]["clock_authority"]:
            raise ValueError("Fresh plan bound another recording")
    return docs, sources, plan


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=WORK)
    freeze(p.parse_args().work)
