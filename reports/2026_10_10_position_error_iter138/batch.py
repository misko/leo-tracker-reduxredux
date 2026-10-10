"""Same serial twelve-member policy, with distinct successor result paths."""

from run import HERE, implementation


def main():
    original = implementation.module(
        "batch136_for138", HERE.parent / "2026_10_10_position_error_iter136/batch.py"
    )
    original.HERE = HERE
    original.main()


if __name__ == "__main__":
    main()
