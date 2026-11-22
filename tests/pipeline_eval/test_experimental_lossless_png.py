import json
import shutil
import subprocess
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from struct import unpack_from
from types import SimpleNamespace

import numpy as np
import pytest
from matplotlib.image import imsave
from PIL import Image, PngImagePlugin

from tools import algo08_scan
from tools.pipeline_eval.qualification import experimental_publication, freeze_publication
from tools.pipeline_eval.qualification.paired_publication import verify_sources
from tools.pipeline_eval.variants.experimental import lossless_png
from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng


@pytest.fixture(scope="module")
def filter_library(tmp_path_factory):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("The optional PNG prototype requires a C compiler")
    library = tmp_path_factory.mktemp("png-filter") / "filters.so"
    source = Path(__file__).parents[2] / "tools/pipeline_eval/variants/experimental/lossless_png.c"
    subprocess.run(
        [
            compiler,
            "-O3",
            "-shared",
            "-fPIC",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(library),
        ],
        check=True,
    )
    if LosslessPng(library).libraries is None:
        pytest.skip("The optional PNG prototype requires the libdeflate.so.0 runtime")
    return library


def _encode(save, pixels, **kwargs):
    stream = BytesIO()
    save(stream, pixels, format="png", origin=kwargs.pop("origin", "upper"), **kwargs)
    return stream.getvalue()


def _ancillary_chunks(payload):
    result = []
    offset = 8
    while offset < len(payload):
        count, tag = unpack_from(">I4s", payload, offset)
        end = offset + count + 12
        if tag not in {b"IDAT", b"IHDR"}:
            result.append(payload[offset:end])
        offset = end
    return result


@pytest.mark.parametrize("width, height", [(1, 1), (2, 5), (5, 5), (9, 5), (33, 6)])
def test_libdeflate_preserves_rgba_bytes_and_every_metadata_chunk(filter_library, width, height):
    values = np.random.default_rng(42).integers(0, 256, (height, width, 4), dtype=np.uint8)
    # Zero alpha still carries meaningful RGB here. The repeats exercise Up.
    values[::2, :, 3] = 0
    if height > 1:
        values[1] = values[0]
    pixels = memoryview(values).toreadonly()
    metadata = dict(
        Software=None,
        Paper="café",
        Heading="曲線 and UTF-8",
        Comment=PngImagePlugin.iTXt("Über", lang="de", tkey="Kommentar"),
    )
    control = _encode(imsave, pixels, dpi=120.25, metadata=metadata)
    results = []
    for simd in (False, True):
        profile = []
        candidate = _encode(
            LosslessPng(filter_library, simd=simd, profile=profile).wrap(imsave),
            pixels,
            dpi=120.25,
            metadata=metadata,
        )
        assert len(profile) == 1
        assert profile[0]["scanline_bytes"] == (4 * width + 1) * height
        with Image.open(BytesIO(candidate)) as image:
            image.verify()
        with Image.open(BytesIO(control)) as expected, Image.open(BytesIO(candidate)) as actual:
            assert actual.format == "PNG"
            assert actual.mode == expected.mode == "RGBA"
            assert actual.size == expected.size == (width, height)
            assert actual.tobytes() == expected.tobytes() == values.tobytes()
            assert actual.info == expected.info
        assert _ancillary_chunks(candidate) == _ancillary_chunks(control)
        results.append(candidate)
    assert results[0] == results[1]


def test_missing_native_library_obeys_the_original_writer(tmp_path):
    encoder = LosslessPng(tmp_path / "unavailable.so", profile=[])
    pixels = memoryview(np.zeros((2, 3, 4), dtype=np.uint8))
    assert _encode(encoder.wrap(imsave), pixels, dpi=120) == _encode(imsave, pixels, dpi=120)
    assert encoder.profile == []


