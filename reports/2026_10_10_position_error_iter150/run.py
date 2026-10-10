"""Explicit fresh150 slice, inherited unchanged123 controller and budgets."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from transition import recovery_port

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'2026_10_10_position_error_iter148'

def main():
    sys.path.insert(0, str(PREVIOUS))
    spec = importlib.util.spec_from_file_location('wrapper148_for150', PREVIOUS/'run.py')
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--protocol', default=str(HERE/'protocol.json'))
    args, _ = parser.parse_known_args()
    wrapper.preflight(json.loads(Path(args.protocol).read_text()))
    source = wrapper.transformed_source((wrapper.PARENT/'run.py').read_text())
    old = 'recover=backend["recovered_region"],'
    if source.count(old) != 1:
        raise ValueError('123 recovery source shape changed')
    source = source.replace(old, 'recover=RECOVERY_PORT(backend, "fitted-c" if args.branch == "native" else "zero-c"),')
    environment = dict(__name__='run123_for150', __file__=str(wrapper.PARENT/'run.py'),
                       EXPERIMENT_HERE=HERE, continue_branch=wrapper.adapter().continue_branch,
                       RECOVERY_PORT=recovery_port)
    exec(compile(source, str(wrapper.PARENT/'run.py'), 'exec'), environment)
    environment['main']()

if __name__ == '__main__':
    main()
