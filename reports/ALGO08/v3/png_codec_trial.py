"""Price zlib-compatible encoding in the real eight-PNG weak saved publication."""

import argparse
from contextlib import contextmanager
from ctypes import c_ubyte, memmove
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch
import zlib

import one_pass_web_png_trial as prior
from calibration_png_layers import EXPLICIT, EXPLICIT_SHA, WORK, name_outputs, probes


HERE = Path(__file__).resolve().parent
ORDER = ("level3", "level2", "level6", "rle", "rle", "level6", "level2", "level3")


class ZlibRle:
    """Experimental DEFLATE strategy with the incumbent row filter and PNG writer."""

    @staticmethod
    def libdeflate_alloc_compressor(level):
        return zlib.compressobj(1, zlib.DEFLATED, zlib.MAX_WBITS, 8, zlib.Z_RLE)

    @staticmethod
    def libdeflate_zlib_compress_bound(compressor, size):
        return size + (size >> 3) + 1024

    @staticmethod
    def libdeflate_zlib_compress(compressor, source, size, destination, bound):
        pixels = (c_ubyte * size).from_address(source)
        encoded = compressor.compress(pixels) + compressor.flush()
        if len(encoded) > bound:
            return 0
        memmove(destination, encoded, len(encoded))
        return len(encoded)

    @staticmethod
    def libdeflate_free_compressor(compressor):
        pass


@contextmanager
def encoder_settings(mode):
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng

    original = LosslessPng._encode
    level = 3 if mode == "rle" else int(mode.removeprefix("level"))
    timings = []

    def encode(encoder, *args):
        libraries = encoder.libraries
        if mode == "rle" and libraries is not None:
            libraries = (libraries[0], ZlibRle())
        with patch.multiple(encoder, level=level, profile=timings, libraries=libraries):
            return original(encoder, *args)

    with patch.object(LosslessPng, "_encode", encode):
        yield timings


def file_chunks(data):
    """Validate PNG CRCs and bind ancillary chunks without binding IDAT bytes."""
    from struct import unpack_from

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature")
    ancillary, cursor, image_data = [], 8, 0
    while cursor < len(data):
        size, name = unpack_from(">I4s", data, cursor)
        end = cursor + 8 + size
        if end + 4 > len(data) or len(name) != 4:
            raise ValueError("Truncated PNG chunk")
        if zlib.crc32(data[cursor + 4:end]) != unpack_from(">I", data, end)[0]:
            raise ValueError("Invalid PNG chunk CRC")
        if name == b"IDAT":
            image_data += size
        else:
            ancillary.append((name.decode("ascii"), sha256(data[cursor:end + 4]).hexdigest()))
        cursor = end + 4
    if not image_data or not ancillary or ancillary[0][0] != "IHDR" or ancillary[-1][0] != "IEND":
        raise ValueError("Incomplete PNG")
    return ancillary


def verify(store, run, rendered, original, expected):
    detail = store.detail(run)
    expected_manifest = {key: value for key, value in original["manifest"].items() if key != "artifacts"}
    immutable = prior.read(store.folder(run) / "manifest.json")
    if {key: value for key, value in immutable.items() if key != "artifacts"} != expected_manifest:
        raise ValueError("Saved official manifest changed apart from PNG content addresses")
    figures = {}
    for row in detail["artifacts"]:
        name = row["name"]
        data = store.artifact(run, name, row["sha256"])
        image = prior.image_evidence(data)
        visual = {key: image[key] for key in ("size", "mode", "rgba_sha256", "metadata")}
        if (rendered[name] != data or json.loads(json.dumps(visual)) != expected[name]
                or image["sha256"] != row["sha256"] or row["byte_count"] != len(data)):
            raise ValueError(f"Saved {name} differs in decoded pixels, metadata, dimensions or content address")
        figures[name] = dict(image, chunks=file_chunks(data))
    media = figures["position"]["sha256"]
    sidecars = {key: getattr(store, "position_" + key)(run) for key in ("grid", "path")}
    for name, data in sidecars.items():
        reference = original[name]
        if data != dict(reference, binding=dict(reference["binding"], position_png_sha256=media)):
            raise ValueError(f"Saved {name} changed beyond its real position PNG pointer")
    return figures


def store_images(output, manifest, original, pngs):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    output.mkdir()
    store = FastStandardAnalysisStore(output)
    start = prior.clocks()
    store.publish(manifest["run_id"], manifest, pngs,
                  position_grid=original["grid"], position_path=original["path"])
    return store, prior.since(start)