def test_unsupported_inputs_keep_original_pillow_encoding(filter_library, tmp_path):
    encoder = LosslessPng(filter_library, profile=[])
    save = encoder.wrap(imsave)
    values = np.arange(4 * 3 * 4, dtype=np.uint8).reshape((4, 3, 4))
    pixels = memoryview(values)
    for source, options in (
        (values, {}),
        (memoryview(values[::-1]), {}),
        (pixels, dict(origin="lower")),
        (pixels, dict(pil_kwargs=dict(compress_level=1))),
    ):
        assert _encode(save, source, **options) == _encode(imsave, source, **options)
    png = tmp_path / "named.png"
    save(fname=png, arr=pixels, format="png", origin="upper")
    assert png.read_bytes() == _encode(imsave, pixels)
    assert encoder.profile == []


def test_freezer_requires_and_binds_both_png_libraries(tmp_path):
    release, checkout = tmp_path / "release", Path(__file__).parents[2]
    (release / "tools").mkdir(parents=True)
    detector = tmp_path / "detector.so"
    detector.write_bytes(b"detector fixture")
    digest = sha256(detector.read_bytes()).hexdigest()
    output = tmp_path / "frozen"
    args = (checkout, output, detector, digest, "stock", "stock", release)
    libraries = {}
    for name in experimental_publication.PNG_LIBRARIES:
        binary = tmp_path / name
        binary.write_text(name)
        libraries[name] = binary, sha256(binary.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="both reviewed PNG"):
        freeze_publication.freeze(*args, rendering="lossless-raster")
    with pytest.raises(ValueError, match="png_deflate library differs"):
        freeze_publication.freeze(
            *args,
            rendering="lossless-raster",
            png_filter=libraries["png_filter"],
            png_deflate=(libraries["png_deflate"][0], "0" * 64),
        )
    assert not output.exists()
    spec = freeze_publication.freeze(*args, rendering="lossless-raster", **libraries)
    for name, filename in experimental_publication.PNG_LIBRARIES.items():
        original, digest = libraries[name]
        library = output / filename
        assert spec[name] == dict(library=str(library), sha256=digest)
        assert library.read_bytes() == original.read_bytes()
        assert spec["sources"][filename] == digest
    for name in (
        "lossless_png.c",
        "lossless_png.py",
        "raster_layout.py",
        "shared_orbit_figures.py",
    ):
        assert f"tools/pipeline_eval/variants/experimental/{name}" in spec["sources"]
    verify_sources(output / freeze_publication.LAUNCHER, spec["sources"])


@pytest.mark.parametrize("substituted", list(experimental_publication.PNG_LIBRARIES))
def test_launch_loads_only_checked_png_bytes_and_supports_fallback(
    tmp_path, monkeypatch, substituted
):
    stock = algo08_scan.render
    output = tmp_path / "output"
    output.mkdir()
    detector = tmp_path / "detector.so"
    detector.touch()
    region = tmp_path / "region.json"
    region.write_text(json.dumps(dict(center=[-33, 113], width_km=35)))
    args = SimpleNamespace(
        recording=tmp_path / "opaque", bulk_root=output, archive=tmp_path / "tle", region=region
    )
    spec = dict(
        solver="stock",
        rendering="lossless-raster",
        detector=str(detector),
        detector_sha256="c" * 64,
    )
    for name, filename in experimental_publication.PNG_LIBRARIES.items():
        binary = tmp_path / filename
        binary.write_text(name)
        spec[name] = dict(library=str(binary), sha256=sha256(binary.read_bytes()).hexdigest())

    packet = {"position": b"original"}

    def load(filter_path, deflate_path):
        for name, private in zip(
            experimental_publication.PNG_LIBRARIES, (filter_path, deflate_path), strict=True
        ):
            public = Path(spec[name]["library"])
            assert private != public
            assert private.read_bytes() == public.read_bytes()
        return None

    monkeypatch.setattr(lossless_png, "_libraries", load)
    monkeypatch.setattr(lossless_png, "render_layout", lambda science, **kwargs: science)
    monkeypatch.setattr(algo08_scan, "analyze", lambda *args: algo08_scan.render(packet))
    assert experimental_publication.run(args, spec) == packet
    assert algo08_scan.render is stock
    Path(spec[substituted]["library"]).write_bytes(b"substituted")
    with pytest.raises(ValueError, match=f"{substituted} library differs"):
        experimental_publication.run(args, spec)
