import json
import os
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
from struct import pack, unpack_from
from zlib import crc32

import pytest
from PIL import Image, PngImagePlugin

from leo.contracts.fast_standard_analysis import MODEL, PLOTS
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


@pytest.fixture(scope="module")
def auditor():
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    source = reports / "audit_shared_publication.py"
    spec = spec_from_file_location(source.stem, source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png(level, *, change_pixel=False, software="ALGO08", dpi=150, reverse_metadata=False):
    image = Image.new("RGBA", (32, 21), (8, 33, 54, 255))
    if change_pixel:
        image.putpixel((31, 20), (8, 33, 54, 254))
    metadata = PngImagePlugin.PngInfo()
    items = [("Software", software), ("Description", "paired PNG")]
    for key, value in reversed(items) if reverse_metadata else items:
        metadata.add_text(key, value)
    stream = BytesIO()
    image.save(stream, format="PNG", compress_level=level, pnginfo=metadata, dpi=(dpi, dpi))
    return stream.getvalue()


def rewrite_idat(encoded, replacement):
    start = 8
    while start < len(encoded):
        length, kind = unpack_from(">I4s", encoded, start)
        end = start + length + 12
        if kind == b"IDAT":
            chunks = []
            for payload in replacement(encoded[start + 8:end - 4]):
                body = b"IDAT" + payload
                chunks.append(pack(">I", len(payload)) + body + pack(">I", crc32(body)))
            return encoded[:start] + b"".join(chunks) + encoded[end:]
        start = end
    raise AssertionError("Fixture has no IDAT")


def publish_pair(tmp_path, control, candidate, *, same_other_images=False):
    runs = {}
    run_id = "example-publication"
    for method, encoded in (("baseline", control), ("candidate", candidate)):
        root = tmp_path / method
        workspace = FastScanStore(root).automatic_workspace(run_id)
        probes = [{"receiver_id": 0, "candidates": [{"cfo_hz": -3120}]}]
        for name, document, time_ns in (
            ("detections.json", {"source": {"probes": probes}}, 1_000_000_000),
            ("terminal.json", {}, 2_000_000_000),
        ):
            path = workspace / name
            path.write_text(json.dumps(document))
            os.utime(path, ns=(time_ns, time_ns))
        images = {name: control if same_other_images else encoded for name in PLOTS}
        images[PLOTS[-1]] = encoded
        arms = {
            arm: {"associated_points": 1, "endpoint_latlon": [0.2, 0.3]}
            for arm in ("c0", "fitted_c")
        }
        publication = FastStandardAnalysisStore(root).publish(
            run_id,
            dict(schema_version=1, model_version=MODEL, run_id=run_id, state="complete",
                 reference_usage="evaluation_only", arms=arms, glrt_points=1),
            images,
        )
        runs[method] = dict(receipt={"run_id": run_id, "session_id": "example-session"},
                            arms=arms, owners={"c0": "first", "fitted_c": "first"},
                            scientific_digests={"grid": "grid", "path": "path"},
                            artifacts=publication["artifacts"], terminal_file_s=2.0,
                            elapsed_s=3.0, cpu_s=2.5)
    path = tmp_path / "pair.json"
    path.write_text(json.dumps({"runs": runs}))
    return path


def test_opt_in_matches_every_reencoded_image_and_default_requires_bytes(auditor, tmp_path):
    pair = publish_pair(tmp_path, png(0), png(9))
    with pytest.raises(ValueError, match="Different published artifacts"):
        auditor.audit(pair)
    result = auditor.audit(pair, lossless_png=True)
    assert result["image_comparison"] == "lossless-png"
    assert tuple(result["image_dimensions"]) == PLOTS
    assert all(dimensions == [32, 21] for dimensions in result["image_dimensions"].values())
    assert result["encoded_images_equal"] == dict.fromkeys(PLOTS, False)
    assert result["probe_rows"] == result["selected"] == 1


def test_byte_equal_default_keeps_receipt_format(auditor, tmp_path):
    raw = png(6)
    result = auditor.audit(publish_pair(tmp_path, raw, raw))
    assert tuple(result["image_dimensions"]) == PLOTS
    assert "image_comparison" not in result
    assert "encoded_images_equal" not in result


def test_lossless_mode_accepts_consecutive_idat_rechunking(auditor, tmp_path):
    original = png(6)
    split = rewrite_idat(original, lambda data: (data[:4], data[4:]))
    pair = publish_pair(tmp_path, original, split)
    assert not any(auditor.audit(pair, lossless_png=True)["encoded_images_equal"].values())


@pytest.mark.parametrize("changes,error", [
    ({"change_pixel": True}, "Different decoded PNG pixels"),
    ({"software": "changed"}, "Different non-IDAT PNG chunks"),
    ({"dpi": 120}, "Different non-IDAT PNG chunks"),
    ({"reverse_metadata": True}, "Different non-IDAT PNG chunks"),
])
def test_lossless_mode_checks_last_plot_pixels_and_metadata(auditor, tmp_path, changes, error):
    pair = publish_pair(tmp_path, png(0), png(9, **changes), same_other_images=True)
    with pytest.raises(ValueError, match=error):
        auditor.audit(pair, lossless_png=True)


@pytest.mark.parametrize("damage,error", [
    (lambda png: png[:-1] + bytes([png[-1] ^ 1]), "Invalid PNG CRC"),
    (lambda png: png + b"trailing", "trailing data"),
    (lambda png: png[:-12], "Missing or truncated PNG IEND"),
    (lambda png: rewrite_idat(png, lambda data: (data + b"trailing",)), "PNG IDAT stream"),
])
def test_lossless_mode_rejects_malformed_png_with_valid_manifest(auditor, tmp_path, damage, error):
    pair = publish_pair(tmp_path, png(0), damage(png(9)), same_other_images=True)
    with pytest.raises(ValueError, match=error):
        auditor.audit(pair, lossless_png=True)


@pytest.mark.parametrize("change,error", [
    (lambda row: row["artifacts"].reverse(), "all eight ordered figures"),
    (lambda row: row["artifacts"].pop(), "all eight ordered figures"),
    (lambda row: row["artifacts"][-1].update(byte_count=1), "all eight ordered figures"),
    (
        lambda row: row["scientific_digests"].update(grid="changed"),
        "Different published scientific_digests",
    ),
])
def test_lossless_mode_preserves_inventory_and_scientific_checks(auditor, tmp_path, change, error):
    pair = publish_pair(tmp_path, png(0), png(9))
    receipt = json.loads(pair.read_bytes())
    change(receipt["runs"]["candidate"])
    pair.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match=error):
        auditor.audit(pair, lossless_png=True)


def test_lossless_mode_verifies_each_encoded_file_against_its_own_manifest(auditor, tmp_path):
    pair = publish_pair(tmp_path, png(0), png(9))
    receipt = json.loads(pair.read_bytes())["runs"]["candidate"]
    store = FastStandardAnalysisStore(tmp_path / "candidate")
    digest = receipt["artifacts"][-1]["sha256"].removeprefix("sha256:")
    path = store.folder(receipt["receipt"]["run_id"]) / f"{digest}.png"
    path.write_bytes(png(1))
    with pytest.raises(ValueError, match="Standard figure integrity failure"):
        auditor.audit(pair, lossless_png=True)
