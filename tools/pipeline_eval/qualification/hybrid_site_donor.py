"""Read sealed real IQ as the established read-only recording service account."""

import json
import sys
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.storage.short_window import ShortWindowReader

from .raw_stream_reader import streamed_windows


def eligible(row, target):
    acq = row.acquisition
    return (
        row.sample_count == 200_000
        and row.receiver_count == 2
        and acq.get("complete") is True
        and acq.get("sample_end", 0) - acq.get("sample_start", 0) == row.sample_count
        and acq.get("validity_authority") == "provider_attested"
        and acq.get("validity_includes_guard") is True
        and acq["actual_if_center_hz"] + target["lnb_lo_hz"] == target["rf_center_hz"]
    )


def rank(salt, case, item):
    sequence, digest = item[1].sequence, item[1].iq_sha256
    return sha256(f"{salt}:{case}:{item[0]}:{sequence}:{digest}".encode()).digest()


def read_plan(plan):
    bucket = defaultdict(list)
    readers = []
    geometry = {row["channel"]: (row["edge"], row["rf_hz"]) for row in plan["visits"]}
    for segment, leaf in enumerate(plan["segments"]):
        path = Path(leaf["path"])
        root = Path("/srv/bulk/leo/fast-scan-recordings")
        if path.name != "manifest.json" or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("donor source must be in the frozen read-only raw inventory")
        reader = ShortWindowReader(path.parent)
        if (
            reader.manifest_sha256 != "sha256:" + leaf["sha256"]
            or reader.manifest.schema_version != 2
            or reader.manifest.sample_rate_hz != 10_000_000
            or reader.manifest.receiver_ids != (0, 1)
        ):
            raise ValueError("donor manifest or native dual-RX geometry changed")
        readers.append(reader)
        targets = {x["target_id"]: x for x in reader.manifest.configuration["targets"]}
        for chunk in reader.manifest.chunks:
            index = reader._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
            for j, line in enumerate(index.splitlines()):
                row = ShortWindowIndexV2.model_validate_json(line)
                target = targets[row.target_id]
                ch = target["channel"]
                if row.sequence != chunk.first_sequence + j:
                    raise ValueError("donor index sequencing differs from sealed manifest")
                if geometry.get(ch) == (target["edge"], target["rf_center_hz"]) and eligible(
                    row, target
                ):
                    bucket[ch].append((segment, row, target))
    chosen = {}
    available = {c: len(rows) for c, rows in sorted(bucket.items())}
    for ch in sorted(geometry):
        visits = [row["visit"] for row in plan["visits"] if row["channel"] == ch]
        ranked = sorted(bucket[ch], key=lambda item: rank(plan["salt"], plan["case"], item))
        if len(ranked) < len(visits):
            raise ValueError(f"donor channel {ch} has {len(ranked)} eligible unique visits")
        for visit, (segment, row, target) in zip(visits, ranked[: len(visits)], strict=True):
            chosen[segment, row.sequence] = dict(
                visit=visit,
                donor=plan["case"],
                segment=segment,
                manifest_sha256=plan["segments"][segment]["sha256"],
                iq_sha256=row.iq_sha256.removeprefix("sha256:"),
                donor_global_visit=row.acquisition["global_visit"],
                donor_sample_start=row.acquisition["sample_start"],
                donor_flags=row.acquisition.get("quality_flags", []),
                donor_rf_hz=target["rf_center_hz"],
                edge=target["edge"],
                nbytes=row.payload_bytes,
            )
    return readers, chosen, available


def main():
    plan = json.load(sys.stdin)
    readers, chosen, available = read_plan(plan)
    stats = Counter()
    out = sys.stdout.buffer
    for segment, reader in enumerate(readers):
        for w in streamed_windows(reader, stats):
            if (receipt := chosen.get((segment, w.index.sequence))) is None:
                continue
            out.write(json.dumps(receipt, separators=(",", ":")).encode() + b"\n")
            out.write(w.samples.tobytes())
            out.flush()
    out.write(
        json.dumps(dict(terminal=True, available=available, extraction_stats=stats)).encode()
        + b"\n"
    )
    out.flush()


if __name__ == "__main__":
    main()
