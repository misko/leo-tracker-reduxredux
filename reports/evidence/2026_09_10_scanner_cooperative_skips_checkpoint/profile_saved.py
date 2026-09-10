"""Bounded saved-LNB native stage profiling. No radio, writes only new results."""
import ctypes as ct
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from tools.benchmark_presence_execution import differences, numerical
from tools.native_presence import ROOT, NativePresence, Result, build_dwell_presence, pointer
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_options

output = Path(__file__).parent / "results-v2"
output.mkdir()
options = fftw_options(Path("/tmp/leo-scanner-5m-profile.53WxTn/fftw"))
algorithm = json.loads((ROOT / "runtime/scanner-glrt/algorithm.json").read_text())
flags = tuple(algorithm["native_defines"]) + options["cflags"]
library = build_dwell_presence(output / "baseline.so", cflags=flags,
    ldflags=options["ldflags"], dependencies=options["dependencies"])
root = Path("/srv/bulk/leo/scanner-lnb-live-20260910.vajIwK")
rows = []
for case, rate in enumerate((2500000, 5000000)):
    source = root / f"case-{case}-{rate}-adaptive"
    identity = json.loads((source / "summary.json").read_text())
    store = AdaptiveHopIqStore(source / "bulk", read_only=True)
    try:
        publication = store.inspect(identity["session_id"])
        receipt = publication.manifest.receipt
        selected = sorted(next(e.visit_index for e in receipt.events[:receipt.complete_visit_count]
            if e.target_index == target and e.valid_start_counter - receipt.terminal.first_counter >= rate*30)
            for target in range(8))
        with ExitStack() as stack:
            dwells = {edge:stack.enter_context(NativeDwell(library, rate, edge, 512)) for edge in ("lower", "upper")}
            confirmations = {edge:stack.enter_context(NativePresence(library, rate, edge)) for edge in dwells}
            reader = stack.enter_context(store.reader(publication.session_id, expected=publication))
            for visit in selected:
                record, samples = reader.read_visit_ci16(visit)
                iq = np.ascontiguousarray(samples[:, 1, :])
                digest = hashlib.sha256(iq.tobytes()).hexdigest()
                edge = record.event.target.edge.value
                d, c = dwells[edge], confirmations[edge]
                for repetition in range(4):
                    result = d.run(iq, maximum=1, seeded=False)
                    window = int(result.rank.order[0])
                    fragment = np.ascontiguousarray(iq[window*(rate//50):(window+1)*(rate//50)])
                    confirmation = Result()
                    assert c.library.leo_presence_run_ci16(c.workspace, pointer(fragment), len(fragment), ct.byref(confirmation)) == 0
                    assert not differences(numerical(unpack(result.confirmations[0])), numerical(unpack(confirmation)))
                    assert hashlib.sha256(iq.tobytes()).hexdigest() == digest
                    if repetition == 0:
                        continue  # Predeclared warm-up, retained in methodology not timing cohort.
                    row = dict(rate_hz=rate, visit=visit, session_id=publication.session_id,
                        manifest_sha256=publication.manifest_sha256, iq_sha256=digest,
                        target=record.event.target_index, edge=edge, repetition=repetition,
                        selected_window=window, dwell=unpack(result),
                        confirmation_profile=c.profile())
                    rows.append(row)
    finally:
        store.close()
summary = {}
for rate in (2500000, 5000000):
    group = [r for r in rows if r["rate_hz"] == rate]
    components = {
        "whole_dwell": [r["dwell"]["total_cpu_ms"] for r in group],
        "ranking": [r["dwell"]["rank"]["total_cpu_ms"] for r in group],
        "rank_fold": [r["dwell"]["rank"]["fold_cpu_ms"] for r in group],
        "rank_correlation": [r["dwell"]["rank"]["correlation_cpu_ms"] for r in group],
    }
    for name in ("conversion", "coarse", "fine", "fractional", "total"):
        components[f"confirmation_{name}"] = [r["dwell"]["confirmations"][0][f"{name}_cpu_ms"] for r in group]
    for name in ("acquisition_fft", "conditioned", "verification", "epoch_lattice", "final_confirmation", "local_coarse"):
        components[name] = [r["confirmation_profile"][f"{name}_cpu_ms"] for r in group]
    components["nuisance"] = [r["dwell"]["nuisances"][0]["cpu_ms"] for r in group]
    summary[rate] = {name:dict(mean_ms=float(np.mean(v)), p99_ms=float(np.percentile(v,99)), maximum_ms=max(v)) for name,v in components.items()}
with (output / "profile.json").open("x") as handle:
    json.dump(dict(method="first saved visit at/after 30 source seconds per target; RX1; one warm-up and three measured repetitions; unchanged native flags and host FFTW; separate confirmation parity checked; desktop timing is not ARM timing", rows=rows, summary=summary),handle,indent=2)
print(json.dumps(summary,indent=2))
