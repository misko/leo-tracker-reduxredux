from pathlib import Path
from types import SimpleNamespace

from algo07v3_inclusion_oracle import original_callable


def original_run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    # This imitates an original audit's operational byte receipt only.
    hashes = {}
    hashes[str(args.output)] = args.output.read_bytes()
    datum = read(args.source)  # noqa: F821 - original module IO replaced explicitly
    answer = dict(value=datum["value"] * 2, source_hashes=hashes)
    print(answer)
    write(args.output, answer)  # noqa: F821


def test_external_adapter_preserves_arithmetic_replacing_only_explicit_io():
    captured = {}
    run = original_callable(
        original_run,
        read=lambda _: dict(value=7),
        write=lambda path, value: captured.update({path: value}),
    )
    path = Path("/path-that-must-not-be-created-v3-oracle")
    assert not path.exists()
    run(SimpleNamespace(output=path, source=None))
    assert not path.exists()
    assert captured == {path: dict(value=14, source_hashes={})}
