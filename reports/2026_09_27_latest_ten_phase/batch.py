"""Replay each frozen scan as its metadata plan becomes available; one IQ reader."""
from pathlib import Path
import json,subprocess,sys,time

HERE=Path(__file__).resolve().parent
deadline=time.monotonic()+1200
for index in range(10):
    while True:
        if time.monotonic()>deadline:raise TimeoutError('Bounded replay scheduling exceeded 20 minutes')
        try:ready=len(json.loads((HERE/'plan.json').read_text())['scans'])>index
        except json.JSONDecodeError:ready=False
        if ready:break
        time.sleep(2)
    subprocess.run([sys.executable,str(HERE/'replay.py'),'--scan',str(index)],check=True)
