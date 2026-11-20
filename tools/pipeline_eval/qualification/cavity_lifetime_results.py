"""Verify sealed kernel, capture and numerical parity for cavity lifetime replays."""

import gzip
import json
import re
from collections import defaultdict

from .. import corpus
from ..__main__ import save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import bounded_cavity_trial as base
from . import cavity_lifetime_trial as trial
from . import row_memory_replay as row
from .full_receiver_comparison import read, sha
from .portable_gate_trials import compressed_rows

OUT = trial.OUT
MIB = 1024**2
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "resolved_request_sha256")


def verify(directory, seal_name, filename):
    seal = read(directory / seal_name)
    for name, digest in seal["files"].items():
        if sha(directory / name) != digest:
            raise ValueError(f"changed output {name}")
    records = list(
        map(json.loads, gzip.decompress((directory / filename).read_bytes()).splitlines())
    )
    assert len(records) == len(seal["cases"]) and {r["id"] for r in records} == set(seal["cases"])
    return {r["id"]: r for r in records}


def statistics(record, external):
    samples = record.get("samples", [])
    if not samples:
        return {}
    checkpoints = [r for r in samples if r["stage"] != "periodic"]
    derived = []
    for stage in ("signed_context", "signed_context_exit", "cavity_policy"):
        by_event = {r["event"]: r for r in checkpoints if r["stage"] == stage}
        for before, after in (
            ("before_direct_release", "after_direct_release"),
            ("before_gc", "after_gc"),
            ("after_gc", "after_trim"),
        ):
            if before not in by_event or after not in by_event:
                continue
            first, last = by_event[before], by_event[after]
            derived.append(
                dict(
                    stage=stage,
                    transition=after,
                    anon_delta_mib=(last["anon_bytes"] - first["anon_bytes"]) / MIB,
                    total_delta_mib=(last["memory_bytes"] - first["memory_bytes"]) / MIB,
                    collected=last.get("collected"),
                    trim_returned=last.get("trim_returned"),
                )
            )
    assert not any(r["swap_bytes"] for r in samples)
    service = "\n".join(record.get("systemd") or [])
    peak = re.search(r"Memory peak: ([\d.]+)M \(swap: 0B\)", service)
    cpu = re.search(r"CPU time consumed: (?:(\d+)min )?([\d.]+)s", service)
    return dict(
        observed_peak_mib=max(r["peak_bytes"] for r in samples) / MIB,
        terminal_peak_mib=float(peak[1]) if peak else None,
        terminal_cpu_s=(60 * int(cpu[1] or 0) + float(cpu[2])) if cpu else None,
        max_sampled_anon_mib=max(
            [r["anon_bytes"] for r in samples if "anon_bytes" in r]
            + [r["stat"]["anon"] for r in external],
            default=0,
        )
        / MIB,
        max_sampled_file_mib=max(
            [r["file_bytes"] for r in samples if "file_bytes" in r]
            + [r["stat"]["file"] for r in external],
            default=0,
        )
        / MIB,
        sampled_cpu_s=max(r["cpu_s"] for r in samples),
        memory_release=derived,
        stages=[r for r in checkpoints if r["stage"] != "family_data"],
    )


def main():
    controls, all_stock = row.controls()
    compact = all_stock[row.baseline.COMPACT]
    original = all_stock[row.baseline.ORIGINAL]
    bounded = verify(base.REPORT, "prediction-lock.json", "capped.jsonl.gz")
    external = defaultdict(list)
    for line in gzip.decompress((base.REPORT / "memory-stat.jsonl.gz").read_bytes()).splitlines():
        reading = json.loads(line)
        external[reading["id"]].append(reading)
    direct = verify(OUT, "direct-lock.json", "direct.jsonl.gz")
    trim = (
        verify(OUT, "gc-trim-lock.json", "gc-trim.jsonl.gz")
        if (OUT / "gc-trim-lock.json").exists()
        else {}
    )
    assert bounded.keys() == direct.keys() == compact.keys() == original.keys()
    sites = {r["id"]: r["truth"] for r in corpus.references("roof16")}
    sites.update((r["id"], r["truth"]) for r in corpus.references("ds26-all159"))
    reports, geography, positions, diagnostic = [], [], [], []
    for ident in controls["cases"]:
        paired = [compact[ident], bounded[ident], direct[ident]]
        if ident in trim:
            paired.append(trim[ident])
        for entry in paired:
            assert all(entry[k] == controls["bindings"][ident][k] for k in MATCH)
            result = entry["result"]
            reports.append(
                dict(
                    id=ident,
                    method=entry["method"],
                    status=result["status"],
                    reason=result.get("reason"),
                    terminal=entry.get("terminal"),
                    systemd=entry.get("systemd"),
                    worker_wall_s=entry.get("worker_wall_s"),
                    **statistics(entry, external[ident] if entry is bounded[ident] else []),
                )
            )
            display = {k: v for k, v in entry.items() if k != "samples"}
            if entry is not trim.get(ident):
                positions.append(display)
            if ident in trim:
                diagnostic.append(display)
            for arm in ARMS:
                arms = result["arms"]
                this = arms[arm]
                stock = compact[ident]["result"]["arms"][arm]
                published = this["latlon"] is not None
                geography.append(
                    dict(
                        id=ident,
                        method=entry["method"],
                        arm=arm,
                        published=published,
                        position_km=distance_km(this["latlon"], sites[ident]),
                        delta_vs_unrestricted_km=distance_km(this["latlon"], stock["latlon"]),
                        exact_arm=dict(this) == dict(stock) if published else None,
                        rf_rms_hz=this.get("rf_rms_hz"),
                        rf_rms_delta_hz=(
                            this["rf_rms_hz"] - stock["rf_rms_hz"]
                            if published and this.get("rf_rms_hz") is not None
                            else None
                        ),
                    )
                )
    summaries = {}
    for method in dict.fromkeys(r["method"] for r in geography):
        for arm in ARMS:
            rows = [r for r in geography if (r["method"], r["arm"]) == (method, arm)]
            summaries[f"{method}/{arm}"] = dict(
                scheduled=len(rows),
                published=sum(r["published"] for r in rows),
                **{
                    k: distribution(r[k] for r in rows)
                    for k in (
                        "position_km",
                        "delta_vs_unrestricted_km",
                        "rf_rms_hz",
                        "rf_rms_delta_hz",
                    )
                },
            )
    score = OUT / "scores.json"
    save_json(score, dict(resources=reports, geography=geography, statistics=summaries))
    output = OUT / "positions.jsonl.gz"
    write(output, compressed_rows(positions))
    figures = [output, score, OUT / "plan.json", OUT / "direct-lock.json"]
    save_json(
        OUT / "figure-lock.json",
        dict(cases=controls["cases"], files={p.name: sha(p) for p in figures}),
    )
    if trim:
        output = OUT / "allocator-diagnostic.jsonl.gz"
        write(output, compressed_rows(diagnostic))
        figures = [output, score, OUT / "plan.json", OUT / "gc-trim-lock.json"]
        save_json(
            OUT / "allocator-figure-lock.json",
            dict(cases=list(trim), files={p.name: sha(p) for p in figures}),
        )


if __name__ == "__main__":
    main()
