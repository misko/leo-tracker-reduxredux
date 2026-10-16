from pathlib import Path
source_code=Path('/tmp/replay_late_cfo.py').read_text()
source_code=source_code.replace("chosen=rows[[0,len(rows)//2,-1]]", "chosen=np.array(json.loads((root/'late_track_extension.json').read_text())['selected_rows'])")
source_code=source_code.replace("candidate=next(c for c in probe.candidates", "assert window.acquisition['sample_start']==probe.valid_start_counter;candidate=next(c for c in probe.candidates")
source_code=source_code.replace("assert len(out)==3", "assert len(out)==len(chosen)")
source_code=source_code.replace("'late_cfo_raw_replay.json'", "'extended_late_cfo_raw_replay.json'")
source_code=source_code.replace("print(json.dumps(rec),flush=True)", "print(json.dumps(dict(time_s=rec['time_s'],change_hz=rec['change_hz'])),flush=True)")
exec(compile(source_code,__file__,'exec'))
