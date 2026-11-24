"""Use each externally enrolled original legacy member's exact prepared map."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))


def map_kinds(plan):
    modes = {}
    for row in plan["members"]:
        kind, pin = row["map_kind"], row["map_sha256"]
        if (kind not in {"literal", "exception", "ordinary"} or (kind == "ordinary") != (pin is None)
                or bool(row["map"]) != (pin is not None) or pin in modes):
            raise ValueError("The signed plan must unambiguously bind each map's reader")
        if pin is not None:
            modes[pin] = kind
    return modes


def mapped_codec(plan):
    from types import SimpleNamespace

    from reports.ALGO08.v3 import legacy_block_multi as multi, legacy_block_seek as literal

    maps = map_kinds(plan)

    def select(reader, chunk, data, pin, binary):
        if maps[pin] == "literal":
            return literal.Selective(reader, chunk, data, pin, binary)
        member = multi.Selective(reader, chunk, data, pin, binary)
        native = member.counts.report

        def counts():
            return native() | dict(exception_spans=member.requests["exception_spans"],
                exception_bytes=member.requests["exception_bytes"],
                exceptional_origin_replays=binary.legacy_origin_replays(member.context),
                exceptional_owner_configured=int(member.owner is not None))

        member.counts.report = counts
        return member

    return SimpleNamespace(MAX_MAP=multi.MAX_SIDECAR, Selective=select)


def run(args):
    import empty_bootstrap as boot
    from legacy_block_raw_entry import run as raw

    with ExitStack() as stack:
        installed = boot.load_runtime

        def load(*call, **kwargs):
            result = installed(*call, **kwargs)
            with patch.object(sys, "path", [*sys.path, str(boot.RELEASE / "src"), str(ROOT)]):
                from reports.ALGO08.v3 import legacy_block_input as port

            plain = port.binding

            @contextmanager
            def bind(boot, plan, folder, binary, audit, *, codec=None):
                if codec is not None:
                    raise ValueError("The sealed all-member plan must choose its own map kinds")
                with plain(boot, plan, folder, binary, audit, codec=mapped_codec(plan)):
                    yield

            stack.enter_context(patch.object(port, "binding", bind))
            return result

        stack.enter_context(patch.object(boot, "load_runtime", load))
        return raw(args)


if __name__ == "__main__":
    from legacy_block_raw_entry import parser

    run(parser().parse_args())
