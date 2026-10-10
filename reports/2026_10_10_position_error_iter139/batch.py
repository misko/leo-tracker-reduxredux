"""Unchanged exclusive-claim serial launch policy."""

from run import HERE, implementation


def main():
    runner = implementation.module(
        "batch136_for139", HERE.parent / "2026_10_10_position_error_iter136/batch.py"
    )
    runner.HERE = HERE
    runner.main()


if __name__ == "__main__":
    main()
