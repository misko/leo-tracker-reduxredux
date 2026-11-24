from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from reports.ALGO08.v3.pillow_rgba_evidence import evidence
from reports.ALGO08.v3.png_readback_transfer import read_artifacts


@pytest.mark.parametrize("mode", ("RGBA", "RGB", "L", "LA", "P", "1", "I;16"))
def test_normal_decode_same_bytes_for_rgba_and_other_pillow_modes(mode, monkeypatch):
    contents = BytesIO()
    with Image.new(mode, (5, 7)) as fixture:
        fixture.save(contents, format="PNG")
    data = contents.getvalue()
    original = Image.Image.convert
    with Image.open(BytesIO(data)) as decoded:
        decoded.load()
        expected = sha256(decoded.convert("RGBA").tobytes()).hexdigest()
    calls = []

    def trace(image, *args, **kwargs):
        calls.append(image.mode)
        return original(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", trace)
    assert evidence(data, "encoded") == {"size": (5, 7), "sha256": "encoded", "rgba_sha256": expected}
    assert bool(calls) is (mode != "RGBA")


def test_truncated_png_raises_original_pillow_error():
    contents = BytesIO()
    with Image.new("RGBA", (300, 30)) as fixture:
        fixture.save(contents, format="PNG", compress_level=0)
    corrupt = contents.getvalue()[:128]
    with Image.open(BytesIO(corrupt)) as original:
        with pytest.raises(OSError) as expected:
            original.load()
    with pytest.raises(type(expected.value)) as observed:
        evidence(corrupt, "encoded")
    assert str(observed.value) == str(expected.value)


def test_live_verified_store_reads_are_required_even_after_success():
    calls = []

    class Store:
        def artifact(self, run, name, expected):
            calls.append((run, name, expected))
            if len(calls) == 2:
                raise ValueError("Standard figure integrity failure")
            return b"verified first read"

    store = Store()
    requests = [("position", {"sha256": "encoded"})]
    witness = dict(size=(1, 1), sha256="encoded", rgba_sha256="pixels")
    assert read_artifacts(store, "run", requests, lambda *args: witness)[0]["position"]["rgba_sha256"] == "pixels"
    with pytest.raises(ValueError, match="Standard figure integrity failure"):
        read_artifacts(store, "run", requests, lambda *args: witness)
