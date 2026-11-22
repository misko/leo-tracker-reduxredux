"""Measure lossless PNG encoding using the eight actual published rasters."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import process_time

from PIL import Image, PngImagePlugin
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def encode(image, level):
    stream = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    for key, value in image.text.items():
        metadata.add_text(key, value)
    image.save(stream, format="PNG", compress_level=level, pnginfo=metadata, dpi=image.info["dpi"])
    return stream.getvalue()


def compare(inputs):
    rows = []
    for order in ((6, 3, 1), (1, 3, 6)):
        for level in order:
            total_s, size, originals = 0., 0, 0
            for original, image in inputs:
                start = process_time()
                payload = encode(image, level)
                total_s += process_time() - start
                with Image.open(BytesIO(payload)) as decoded:
                    if (decoded.mode != image.mode or decoded.size != image.size or
                            decoded.tobytes() != image.tobytes() or decoded.info != image.info):
                        raise ValueError("Raster or PNG metadata changed")
                size += len(payload)
                originals += sha256(payload).digest() == sha256(original).digest()
            rows.append(dict(order=order, compression=level, cpu_s=total_s, encoded_bytes=size,
                             original_bytes_matched=originals, pixels_and_metadata_matched=len(inputs)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path)
    args = parser.parse_args()
    pair = json.loads(args.pair.read_bytes())
    base = pair["runs"]["baseline"]
    store = FastStandardAnalysisStore(args.pair.parent/"baseline")
    inputs = []
    for entry in base["artifacts"]:
        original = store.artifact(base["receipt"]["run_id"], entry["name"], entry["sha256"])
        image = Image.open(BytesIO(original))
        image.load()
        inputs.append((original,image))
    if len(inputs) != 8:
        raise ValueError("Expected all eight PNGs from a completed position")
    print(json.dumps(dict(session=base["receipt"]["session_id"], rows=compare(inputs),
                          original_bytes=sum(len(p) for p,_ in inputs)), indent=2))


if __name__ == "__main__":
    main()
