"""Run the unmodified signed-context nomination policy with score receipts."""

import sys

from tools.pipeline_eval.qualification.nomination_memory_worker import worker

if __name__ == "__main__":
    worker(*sys.argv[1:], stock=True)