def durable(manifest, original, expected, products, contender):
    # The only disk probe is the temporary official compact publication on local ext4.
    def nvme_snapshot():
        return tuple(map(int, Path("/sys/class/block/nvme0n1/stat").read_text().split()[:11]))

    local = Path("/var/tmp")
    source, fstype, device = subprocess.check_output(
        ["findmnt", "-T", str(local), "-no", "SOURCE,FSTYPE,MAJ:MIN"], text=True,
    ).split()
    mount = dict(source=source, fstype=fstype, device=device, available_bytes=shutil.disk_usage(local).free)
    before = nvme_snapshot()
    results = []
    if (mount["fstype"] == "ext4" and mount["available_bytes"] > 128 * 2**20
            and (Path("/sys/dev/block") / device / "slaves/nvme0n1p3").exists()):
        with TemporaryDirectory(prefix="leo-weak-png-codec-", dir=local) as base:
            for number, mode in enumerate(("level3", contender, contender, "level3")):
                calls = []
                sync = os.fsync

                def observed(fd):
                    path = os.readlink(f"/proc/self/fd/{fd}")
                    start = perf_counter_ns()
                    sync(fd)
                    calls.append((Path(path).suffix, perf_counter_ns() - start))

                with patch.object(os, "fsync", observed):
                    store, clocks = store_images(Path(base) / str(number), manifest, original, products[mode])
                verify(store, manifest["run_id"], products[mode], original, expected)
                if len(calls) != 14 or sum(name == ".png" for name, _ in calls) != 8:
                    raise ValueError("Durable publisher changed its original sync schedule")
                results.append(dict(mode=mode, publication=clocks, calls=calls))
    return dict(mount=mount, nvme_before=before, nvme_after=nvme_snapshot(),
                pressure=Path("/proc/pressure/io").read_text(), runs=results)


def compare(packet, renderer, options, archived, original, destination):
    from one_pass_web_png import render

    science = prior.verify_packet(packet, original, archived)
    if not all(science.values()):
        raise ValueError("The original weak plotting packet changed")
    reference = prior.sealed(EXPLICIT, EXPLICIT_SHA)["publication"]["direct"]["figures"]
    expected = {name: {key: item[key] for key in ("size", "mode", "rgba_sha256", "metadata")}
                for name, item in reference.items()}
    manifest = {k: v for k, v in original["manifest"].items() if k != "artifacts"}
    results, references, products = [], {}, {}
    for number, mode in enumerate(ORDER):
        with encoder_settings(mode) as encoding, probes(enabled=True) as draw:
            start = prior.clocks()
            pngs, layout = render(renderer, packet, enabled=True, **options)
            render_clock = prior.since(start)
        store, commit_clock = store_images(destination / f"{number}-{mode}", manifest, original, pngs)
        start = prior.clocks()
        figures = verify(store, manifest["run_id"], pngs, original, expected)
        check_clock = prior.since(start)
        if layout != WORK or draw["canvases"] != 6 or len(encoding) != 8:
            raise ValueError(f"Expected six Agg draws and eight native encodes: {layout}, {draw['canvases']}, {len(encoding)}")
        name_outputs(draw["outputs"], pngs)
        if pngs.keys() != reference.keys() or figures != references.setdefault(mode, figures):
            raise ValueError("Expected all eight deterministic figure products")
        if mode == "level3" and any(figures[name]["sha256"] != item["sha256"] for name, item in reference.items()):
            raise ValueError("Incumbent encoded bytes differ from the prior qualified publication")
        products.setdefault(mode, pngs)
        results.append(dict(mode=mode, render=render_clock, publish=commit_clock, verify=check_clock,
                            encode_cpu_ns=sum(row["encode_cpu_s"] for row in encoding) * 1e9,
                            bytes=sum(map(len, pngs.values())), encode=encoding, draws=draw["canvases"]))
        print(mode, results[-1]["bytes"], round(results[-1]["encode_cpu_ns"] / 1e6, 2), flush=True)
    if any(item["chunks"] != references["level3"][name]["chunks"]
           for figures in references.values() for name, item in figures.items()):
        raise ValueError("An encoder changed the original non-IDAT chunks")
    medians = {mode: median(row["encode_cpu_ns"] for row in results if row["mode"] == mode)
               for mode in references}
    contender = min((mode for mode in medians if mode != "level3"), key=medians.__getitem__)
    evidence = dict(science=science, runs=results, figures=references, zlib_version=zlib.ZLIB_RUNTIME_VERSION,
                    explicit_sha256=EXPLICIT_SHA, contender=contender, encode_cpu_medians_ns=medians)
    prior.write(destination / "render-sealed.json", evidence)
    return dict(evidence, durable=durable(manifest, original, expected, products, contender))


def run(destination):
    original = prior.authority

    def authority(specification):
        result = original(specification)
        paths = (Path(__file__), HERE / "png-codec-protocol.md", EXPLICIT)
        result["files"].update({str(p): prior.file_sha(p) for p in paths})
        return result

    with patch.object(prior, "authority", authority), patch.object(prior, "ORDER", ORDER), patch.object(prior, "compare", compare):
        prior.run(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    run(parser.parse_args().destination)
