"""Install an optional, strict regional catalogue projection in the phase-release receiver."""

from pathlib import Path

from .. import cavity_runtime
from .full_receiver_comparison import sha

ELEMENTS = "leo/analysis/localization_v3/elements.py"
INPUTS = "leo/operations/localization_v3_inputs.py"
LIFETIME = "tools/pipeline_eval/variants/direct_lifetime_kernels.py"
APPLICATION = "leo/application/localization_v3.py"
BASE = "phase-release"


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("the published phase-release source has moved the exact adapter port")
    return source.replace(old, new)


def parser(source, candidate):
    source = replace(
        source,
        "from collections import OrderedDict\n",
        "from collections import OrderedDict\nfrom hashlib import sha256\n",
    )
    source = replace(
        source,
        "        self._records = OrderedDict()",
        "        self._records = OrderedDict()\n"
        "        self.constructed = self.offered = self.planned = 0\n"
        "        self._validated = set()",
    )
    source = replace(
        source,
        "    def __call__(self, text):",
        f"    screened = {candidate!r}\n\n"
        "    def __call__(self, text, *, selected=None):\n"
        "        if self.screened:\n"
        "            fingerprint = sha256(text.encode()).digest()\n"
        "            narrow = selected is not None and fingerprint in self._validated\n"
        "        else:\n"
        "            narrow = False",
    )
    source = replace(
        source,
        "        for record in records:\n            try:",
        "        self.offered += len(records)\n"
        "        if narrow:\n"
        "            self.planned += 1\n"
        "            rows = tuple(r for r in records if r.satellite_number in selected)\n"
        "        else:\n"
        "            rows = records\n"
        "        for record in rows:\n            try:",
    )
    return replace(
        source,
        "        return ElementSetCatalogue(tuple(names), tuple(numbers), tuple(satellites))",
        "        self.constructed += len(satellites)\n"
        "        if (self.screened and not narrow and len(self._validated) < 512\n"
        "                and all(number == r.satellite_number\n"
        "                        for number, r in zip(numbers, records, strict=True))):\n"
        "            self._validated.add(fingerprint)\n"
        "        return ElementSetCatalogue(tuple(names), tuple(numbers), tuple(satellites))",
    )


def inputs(source):
    source = replace(
        source,
        "\ndef prepare_recovery_catalogue",
        """
def screened_catalogue(reader, snapshot, parser, numbers):
    text = reader.read(snapshot)
    if getattr(parser, 'screened', False):
        return parser(text, selected=numbers)
    return parser(text)


def prepare_recovery_catalogue""",
    )
    for loop, ids in (
        ("    for snapshot in unique.values():", "regional"),
        ("    for snapshot in sorted(unique.values()):", "regional"),
        ("    for snapshot in snapshots:", "lookup"),
    ):
        old = "\n".join((loop, "        cat = element_parser(reader.read(snapshot))"))
        replacement = "\n".join(
            (loop, f"        cat = screened_catalogue(reader, snapshot, element_parser, {ids})")
        )
        if ids == "regional":
            replacement = "    regional = frozenset(map(int, elements))\n" + replacement
        source = replace(source, old, replacement)
    return source


def lifetime(source):
    source = replace(
        source,
        "    def consume(text):\n        catalogue = parser(text)",
        "    def consume(text, *, selected=None):\n"
        "        catalogue = parser(text) if selected is None else parser(text, selected=selected)",
    )
    return replace(
        source,
        "    try:\n        yield consume",
        """
    consume.screened = getattr(parser, 'screened', False)
    try:
        yield consume""",
    )


def application(source):
    return replace(
        source,
        """    return dict(status='inputs_prepared', tracks=prepared, sky=sky, noise=noise,
                phase_history=history, phase_forecast=forecast(history))""",
        """    prior = forecast(history)
    if own_parser:
        import json
        import sys
        from hashlib import sha256

        evidence = {k: v for k, v in sky.items() if k != 'bank'}
        complete = json.dumps([evidence, history, prior], sort_keys=True,
                              default=lambda value: value.tolist())
        print('catalogue-work ' + json.dumps(dict(
            evidence_sha256=sha256(complete.encode()).hexdigest(),
            offered=element_parser.offered, constructed=element_parser.constructed,
            projected_snapshots=element_parser.planned, **element_parser.statistics(),
        )), file=sys.stderr, flush=True)
    return dict(status='inputs_prepared', tracks=prepared, sky=sky, noise=noise,
                phase_history=history, phase_forecast=prior)""",
    )


def install(out, *, candidate=True):
    pinned = cavity_runtime.release_files(cavity_runtime.RELEASE, BASE)
    cavity_runtime.install(out, profile=BASE)
    edits = {ELEMENTS: lambda source: parser(source, candidate), APPLICATION: application}
    if candidate:
        edits.update({INPUTS: inputs, LIFETIME: lifetime})
    for relative, change in edits.items():
        file = out / relative
        bound = file.read_bytes()
        if bound != pinned[relative]:
            raise ValueError(f"unexpected original installed source at {relative}")
        replacement = change(bound.decode())
        compile(replacement, str(file), "exec")
        file.write_text(replacement)
    return {
        name: sha(out / name)
        for name in (
            *pinned,
            "__main__.py",
            "tools/__init__.py",
            "native/manifest.json",
            "native/native_bound.so",
            "projector.so",
        )
    }


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("path", type=Path)
    cli.add_argument("--stock", action="store_true")
    args = cli.parse_args()
    install(args.path, candidate=not args.stock)
