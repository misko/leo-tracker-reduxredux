"""Complete one timed-out stock publication without rerunning the sealed candidate."""

import argparse
import os
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from aperture_trial import read, write
from dense_full_short_crossover import file_sha
from dense_geographic_trial import host
from regional_probe_block_publication import RECEIPTS


def record(output, clock):
    report = read(output / RECEIPTS[0])
    return dict(
        process=clock,
        expected_evidence=report["evidence"],
        files={p: file_sha(output / p) for p in RECEIPTS},
    )


def retry(initial, output, cpu, wall):
    machine = host()
    source = initial / "source-lock.json"
    lock = read(source)
    if lock["machine"] != machine:
        raise ValueError("Retry changed the pinned host limits")
    if (initial / "prediction-lock.json").exists() or (initial / "stock" / RECEIPTS[0]).exists():
        raise ValueError("Stock already completed")
    partial, = (initial / "stock/fast-scan-automatic-work").glob("*/terminal.json")
    candidate = record(initial / "guarded", dict(cpu_s=cpu, elapsed_s=wall))
    driver = Path(__file__).with_name("regional_probe_block_publication.py")
    if file_sha(driver) != lock["files"][str(driver)]:
        raise ValueError("Original publication driver changed")
    output.mkdir()
    (output / "guarded").symlink_to(initial / "guarded", target_is_directory=True)
    (output / "source-lock.json").write_bytes(source.read_bytes())
    recovery = dict(
        machine=machine, initial=str(initial), original_stock_limit_s=100,
        original_stock_status="timed_out_before_complete_publication",
        partial_terminal_sha256=file_sha(partial),
        candidate_clock_source="Successful per-leg launcher stdout",
        candidate=candidate, retry_limit_s=150, driver_sha256=file_sha(Path(__file__)),
    )
    write(output / "recovery-lock.json", recovery)
    os.environ["MPLCONFIGDIR"] = str(initial / "fonts")
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = perf_counter()
    subprocess.run(
        [sys.executable, "-BPs", str(driver), "child", "stock",
         *lock["command"], "--output", str(output / "stock")],
        check=True, timeout=recovery["retry_limit_s"],
    )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    clocks = dict(cpu_s=after.ru_utime - before.ru_utime + after.ru_stime - before.ru_stime,
                  elapsed_s=perf_counter() - start)
    write(output / "prediction-lock.json", dict(
        source_sha256=file_sha(source),
        recovery_sha256=file_sha(output / "recovery-lock.json"),
        outputs=dict(guarded=candidate, stock=record(output / "stock", clocks)),
    ))
    print(clocks, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("initial", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("cpu", type=float)
    parser.add_argument("wall", type=float)
    retry(**vars(parser.parse_args()))
