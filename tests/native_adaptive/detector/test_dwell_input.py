from pathlib import Path
import subprocess


def test_ci16_input_prefix_exactness(tmp_path):
    root=Path(__file__).resolve().parents[3]
    binary=tmp_path/'test-dwell-input'
    subprocess.run(['cc','-std=c11','-O3','-fno-fast-math','-Wall','-Wextra','-Werror',
                    '-I'+str(root/'native/adaptive/detector'),str(Path(__file__).with_suffix('.c')),
                    '-lm','-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=15)
