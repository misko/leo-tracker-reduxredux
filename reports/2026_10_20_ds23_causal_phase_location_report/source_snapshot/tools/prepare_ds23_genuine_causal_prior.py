"""Read-only causal archive repair: reject sub-second epoch round-trip duplicates."""

import hashlib
import json
from pathlib import Path

from sgp4.exporter import export_tle

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
OUTPUT = ROOT / "reports/2026_10_18_ds23_adaptive_failures/genuine_prior_inputs"


def earlier_epoch(epoch, latest):
    # Millisecond round-trip differences are not independent orbital updates.
    return latest - epoch >= 1_000_000_000


def run(case):
    source = SOURCE / case
    receipt = json.loads((source / "receipt.json").read_text())
    elements = json.loads((source / "nominal_elements.json").read_text())
    cutoff = receipt["cutoff_utc_ns"]
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = [s for s in reader.list_snapshots("space-track")
                 if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff]
    unique = {}
    for s in snapshots:
        if s.sha256 not in unique or s.collected_utc_ns > unique[s.sha256].collected_utc_ns:
            unique[s.sha256] = s
    previous, rejected = {}, set()
    for s in unique.values():
        cat = parse_element_sets(reader.read(s))
        for name, n, satellite, epoch in zip(cat.names, cat.satellite_numbers, cat.satellites,
                                             cat.element_epoch_utc_ns(), strict=True):
            if str(n) not in elements or epoch > cutoff:
                continue
            latest = elements[str(n)]["provenance"]["element_epoch_utc_ns"]
            if not earlier_epoch(epoch, latest):
                if epoch < latest:
                    rejected.add(n)
                continue
            key = int(epoch), s.collected_utc_ns
            if n not in previous or key > previous[n][0]:
                previous[n] = key, name, satellite, s
    text, provenance = "", {}
    for n, (key, name, satellite, s) in sorted(previous.items()):
        lines = export_tle(satellite)
        text += f"0 {name}\n{lines[0]}\n{lines[1]}\n"
        provenance[str(n)] = dict(epoch_utc_ns=key[0], collected_utc_ns=key[1],
                                  snapshot_digest=s.digest)
    d = OUTPUT / case
    d.mkdir(parents=True, exist_ok=True)
    (d / "previous.tle").write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (d / "previous_receipt.json").write_text(json.dumps(dict(sources=provenance,
        catalogue_sha256=digest, minimum_epoch_separation_s=1.,
        rejected_near_duplicate_norads=sorted(rejected)), indent=2) + "\n")
    receipt.update(previous_tle_sha256=digest, previous_count=len(previous),
                   previous_prior_repair="reject epoch differences under one second")
    (d / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(case, "genuine previous", len(previous), "near-duplicate identities", len(rejected),
          flush=True)


if __name__ == "__main__":
    for case in ("DS23-0342", "DS23-0039"):
        run(case)
