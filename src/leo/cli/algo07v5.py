"""Run or resume a pinned ALGO07v5 job with explicit policies."""

from leo.cli.algo07v4 import main as native_main
from leo.cli.algo07v4 import worker as native_worker


def worker(args):
    from leo.analysis.localization_v5.control_reuse import ControlReuseFailure
    from leo.analysis.localization_v5.joint_schedule import JointScheduleFailure
    from leo.cli.algo07v3 import write
    from leo.operations.localization_v5_job import execute

    try:
        return native_worker(args, _execute=execute)
    except (ControlReuseFailure, JointScheduleFailure) as error:
        write(args.outcome, dict(status='failed', error=f'{type(error).__name__}: {error}'))
        return 1


def main():
    from leo.operations.localization_v5_job import validate_request

    return native_main(_module="leo.cli.algo07v5", _worker=worker,
                       _validator=validate_request, _description=__doc__)


if __name__ == "__main__":
    raise SystemExit(main())
