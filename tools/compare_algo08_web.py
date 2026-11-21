"""Download two published manifests and pair their digest-verified Gauss web PNGs."""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont

from leo.contracts.fast_standard_analysis import ALGO08, MODEL, PLOTS


def gallery(origin, original, compact, out):
    def fetch(path):
        with urlopen(origin.rstrip("/") + path, timeout=30) as response:
            return response.read(), response.headers.get_content_type()

    roots = [f"/api/v2/fast-scans/{quote(rid, safe='')}/standard-analysis" for rid in (original, compact)]
    docs = [json.loads(fetch(root)[0]) for root in roots]
    if ([d["model_version"] for d in docs] != [MODEL, ALGO08]
            or docs[0]["session_id"] != docs[1]["session_id"]
            or [d["run_id"] for d in docs] != [original, compact]
            or any(d["state"] != "complete" or [a["name"] for a in d["artifacts"]] != list(PLOTS)
                   for d in docs)):
        raise ValueError("Expected two complete publications for the same capture")
    out.mkdir(parents=True, exist_ok=True)
    receipt = dict(session=docs[0]["session_id"], runs=[original, compact], figures={})
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 29)
    for name in PLOTS:
        pair, evidence = [], []
        for root, doc in zip(roots, docs, strict=True):
            entry = next(a for a in doc["artifacts"] if a["name"] == name)
            path = f"{root}/{name}.png?sha256={quote(entry['sha256'], safe='')}"
            raw, kind = fetch(path)
            if (kind != "image/png" or len(raw) != entry["byte_count"]
                    or "sha256:" + hashlib.sha256(raw).hexdigest() != entry["sha256"]):
                raise ValueError("Web PNG differs from its publication")
            with Image.open(BytesIO(raw)) as im:
                if im.format != "PNG":
                    raise ValueError("Invalid PNG")
                page = im.convert("RGB")
            evidence.append(dict(url=path, pixels=list(page.size), **entry))
            page.thumbnail((1500, 1600), Image.Resampling.LANCZOS)
            pair.append(page)
        width = max(im.width for im in pair)
        canvas = Image.new("RGB", (width*2+24, max(im.height for im in pair)+60), "white")
        pen = ImageDraw.Draw(canvas)
        for i, (label, page) in enumerate(zip(("ALGO07", "ALGO08"), pair, strict=True)):
            x = (width+24)*i
            pen.text((x+20, 9), label, font=font, fill="#192f3c")
            canvas.paste(page, (x+(width-page.width)//2, 60))
        canvas.save(out/(name+".png"), optimize=True)
        receipt["figures"][name] = evidence
    (out/"web-figures.json").write_text(json.dumps(receipt, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("original")
    parser.add_argument("compact")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    gallery(args.origin, args.original, args.compact, args.out)
