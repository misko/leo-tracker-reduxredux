"""The normal Pillow verifier without duplicating an already decoded RGBA raster."""

from hashlib import sha256
from io import BytesIO


def evidence(data, digest):
    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.mode == "RGBA":
            pixels = image.tobytes()
        else:
            with image.convert("RGBA") as converted:
                pixels = converted.tobytes()
        return dict(size=image.size, sha256=digest, rgba_sha256=sha256(pixels).hexdigest())
