"""Run only the freshly built component tests, serially, without RF activity."""
import json
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a


def main():
    receipts = [HERE.parent/'2026_09_29_arm_compile_pack/builds'/v/'arm/build-receipt.json'
                for v in ('strict-lto', 'fine-local-v2', 'combined-v2', 'limited-complex-v2')]
    receipts += [HERE.parent/'2026_09_29_arm_fixed_fft/builds/arm-q15-v7/fixed-fft-build.json',
                 HERE.parent/'2026_09_29_arm_packed_cache/builds/arm-pack-q15-v2/build-receipt.json']
    destination = '/mnt/glrtbench/low-precision-units-'+str(int(time.time()))
    a.remote('mkdir '+destination)
    results = []
    for i, receipt in enumerate(receipts):
        metadata = json.loads(receipt.read_text())
        for name, digest in metadata['binaries'].items():
            if not name.startswith('test_'):
                continue
            binary = receipt.parent/name
            assert a.sha(binary) == digest
            remote = destination+'/'+str(i)+'-'+name
            a.upload(binary, remote)
            assert a.remote('sha256sum '+remote).split()[0] == digest
            stdout = a.remote(remote, timeout=120)
            results.append({'receipt': str(receipt.relative_to(HERE.parent)),
                            'receipt_sha256': a.sha(receipt), 'binary': name,
                            'binary_sha256': digest, 'stdout': stdout, 'passed': True})
            print(name, 'passed', flush=True)
    (HERE/'arm-units.json').write_text(json.dumps({'target': '192.168.1.15',
                    'radio_activity': False, 'results': results}, indent=2)+'\n')


if __name__ == '__main__':
    main()
