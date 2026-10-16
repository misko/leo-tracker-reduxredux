"""Render the saved HTML report as GitHub Markdown without rerunning fits.

Run from any directory with Python 3; only the standard library is required.
The manifest covers all bundle files except itself and retains its provenance.
"""

from __future__ import annotations

import base64
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import re


class Node:
    def __init__(self, tag: str, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list[Node | str] = []


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def convert(bundle: Path) -> str:
    document = Document()
    document.feed((bundle / "report.html").read_text())
    images = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path.relative_to(bundle).as_posix()
        for path in sorted((bundle / "figures").glob("*.png"))
    }

    def render(node):
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        tag = node.tag
        if tag in {"head", "style", "script"}:
            return ""
        if tag == "img":
            source = node.attrs["src"]
            if source.startswith("data:image/png;base64,"):
                digest = hashlib.sha256(base64.b64decode(source.split(",", 1)[1])).hexdigest()
                source = images[digest]
            return f"\n\n![{node.attrs.get('alt', '')}]({source})\n\n"
        if tag == "table":
            def rows(item):
                if isinstance(item, str):
                    return []
                if item.tag == "tr":
                    return [[render(cell).strip().replace("|", "\\|") for cell in item.children if isinstance(cell, Node) and cell.tag in {"th", "td"}]]
                return [row for child in item.children for row in rows(child)]
            values = rows(node)
            lines = ["| " + " | ".join(row) + " |" for row in values]
            lines.insert(1, "| " + " | ".join(["---"] * len(values[0])) + " |")
            return "\n\n" + "\n".join(lines) + "\n\n"
        if tag in {"ul", "ol"}:
            items = [child for child in node.children if isinstance(child, Node) and child.tag == "li"]
            return "\n\n" + "\n".join((f"{index}. " if tag == "ol" else "- ") + render(item).strip() for index, item in enumerate(items, 1)) + "\n\n"
        content = "".join(render(child) for child in node.children)
        if tag in {"h1", "h2", "h3", "h4"}:
            return "\n\n" + "#" * int(tag[1]) + " " + content.strip() + "\n\n"
        if tag == "strong":
            return "**" + content + "**"
        if tag in {"em", "figcaption"}:
            return "\n\n*" + content.strip() + "*\n\n" if tag == "figcaption" else "*" + content + "*"
        if tag == "code":
            return "`" + content + "`"
        if tag == "a":
            return f"[{content}]({node.attrs['href']})"
        if tag == "br":
            return "\n\n"
        if tag == "summary":
            return "\n\n### " + content.strip() + "\n\n"
        if tag in {"p", "div", "footer", "figure", "details"}:
            return "\n\n" + content.strip() + "\n\n"
        return content

    result = render(document.root)
    result = re.sub(r"\n[ \t]+", "\n", result)
    return re.sub(r"\n{3,}", "\n\n", result).strip() + "\n"


def main():
    bundle = Path(__file__).resolve().parents[1]
    (bundle / "report.md").write_text(convert(bundle))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = [
        {
            "path": path.relative_to(bundle).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path != manifest_path
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Converted report.md; manifest covers {len(manifest['files'])} files")


if __name__ == "__main__":
    main()
