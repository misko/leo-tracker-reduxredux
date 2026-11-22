"""Measure causal winner selection on pre-parsed, digest-checked archive snapshots."""

import argparse
import json
import runpy
from hashlib import sha256
from pathlib import Path
from time import process_time
from types import SimpleNamespace

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.contracts.digests import canonical_digest
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
from .selected_changes import bound_native


RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
BASE = RELEASE / "src/leo/operations/causal_tle_catalogue.py"


def trial(pair_path):
    if sha256(BASE.read_bytes()).hexdigest() != "5076a2182ba9f551f54df78ba1dee53eb223e922d7aac86088fcd4cf429dc6a8":
        raise ValueError("Expected deployed catalogue selector")
    original = runpy.run_path(str(BASE))["causal_catalogue"]
    pair = json.loads(pair_path.read_bytes())
    native = bound_native(pair_path.parent / "baseline", pair["runs"]["baseline"])
    cutoff = frequency_evidence(native)[2]["causal_cutoff_utc_ns"]
    reader = TleArchiveReader(Path(pair["archive"]["root"]))
    snapshots = [s for s in reader.list_snapshots("space-track")
                 if cutoff - 72 * 3600 * 10**9 <= s.collected_utc_ns <= cutoff]
    parser = CausalPreparationParser()
    tables = {}
    for snapshot in snapshots:
        text = reader.read(snapshot)
        if snapshot.sha256 not in tables:
            tables[snapshot.sha256] = parser(text)
    # Measure the unchanged selection policy with matching, pre-verified rows.
    saved = SimpleNamespace(list_snapshots=lambda provider: snapshots, read=lambda ref: ref.sha256)
    measurements = {}
    for hours in (48, 72):
        control = None
        clocks = {"deployed": [], "deferred": []}
        for name in ("deployed", "deferred", "deferred", "deployed", "deployed", "deferred"):
            op = original if name == "deployed" else causal_catalogue
            start = process_time()
            result = op(saved, cutoff, maximum_age_s=hours * 3600, element_parser=tables.__getitem__)
            clocks[name].append(process_time() - start)
            if control is None:
                control = result
            if (result.catalogue != control.catalogue or result.provenance != control.provenance
                    or result.snapshot_count != control.snapshot_count):
                raise ValueError("Selected satellites, orbital objects or provenance differ")
        measurements[hours] = dict(cpu_s=clocks, members=len(result.catalogue),
                                   snapshots=result.snapshot_count, provenance_sha256=canonical_digest(result.provenance))
    return dict(pair_sha256=sha256(pair_path.read_bytes()).hexdigest(), cutoff_utc_ns=cutoff,
                input_snapshot_digests=[s.digest for s in snapshots], measurements=measurements)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    print(json.dumps(trial(cli.parse_args().pair), indent=2, allow_nan=False))
