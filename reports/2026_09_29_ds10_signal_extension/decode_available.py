"""Consume checkpointed DS10 captures while the independent census progresses."""

import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, decode_one  # noqa: E402


def main():
    done, pending = set(), {}
    with ProcessPoolExecutor(max_workers=4) as pool:
        while True:
            available = sorted((OUT / "captures").glob("DS10-*.json"))
            for path in available:
                if path.stem in done or path.stem in pending.values():
                    continue
                if len(pending) >= 4:
                    break
                # Census writes one complete capture at a time. Retry an in-flight write.
                try:
                    capture = json.loads(path.read_text())
                except json.JSONDecodeError:
                    continue
                pending[pool.submit(decode_one, capture)] = path.stem
            if pending:
                completed, _ = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
                for future in completed:
                    unit = pending.pop(future)
                    print(json.dumps(future.result()), flush=True)
                    done.add(unit)
            else:
                time.sleep(2)
            if len(done) == 151:
                break


if __name__ == "__main__":
    main()
