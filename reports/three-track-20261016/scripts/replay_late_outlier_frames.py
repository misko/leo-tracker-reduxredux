from pathlib import Path
code=Path('/tmp/replay_late_cfo.py').read_text()
code=code.replace('chosen=rows[[0,len(rows)//2,-1]]', 'chosen=np.array([2728,2753,2759])')
# Resolve adjacent recorded observations from the saved audit, rather than assuming rows.
code=code.replace('chosen=np.array([2728,2753,2759])', "chosen=np.array([p['row'] for p in json.loads((root/'three_track_exception_audit.json').read_text())['points'] if p['track']=='late_ch2' and any(abs(p['time_s']-t)<1e-6 for t in [171.092824376,172.512839053,172.86884265])])")
extra='''
from leo.analysis.starlink.glrt_refinement_prototype import continuous_peak, _conditioned_correlation_workspace, StarlinkEdge
original_continuous_glrt_score=continuous_glrt_score
def continuous_glrt_score(samples,fs,*,anchor,offset,conditioning_cfo_hz,edge):
    score,details=original_continuous_glrt_score(samples,fs,anchor=anchor,offset=offset,conditioning_cfo_hz=conditioning_cfo_hz,edge=edge)
    symbols=np.arange(2,66)
    workspace=_conditioned_correlation_workspace(np.asarray(samples,dtype=complex),fs,anchor,conditioning_cfo_hz,selected_symbols=symbols,fractional_epoch_offset_samples=offset,edge=StarlinkEdge(edge))
    selected=workspace.select(symbols)
    full=details['exact']['frequency_hz']
    frame_peaks=[continuous_peak(x[None,:],selected.symbol_step_s) for x in selected.values]
    differences=np.array([float(circular(x.frequency_hz-full)) for x in frame_peaks])
    splits={}
    for name,values in [('first_frames',selected.values[:len(selected.values)//2]),('last_frames',selected.values[len(selected.values)//2:]),('first_symbols',selected.values[:,:32]),('last_symbols',selected.values[:,32:])]:
        peak=continuous_peak(values,selected.symbol_step_s)
        splits[name]=dict(delta_from_full_hz=float(circular(peak.frequency_hz-full)),score=float(peak.score))
    details['frame_diagnostic']=dict(frame_count=len(differences),frame_offsets_from_full_hz=differences.tolist(),median_frame_offset_hz=float(np.median(differences)),frame_offset_std_hz=float(np.std(differences)),split_peaks=splits)
    return score,details
'''
code=code.replace("store=FastScanStore('/srv/bulk/leo')",extra+"\nstore=FastScanStore('/srv/bulk/leo')")
code=code.replace("'late_cfo_raw_replay.json'","'late_outlier_frame_replay.json'")
exec(compile(code,__file__,'exec'))
