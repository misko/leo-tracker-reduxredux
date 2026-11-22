"""Verify two full publications against each other from their actual local files."""

import argparse
import json
import zlib
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from struct import unpack_from

from PIL import Image

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_LAYOUT = {
    0: (1, (1, 2, 4, 8, 16)),
    2: (3, (8, 16)),
    3: (1, (1, 2, 4, 8)),
    4: (2, (8, 16)),
    6: (4, (8, 16)),
}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
         (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _scanline_bytes(header):
    width, height, depth, color, compression, filtering, interlace = unpack_from(">IIBBBBB", header)
    channels, depths = PNG_LAYOUT.get(color, (0, ()))
    if (not 0 < width < 2**31 or not 0 < height < 2**31 or depth not in depths
            or compression or filtering or interlace not in (0, 1)):
        raise ValueError("Invalid PNG header")
    bits_per_pixel = depth * channels
    total = 0
    for x, y, dx, dy in ADAM7 if interlace else ((0, 0, 1, 1),):
        if x < width and y < height:
            columns = (width - x + dx - 1) // dx
            rows = (height - y + dy - 1) // dy
            total += rows * (1 + (columns * bits_per_pixel + 7) // 8)
    return total


def _png_scaffold(encoded):
    """Check framing and retain every non-IDAT byte and the position of the IDAT run."""
    data = memoryview(encoded)
    if data[:8] != PNG_SIGNATURE:
        raise ValueError("Wrong figure format")
    position, inflated = 8, 0
    scaffold, stream = [], zlib.decompressobj()
    idat_started = idat_ended = palette = False
    while position + 12 <= len(data):
        length, kind = unpack_from(">I4s", data, position)
        end = position + length + 12
        if length >= 2**31 or end > len(data) or not kind.isalpha() or not kind[2:3].isupper():
            raise ValueError("Invalid PNG chunk framing")
        payload = data[position + 8:end - 4]
        if zlib.crc32(data[position + 4:end - 4]) != unpack_from(">I", data, end - 4)[0]:
            raise ValueError(f"Invalid PNG CRC for {kind!r}")
        if position == 8:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG must start with one IHDR")
            expected = _scanline_bytes(payload)
            depth, color = payload[8:10]
        elif kind == b"IHDR":
            raise ValueError("PNG has a duplicate IHDR")
        if kind == b"IDAT":
            if idat_ended:
                raise ValueError("PNG IDAT chunks must be consecutive")
            if not idat_started:
                scaffold.append(b"IDAT")
                idat_started = True
            pending = payload
            try:
                while pending:
                    limit = min(1 << 20, expected - inflated + 1)
                    inflated += len(stream.decompress(pending, limit))
                    if inflated > expected or stream.unused_data:
                        raise ValueError("Unexpected data in PNG IDAT stream")
                    pending = stream.unconsumed_tail
            except zlib.error as exc:
                raise ValueError("Invalid compressed PNG data") from exc
        else:
            if kind == b"PLTE":
                if (palette or idat_started or color in (0, 4) or not 0 < length <= 768
                        or length % 3 or (color == 3 and length // 3 > 2**depth)):
                    raise ValueError("Invalid PNG palette")
                palette = True
            elif kind[0:1].isupper() and kind not in (b"IHDR", b"IEND"):
                raise ValueError(f"Unknown critical PNG chunk {kind!r}")
            scaffold.append(data[position:end])
            idat_ended = idat_started
        if kind == b"IEND":
            if length or end != len(data):
                raise ValueError("Invalid PNG IEND or trailing data")
            if (not idat_started or not stream.eof or inflated != expected
                    or (color == 3 and not palette)):
                raise ValueError("Incomplete PNG image data")
            return scaffold
        position = end
    raise ValueError("Missing or truncated PNG IEND")


def _compare_png(left, right, *, name, lossless_png):
    if not lossless_png and left != right:
        raise ValueError(f"Different encoded figure {name}")
    scaffold = _png_scaffold(left)
    if left != right and scaffold != _png_scaffold(right):
        raise ValueError(f"Different non-IDAT PNG chunks for {name}")
    with Image.open(BytesIO(left)) as control, Image.open(BytesIO(right)) as candidate:
        if control.format != "PNG" or candidate.format != "PNG":
            raise ValueError("Wrong figure format")
        control.load()
        candidate.load()
        if lossless_png:
            # Pillow would downconvert 16-bit multichannel PNGs when reading pixels.
            if (control.n_frames != 1 or candidate.n_frames != 1
                    or (left[24] == 16 and left[25] != 0)):
                raise ValueError(f"Unsupported pixel representation for {name}")
            if (control.mode, control.size) != (candidate.mode, candidate.size):
                raise ValueError(f"Different decoded PNG mode or dimensions for {name}")
            if control.tobytes() != candidate.tobytes():
                raise ValueError(f"Different decoded PNG pixels for {name}")
        return list(control.size)


def audit(pair, *, lossless_png=False, read_only=False, bind_native=False):
    data = json.loads(pair.read_bytes())
    if "failure" in data:
        raise ValueError("Cannot audit a failed pair as an exact success")
    before, after = (data["runs"][method] for method in ("baseline", "candidate"))
    state = before["receipt"].get("decision", "complete")
    if state != after["receipt"].get("decision", "complete") or before.get("reason") != after.get("reason"):
        raise ValueError("Different terminal decisions or reasons")
    if state not in ("complete", "withheld"):
        raise ValueError("Expected a completed publication or withholding")
    for key in ("arms", "owners", "scientific_digests"):
        if before[key] != after[key]:
            raise ValueError(f"Different published {key}")
    if not lossless_png and before["artifacts"] != after["artifacts"]:
        raise ValueError("Different published artifacts")
    probes, timings, stores, detectors = {}, {}, {}, {}
    for method, row in (("baseline", before), ("candidate", after)):
        root = pair.parent / method
        files = list((root / "fast-scan-automatic-work").glob("*/detections.json"))
        if len(files) != 1:
            raise ValueError("Expected one sealed receiver output")
        doc = json.loads(files[0].read_bytes())
        probes[method] = doc["source"]["probes"]
        scans = FastScanStore(root)
        run_id = row["receipt"]["run_id"]
        workspace = scans.automatic_workspace(run_id, create=False) if read_only else scans.automatic_workspace(run_id)
        terminal = workspace / "terminal.json"
        if bind_native:
            if (canonical_digest(doc) != json.loads(terminal.read_bytes())["native_sha256"]
                    or doc["source"]["raw_recording_authority_digest"] != row["raw_authority"]):
                raise ValueError(f"Detector output differs from the {method} terminal binding")
            detectors[method] = doc["provenance"]["detector_sha256"]
        terminal_ns = terminal.stat().st_mtime_ns
        delta = (terminal_ns - files[0].stat().st_mtime_ns) / 1e9
        timings[method] = dict(launch_to_detections=row["terminal_file_s"] - delta,
                               detections_to_terminal=delta,
                               terminal_to_exit=row["elapsed_s"] - row["terminal_file_s"])
        if min(timings[method].values()) < 0:
            raise ValueError("Published file timestamps disagree with the launch clock")
        store = FastStandardAnalysisStore(root)
        manifest = store.detail(run_id)
        expected = PLOTS if state == "complete" else ()
        if (manifest["state"] != state or manifest["artifacts"] != row["artifacts"]
                or tuple(item["name"] for item in manifest["artifacts"]) != expected):
            if state == "complete":
                raise ValueError(f"Expected all eight ordered figures in the {method} publication")
            raise ValueError(f"Unexpected figures in the {method} withholding")
        stores[method] = (store, run_id)
    if probes["baseline"] != probes["candidate"]:
        raise ValueError("Receiver output changed")

    control_store, control_run = stores["baseline"]
    candidate_store, candidate_run = stores["candidate"]
    figures, encoded_matches = {}, {}
    for control_item, candidate_item in zip(before["artifacts"], after["artifacts"], strict=True):
        name = control_item["name"]
        control = control_store.artifact(control_run, name, control_item["sha256"])
        candidate = candidate_store.artifact(candidate_run, name, candidate_item["sha256"])
        figures[name] = _compare_png(control, candidate, name=name, lossless_png=lossless_png)
        encoded_matches[name] = control == candidate
    packed = json.dumps(probes["baseline"], sort_keys=True, separators=(",", ":")).encode()
    result = dict(
        session=before["receipt"]["session_id"], probe_rows=len(probes["baseline"]),
        selected=sum(len(r["candidates"]) for r in probes["baseline"]),
        probe_rows_sha256=sha256(packed).hexdigest(), image_dimensions=figures,
        elapsed_stages_s=timings, elapsed_speedup=before["elapsed_s"] / after["elapsed_s"],
        cpu_speedup=before["cpu_s"] / after["cpu_s"],
    )
    if lossless_png:
        result.update(image_comparison="lossless-png", encoded_images_equal=encoded_matches)
    if bind_native:
        result["detector_sha256"] = detectors
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path, nargs="+")
    parser.add_argument(
        "--lossless-png", action="store_true",
        help="allow IDAT re-encoding with identical decoded pixels and PNG metadata",
    )
    args = parser.parse_args()
    results = {pair.parent.name: audit(pair, lossless_png=args.lossless_png) for pair in args.pair}
    print(json.dumps(results, indent=2))
