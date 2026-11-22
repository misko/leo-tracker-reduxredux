"""Time one archived portable solve with the system allocator and stock jemalloc."""

import argparse
import os
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification.paired_publication import archive_identity

from . import covariance_transfer_trial as transfer
from .complete_family_cavity_trial import verify_archive
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import KEYS, MEASUREMENTS, evidence_digests, write
from .solver_fused_phase_trial import RELEASE

ALLOCATOR = Path("/usr/lib/x86_64-linux-gnu/libjemalloc.so.2")


def run(bench, output):
    parent = bench / "integration-restored-scout-graph"
    spec = read(MEASUREMENTS / "restored-scout-graph-freeze.json")["specification"]
    require_spec(parent, spec)
    site = bench / "portable-v5-geodiverse" / transfer.INDIA
    native, offer, archive = site / "native.json", site / "matched-tile.json", site / "tle"
    baseline = read(MEASUREMENTS / "screened-stock-recovery-containing.json")
    row = next(r for r in baseline["rows"] if r["case"] == transfer.INDIA)
    if digest(native) != row["document_sha256"] or read(offer) != row["offer"]:
        raise ValueError("Unexpected detector input or region")
    verify_archive(vars(transfer), row, site)
    allocator_sha = digest(ALLOCATOR)
    if allocator_sha != "88abf640d394354438475ed5978616475fb28d95390f347ecfcee6ddf3beffc8":
        raise ValueError("Unexpected allocator build")
    output.mkdir()
    rows = []
    reference = None
    for index, mode in enumerate(("system", "jemalloc", "jemalloc", "system")):
        env = dict(os.environ, PYTHONPATH=f"{parent}:{RELEASE / 'src'}:{RELEASE}",
                   OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        for key in ("LD_PRELOAD", "MALLOC_CONF", "PYTHONMALLOC"):
            env.pop(key, None)
        if mode == "jemalloc":
            env["LD_PRELOAD"] = str(ALLOCATOR)
        terminal = output / f"run-{index}.json"
        rss = output / f"rss-{index}.txt"
        subprocess.run(["/usr/bin/time", "-f", "%M", "-o", str(rss),
                        str(RELEASE / "venv/bin/python"), "-BPs",
                        str(Path(__file__).with_name("guarded_solver_profile.py")), str(native),
                        str(parent / "spec.json"), str(archive), str(offer), str(terminal)],
                       env=env, timeout=90, check=True)
        result = read(terminal)
        science = {key: result[key] for key in KEYS} | {"evidence": evidence_digests(result)}
        if reference is None:
            reference = science
        elif science != reference:
            raise ValueError("Changed solver outputs with alternate allocation")
        rows.append(dict(mode=mode, cpu_s=result["solver_cpu_s"], elapsed_s=result["solver_wall_s"],
                         peak_process_rss_kib=int(rss.read_text())))
    verify_archive(vars(transfer), row, site)
    return dict(specification=spec, archive=archive_identity(archive), native_sha256=digest(native),
                offer=row["offer"], allocator_sha256=allocator_sha, science=reference, runs=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bench", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    write(args.output / "result.json", run(args.bench, args.output))
