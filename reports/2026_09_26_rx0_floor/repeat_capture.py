"""One operator-authorized capture using the installed runner and a unique ID.

Only the session/seed identity is salted; real UTC and slot configuration remain
unchanged. A separate summary directory preserves every repeated slot's evidence.
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

RUNNER = Path('/opt/leo-v058-adaptive/1e7bebed663bc2178a1b91af5b98eb55bc97dc84/scripts/run_v052_adaptive_live.py')


def main():
    nonce = sys.argv[1]
    spec = importlib.util.spec_from_file_location('installed_capture', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.campaign_configuration

    def configuration(epoch, serial, rate):
        ordinal, rate, edge, frequencies, identity = original(epoch, serial, rate)
        identity = hashlib.sha256(identity + b'\0coax-repair-repeat\0' + nonce.encode()).digest()
        print('SESSION scan-fw-' + identity[:8].hex(), flush=True)
        return ordinal, rate, edge, frequencies, identity

    module.campaign_configuration = configuration
    sys.argv = [str(RUNNER), *sys.argv[2:]]
    return module.main()


if __name__ == '__main__':
    raise SystemExit(main())
