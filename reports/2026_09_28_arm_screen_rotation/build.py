"""Build the screen-only rotation experiment using the frozen CZT builder."""
import argparse
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_28_arm_conditioned_czt/build.py'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--arm',action='store_true')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('frozen_czt_build',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.HERE=HERE
    module.BASELINE=Path('/var/tmp/leo-host-conditioned-czt-v2')
    module.build(args.output.resolve(),args.arm,args.sanitize)
