"""Saved-IQ ARM runner for explicit uncomputed refinement fields.

The frozen transport runner is reused. Its oracle comparison considers only
computed quantities; skipped quantities stay JSON null, never fabricated zero.
An exact-oracle mismatch remains a mismatch and does not become a quality pass.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_28_arm_full_optimization/arm_run.py'
SKIPPED={'conditioned_cfo_hz','acquire_score','verify_score',
         'verify_control_score','conditioned_score'}


def run(build,oracle,output,repeats):
    spec=importlib.util.spec_from_file_location('frozen_arm_runner',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_loader=module.module
    def load(name,path):
        value=original_loader(name,path)
        if name=='full_compare':
            value.FLOAT_FIELDS=tuple(row for row in value.FLOAT_FIELDS if row[0] not in SKIPPED)
        return value
    module.module=load
    try:
        # Stage the explicitly named direct binary under the transport's fixed
        # name. Its bytes and unchanged receipt remain tied to the original build.
        binary=build/'probe_direct'
        original_receipt=json.loads((build/'build.json').read_text())
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=original_receipt['binary_sha256']['probe_direct']:
            raise ValueError('direct probe differs from build receipt')
        with tempfile.TemporaryDirectory(prefix='leo-direct-probe-') as temporary:
            staged=Path(temporary)
            shutil.copyfile(binary,staged/'probe')
            shutil.copyfile(build/'build.json',staged/'build.json')
            module.run(staged,oracle,output,repeats)
    finally:
        receipt=output/'run.json'
        if receipt.exists():
            data=json.loads(receipt.read_text())
            data['comparison_scope']='Only computed coarse/final fields; approximate outputs are not required to equal original refinement'
            data['uncomputed_fields_excluded']=sorted(SKIPPED)
            data['source_build']=str(build)
            data['source_probe_name']='probe_direct'
            data['adapter_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            data['frozen_runner_source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
            receipt.write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    a=p.parse_args();run(a.build.resolve(),a.oracle.resolve(),a.output.resolve(),a.repeats)
