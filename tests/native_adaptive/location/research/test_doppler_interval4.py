from pathlib import Path
import subprocess


def test_portable_interval_enclosure(tmp_path):
    root=Path(__file__).resolve().parents[4]
    binary=tmp_path/'test-doppler-interval4'
    subprocess.run(['g++','-std=c++17','-O3','-fno-fast-math','-Wall','-Wextra','-Werror',
                    '-I'+str(root/'native/adaptive/location'),str(Path(__file__).with_suffix('.cpp')),
                    '-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
