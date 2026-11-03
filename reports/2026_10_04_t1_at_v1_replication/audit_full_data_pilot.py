"""Read-only numerical audit of the full-data calibration pilot; writes a receipt."""
import json
from types import SimpleNamespace
import numpy as np
from full_data_calibration import OUT,ARMS,FullCalibration,digest,serial
from full_data_localization import SCANS,CASES
from subset_positions import enable_research_model
from render_leave_one_satellite_out import check_stationarity


def main():
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    rows=[]
    for scan in SCANS:
        cal=FullCalibration(scan)
        assert not cal.record['heldout_original_rows']
        inputs={}
        for case in CASES:
            source=OUT/scan/f'{case}-input.npz'
            result=json.loads((OUT/scan/f'{case}-position.json').read_text())
            assert digest(source)==result['input_sha256']
            with np.load(source) as z:data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
            inputs[case]=data
            for arm in ARMS:
                saved=result['arms'][arm];best=saved['best']
                obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
                obj.center=result['input_metadata']['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
                obj.likelihood.features=obj.features;obj.base.deadline=float('inf')
                obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
                obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
                if arm=='zero-c':obj.bounds[-1]=(0.,0.)
                score,kkt=check_stationarity(obj,best,4.)
                assert abs(score-saved['objective'])<1e-7
                assert abs(kkt-best['kkt_residual'])<1e-7
                assert (kkt<=1e-3)==saved['converged']
                assert np.linalg.norm(best['point_km'])<=4.+1e-7
                assert max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
                rows.append(dict(scan=scan,case=case,arm=arm,score_error=score-saved['objective'],
                                 kkt=kkt,converged=saved['converged']))
        a,b=inputs['fold-control'],inputs['full-fixed-members']
        for key in ('times','rf','receiver','channel','group','owners','original_rows','numbers','position','velocity'):
            np.testing.assert_array_equal(getattr(a,key),getattr(b,key))
        np.testing.assert_allclose(a.measured+a.fixed_receiver_hz,b.measured+b.fixed_receiver_hz,atol=1e-7,rtol=0)
    receipt=dict(status='passed',position_cases=len(rows),converged=sum(r['converged'] for r in rows),
                 full_calibration_row_inventories_verified=True,matched_raw_observations_verified=True,
                 rf_arms_share_case_inputs=True,score_and_kkt_reconstructed=True,rows=rows)
    (OUT/'audit.json').write_text(json.dumps(receipt,default=serial,indent=2))
    print(json.dumps(receipt,default=serial))


if __name__=='__main__':main()
