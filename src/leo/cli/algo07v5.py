"""Run or resume ALGO07v5 with explicit zero-phase control reuse."""

from leo.cli.algo07v4 import main as native_main
from leo.cli.algo07v4 import worker as native_worker


def worker(args):
    from leo.operations.localization_v5_job import execute

    return native_worker(args, _execute=execute)


def main():
    from leo.operations.localization_v5_job import validate_request

    return native_main(_module="leo.cli.algo07v5", _worker=worker,
                       _validator=validate_request, _description=__doc__)


if __name__ == "__main__":
    raise SystemExit(main())
