"""Time complete public TLE parses and compare all propagated states outside the timer."""

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from leo.sky import propagation
from leo.sky.sampling import SamplingGrid

from ..__main__ import encoded, local_output, save_json
from .catalogue_checksum import scalar_checksum
from .full_v5_check import BULK, PRODUCERS, _load_case, _sha


def states(catalogue, utc_ns):
    span = 30_000_000_000
    grid = SamplingGrid((utc_ns - span, utc_ns, utc_ns + span), 1, 30.0)
    orbit = propagation.propagate_grid(catalogue, grid)
    digest = hashlib.sha256(encoded([catalogue.names, catalogue.satellite_numbers, grid.utc_ns]))
    for array in (orbit.error_code, orbit.position_teme_km, orbit.velocity_teme_km_s):
        digest.update(array.tobytes())
    return dict(objects=len(catalogue), states=orbit.error_code.size, sha256=digest.hexdigest())


def compare(text, utc_ns, repeats=6):
    versions = (("Scalar", scalar_checksum), ("Public parser", propagation.element_line_checksum))
    rows, expected = [], None
    for repeat in range(repeats):
        for method, checksum in versions if repeat % 2 == 0 else reversed(versions):
            with patch.object(propagation, "element_line_checksum", checksum):
                wall, cpu = perf_counter(), process_time()
                catalogue = propagation.parse_element_sets(text)
                cpu_ms = (process_time() - cpu) * 1000
                wall_ms = (perf_counter() - wall) * 1000
            observed = states(catalogue, utc_ns)
            if expected is not None and observed != expected:
                raise ValueError("parsed identities or propagated states changed")
            expected = observed
            rows.append(dict(method=method, pair=repeat + 1, cpu_ms=cpu_ms, wall_ms=wall_ms))
            del catalogue
    return rows, expected


def plot(out, rows):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), sharey=True, layout="constrained")
    for ax, metric, title in zip(axes, ("cpu_ms", "wall_ms"), ("CPU", "Elapsed"), strict=True):
        for i, case in enumerate(PRODUCERS):
            data = [row for row in rows if row["case"] == case]
            for repeat in sorted({r["pair"] for r in data}):
                pair = {r["method"]: r[metric] for r in data if r["pair"] == repeat}
                ax.plot(
                    (i - 0.13, i + 0.13),
                    (pair["Scalar"], pair["Public parser"]),
                    color="#b9bec4",
                    linewidth=1,
                    zorder=1,
                )
            for shift, name, color in (
                (-0.13, "Scalar", "#4c5875"),
                (0.13, "Public parser", "#007961"),
            ):
                values = [r[metric] for r in data if r["method"] == name]
                ax.scatter(
                    [i + shift] * len(values),
                    values,
                    color=color,
                    s=20,
                    label=name if i == 0 else None,
                    zorder=2,
                )
        ax.set(
            title=title,
            xticks=list(range(len(PRODUCERS))),
            xticklabels=list(PRODUCERS),
            ylim=(0, None),
            xmargin=0.25,
        )
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Complete catalogue parse (ms)")
    axes[1].legend(frameon=False, loc="lower left")
    fig.suptitle("Parsing the same causal catalogues with two checksum implementations")
    fig.savefig(out / "stage.png", dpi=160)
    fig.savefig(out / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, required=True)
    out = parser.parse_args().out
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 1:
        parser.error("pin this benchmark to one available CPU")
    out.mkdir(parents=True, exist_ok=False)
    rows, cases = [], {}
    for ident in PRODUCERS:
        case = _load_case(ident)
        path = BULK / case["catalog"]["path"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (
            digest != case["catalog"]["sha256"]
            or case["catalog_timestamp_ns"] > case["cutoff_utc_ns"]
        ):
            raise ValueError(f"catalogue source or cutoff changed for {ident}")
        times, result = compare(raw.decode("utf-8"), case["cutoff_utc_ns"])
        rows.extend(dict(case=ident, **row) for row in times)
        cases[ident] = dict(catalogue_sha256=digest, cutoff_utc_ns=case["cutoff_utc_ns"], **result)
    with (out / "stage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    save_json(
        out / "evidence.json",
        dict(
            cases=cases,
            cpu=cpus[0],
            python=sys.version,
            production_source_sha256=_sha(Path(propagation.__file__)),
            script_sha256=_sha(Path(__file__)),
            scalar_source_sha256=_sha(Path(sys.modules[scalar_checksum.__module__].__file__)),
        ),
    )
    plot(out, rows)
    save_json(
        out / "stage-figure-lock.json",
        dict(
            files={
                name: _sha(out / name)
                for name in ("evidence.json", "stage.csv", "stage.png", "stage.pdf")
            }
        ),
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="public-catalogue-checksum",
            title="Complete causal catalogue parsing",
            sample="Two catalogues, six interleaved pairs each",
            boundary="Text in memory through every validated and parsed satellite",
            note="State propagation and numerical comparison ran after each parse timer stopped.",
            csv="stage.csv",
            image="stage.png",
            pdf="stage.pdf",
            seal="stage-figure-lock.json",
        ),
    )


if __name__ == "__main__":
    main()
