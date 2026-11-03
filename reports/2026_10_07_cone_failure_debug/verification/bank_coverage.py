"""Fixed own-state full-bank coverage diagnostic, no optimization or truth seed."""
import json
from dataclasses import replace
import numpy as np
from audit import HERE,PARENT,oracle,background,controls
from leo.analysis.regional_position_score import PositionObjective,predict_orbits,circular
from leo.contracts.regional_position import PositionScore,PositionObservations

OFFSETS=(0.,-1.,1.,-2.,2.,-4.,4.)

def main():
    out={'scope':'own fitted background position/clock fixed; selected shifts preserved; omitted common shift plus grid or absolute zero','offsets_s':OFFSETS,'match_threshold_hz':250.,'cases':[]}
    pairs_doc=json.loads((PARENT/'identity/paired_topone.json').read_text())
    for case in ('1939','2139'):
        doc,old,obs,prior,bank,cp,prefix=oracle.load(case)
        receipt=json.loads((PARENT/'paired_background'/f'{case}.json').read_text());selected=next(r for r in receipt['selections'] if r['option']=='background' and r['arm']=='fitted-c');v=np.asarray(selected['vector']);basin=selected['basin']
        assoc=cp.get(prefix+':'+basin+':association')['result'];cal=cp.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices']);baseline=np.asarray(cal['receiver_baseline_hz']);score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        pairs=np.array([[r['row0'],r['row1']] for r in pairs_doc['cases'][case]['100ns']['rows']]);obj=background.BackgroundObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,pairs=pairs,rho=receipt['rho'],eta=receipt['eta']);obj.evaluate(v)
        unknown=obj.last_background['common_background_probability'];clock=obj.design@v[2:7]+obj.baseline;physical=v[7]+obj.basis@v[8:]
        indices=pairs.ravel();pair_obs=PositionObservations(tuple(obs.window_ids[i] for i in indices),obs.times_s[indices],obs.measured_hz[indices],obs.rf_hz[indices],obs.receiver[indices],obs.channel[indices],obs.margin[indices])
        lookup={int(n):float(s) for n,s in zip(subset.numbers,physical)};kept=np.array([int(n) in lookup for n in bank.numbers]);omitted=~kept
        row={'case':case,'arm':'fitted-c','basin':basin,'vector_sha256':controls.vector_digest(v),'full_bank_count':len(bank.numbers),'selected_bank_count':len(subset.numbers),'pair_count':len(pairs),'unknown_pair_count_above_half':int(np.sum(unknown>.5)),'mean_unknown_pair_probability':float(unknown.mean()),'grids':[],'best_omitted_matches':[]}
        best=np.full(len(pairs),np.inf);best_number=np.zeros(len(pairs),int);best_shift=np.zeros(len(pairs));selected_score=None
        null_offsets=(-10000.,-5000.,5000.,10000.);null_best={offset:np.full(len(pairs),np.inf) for offset in null_offsets}
        for label,offset in [(f'common{offset:+g}',offset) for offset in OFFSETS]+[('absolute-zero',None)]:
            shifts=np.array([lookup.get(int(n),0. if offset is None else v[7]+offset) for n in bank.numbers]);prediction,visible,_,_=predict_orbits(bank,pair_obs,prior,v[:2],shifts,derivatives=False);prediction+=clock[indices,None]
            residual=circular(pair_obs.measured_hz[:,None]-prediction);paired_error=np.maximum(abs(residual[::2]),abs(residual[1::2]));paired_error[~(visible[::2]&visible[1::2])]=np.inf
            for null_offset in null_offsets:
                shifted=circular(residual+null_offset);error=np.maximum(abs(shifted[::2]),abs(shifted[1::2]));error[~(visible[::2]&visible[1::2])]=np.inf
                null_best[null_offset]=np.minimum(null_best[null_offset],np.min(error[:,omitted],axis=1))
            selected_scores=np.min(paired_error[:,kept],axis=1);omitted_scores=np.min(paired_error[:,omitted],axis=1);full_scores=np.minimum(selected_scores,omitted_scores)
            if selected_score is None:selected_score=selected_scores.copy()
            choose=np.argmin(paired_error[:,omitted],axis=1);numbers=bank.numbers[omitted][choose];trial_shifts=shifts[omitted][choose];improve=omitted_scores<best
            best[improve]=omitted_scores[improve];best_number[improve]=numbers[improve];best_shift[improve]=trial_shifts[improve]
            mask=unknown>.5
            row['grids'].append({'label':label,'selected_matches':int(np.sum(selected_scores<=250)),'omitted_matches':int(np.sum(omitted_scores<=250)),'full_matches':int(np.sum(full_scores<=250)),'unknown_selected_matches':int(np.sum(mask&(selected_scores<=250))),'unknown_omitted_matches':int(np.sum(mask&(omitted_scores<=250))),'unknown_full_matches':int(np.sum(mask&(full_scores<=250)))})
        unknown_mask=unknown>.5;new=(selected_score>250)&(best<=250)
        row.update(selected_matches=int(np.sum(selected_score<=250)),omitted_union_matches=int(np.sum(best<=250)),newly_explained_by_omitted=int(np.sum(new)),unknown_newly_explained_by_omitted=int(np.sum(new&unknown_mask)))
        row['common_cfo_shift_nulls']=[{'offset_hz':offset,'omitted_union_matches':int(np.sum(scores<=250)),'unknown_omitted_union_matches':int(np.sum((scores<=250)&unknown_mask))} for offset,scores in null_best.items()]
        unique,counts=np.unique(best_number[new],return_counts=True);row['new_match_id_count']=len(unique);row['largest_id_match_count']=int(counts.max(initial=0))
        for j in np.flatnonzero(new):row['best_omitted_matches'].append({'pair_index':int(j),'rows':pairs[j].tolist(),'number':int(best_number[j]),'shift_s':float(best_shift[j]),'max_residual_hz':float(best[j]),'previous_selected_max_residual_hz':float(selected_score[j]),'unknown_probability':float(unknown[j])})
        out['cases'].append(row)
    (HERE/'bank_coverage.json').write_text(json.dumps(out,indent=2,default=controls.encode));print(json.dumps(out,indent=2))

if __name__=='__main__':main()
