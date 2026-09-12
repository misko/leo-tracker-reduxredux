"""Bounded offline additions to the frozen five-dwell GLRT/PSS comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
from compare_paired_pss_bandwidth import write

from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.full_capture_glrt20ms import _acquisition_config, _analyze_window
from leo.analysis.standard.native_pss import starlink_pss_channel_reference_hz
from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.analysis.starlink.pss_search import compile_pss_projection, project_pss_block
from leo.contracts.states import StarlinkEdge
from leo.storage import RecordingStore


def freeze_tles(selection: list[dict], out: Path) -> None:
    # The privileged child only uses the archive's read-only public port. All
    # output files are written by the ordinary user outside the archive.
    script = """
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from leo.operations.tle_archive import TleArchiveReader
r=TleArchiveReader(Path('/var/lib/leo/tle'))
result=[]
for t in json.loads(sys.argv[2]):
 s=r.select_latest_before(t, provider='space-track')
 result.append(dict(collected_utc_ns=s.collected_utc_ns,sha256=s.sha256,
                    source_path=str(s.path),text=r.read(s)))
print(json.dumps(result))
"""
    starts = [
        c["native"]["binding"]["timing"]["first_estimate_utc_ns"] + round(c["native_start_s"] * 1e9)
        for c in selection
    ]
    result = subprocess.run(
        [
            "sudo",
            "-n",
            sys.executable,
            "-c",
            script,
            str(Path(__file__).resolve().parents[1] / "src"),
            json.dumps(starts),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    records = json.loads(result.stdout)
    refs = []
    for c, t, r in zip(selection, starts, records, strict=True):
        raw = r.pop("text").encode()
        assert hashlib.sha256(raw).hexdigest() == r["sha256"]
        filename = Path(r["source_path"]).name
        (out / filename).write_bytes(raw)
        refs.append(
            dict(
                capture_id=c["capture_id"],
                measurement_start_utc_ns=t,
                snapshot_filename=filename,
                **r,
            )
        )
    write(out / "tle-snapshots.json", refs)


def replay(
    selection: list[dict], source: Path, out: Path, root: Path, *, fractional: bool = False
) -> None:
    config = production_receiver_standard_config(sample_rate_hz=2_500_000)
    acquisition = _acquisition_config(50_000, config.feedback)
    store = RecordingStore.open_read_only(root)
    try:
        for c in selection:
            dest = out / c["capture_id"]
            dest.mkdir(exist_ok=True)
            bundle = store.inspect(c["capture_id"])
            if (
                "sha256:" + bundle.manifest_sha256.removeprefix("sha256:")
                != c["native"]["manifest_digest"]
            ):
                raise ValueError("manifest changed")
            b, narrow = c["native"]["binding"], c["recorded"]["binding"]
            reader = store.reader(bundle, b["stream_id"], verify=True)
            projection = compile_pss_projection(
                input_sample_rate_hz=b["sample_rate_hz"],
                input_center_frequency_hz=b["tuned_center_frequency_hz"],
                rf_bandwidth_hz=b["rf_bandwidth_hz"],
                target_center_frequency_hz=narrow["tuned_center_frequency_hz"],
                channel_reference_hz=starlink_pss_channel_reference_hz(
                    b["starlink_channel"], b["starlink_edge"]
                ),
                canonical_output_sample_rate_hz=2_500_000,
            )
            geometry = compile_pilot_search_geometry(
                receiver_id=b["receiver_id"],
                starlink_channel=b["starlink_channel"],
                edge=b["starlink_edge"],
                tuned_center_frequency_hz=narrow["tuned_center_frequency_hz"],
                sample_rate_hz=2_500_000,
                rf_bandwidth_hz=2_500_000,
                residual_cfo_min_hz=config.feedback.cfo_search_min_hz,
                residual_cfo_max_hz=config.feedback.cfo_search_max_hz,
            )
            for block_index in range(9):
                path = dest / f"derived-glrt-{block_index:02}.json"
                if path.exists():
                    cached = json.loads(path.read_text())
                    evaluated = any(
                        w["fractional_epoch_status"] != "not_evaluated"
                        for w in cached["windows"]
                    )
                    if evaluated != fractional:
                        raise ValueError("cached refinement policy differs; use a fresh output")
                    continue
                start = round((c["native_start_s"] + block_index * 0.25) * 25_000_000)
                span = reader.read_device_span(start, 6_250_000, receiver_ids=(b["receiver_id"],))
                segments = np.unique(span.continuity_segment_ids)
                if not span.valid_samples.all() or len(segments) != 1 or segments[0] < 0:
                    raise ValueError("gap in selected span")
                digest = hashlib.sha256(span.samples.tobytes()).hexdigest()
                prior = json.loads(
                    (source / c["capture_id"] / f"derived2p5-{block_index:02}.json").read_text()
                )
                if digest != prior["selected_iq_sha256"]:
                    raise ValueError("GLRT and PSS input hashes differ")
                iq = span.samples[:, 0, 0].astype(np.float32) + 1j * span.samples[:, 0, 1].astype(
                    np.float32
                )
                block = project_pss_block(
                    iq,
                    projection,
                    input_device_sample_start=start,
                    continuity_segment_index=int(segments[0]),
                )
                starts = list(range(0, len(block.samples) - 50_000 + 1, 25_000))

                def analyze(pair, block=block, binding=b, geometry=geometry):
                    i, s = pair
                    # Research adapter uses the same pure window kernel as the
                    # persisted products, retaining float projected IQ.
                    return asdict(
                        _analyze_window(
                            i,
                            s,
                            np.asarray(block.samples[s : s + 50_000], dtype=np.complex128) / 32768,
                            sample_rate_hz=2_500_000,
                            edge=StarlinkEdge(binding["starlink_edge"]),
                            acquisition_config=acquisition,
                            glrt_size=config.feedback.glrt_size,
                            margin_gate=config.full_capture_glrt20ms.margin_gate,
                            frequency_reference=geometry.frequency_reference,
                            refine_fractional_epoch=fractional,
                        )
                    )

                with ThreadPoolExecutor(max_workers=4) as pool:
                    rows = list(pool.map(analyze, enumerate(starts)))
                write(
                    path,
                    dict(
                        input_iq_sha256=digest,
                        projection=asdict(projection),
                        output_device_sample_start=block.output_device_sample_start,
                        windows=rows,
                    ),
                )
                print(
                    f"{c['capture_id'][-6:]} derived GLRT {block_index + 1}/9: "
                    f"{sum(w['passed_margin_gate'] for w in rows)}/{len(rows)} passing",
                    flush=True,
                )
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "replay"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fractional", action="store_true")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    args.output.mkdir(exist_ok=True)
    selection = json.loads((args.source / "selection.json").read_text())["selected"]
    if args.action == "freeze":
        freeze_tles(selection, args.output)
    else:
        replay(
            selection, args.source, args.output, Path("/srv/bulk/leo"), fractional=args.fractional
        )


if __name__ == "__main__":
    main()
