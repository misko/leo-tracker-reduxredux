"""RF-endpoint line profiles on common full native evidence; no GPS."""
from pathlib import Path
import numpy as np
import mechanism as m
from probe_algo03_feasible_recovery import gate_slacks

OUT=Path(__file__).resolve().parents[1]


def main():
    protocol=dict(source_sha256=m.sha(Path(__file__)),cases=['DS23-0259','DS23-0353'],
                  lines=['graph_to_ordinary_native','ordinary_native_to_previous_final'],
                  points_per_line=11,phase_rounds=5,fixed_full_native_observation_mask=True,
                  objective='squared p.residual, actual ordinary fitting loss',
                  scope='posthoc RF-endpoint interpolation, not a regional/global search or GPS-selected line',no_GPS=True)
    path=OUT/'lines_protocol.json'
    if path.exists():assert m.read(path)==protocol
    else:m.write(path,protocol)
    rows=[]
    for case in protocol['cases']:
        parent,kind,fragments,record=m.load(case);full=m.append(parent,fragments)
        native=m.read(m.FROZEN/'raw'/case/'native'/(case+'.json'))['methods']['persistent5s']['arms']
        for arm in m.ARMS:
            pairs=[('graph_to_ordinary_native',record['ordinary_graph']['arms'][arm],native[arm])]
            if case=='DS23-0353':pairs.append(('ordinary_native_to_previous_final',native[arm],record['final']['arms'][arm]))
            for name,start,stop in pairs:
                for t in np.linspace(0,1,11):
                    x=(1-t)*np.array(start['endpoint_east_north_km'])+t*np.array(stop['endpoint_east_north_km'])
                    ref=np.asarray(native[arm]['phase_reference'])
                    for _ in range(5):
                        p=m.exp.paths.build(full,kind,arm,ref)
                        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                        change=float(np.max(abs(phase-ref)));ref=phase
                    r=p.residual(x);g=gate_slacks(p,x,full['entries']);calc=p.calculate(x)
                    rows.append(dict(case=case,arm=arm,line=name,fraction=float(t),position_east_north_km=x,
                                     actual_fit_loss=float(r@r),negative_twice_elbo=calc['negative_twice_elbo'],
                                     phase_change_s=change,minimum_gate_slack=min(g.values()),
                                     failing_gates={k:v for k,v in g.items() if v<0}))
    m.write(OUT/'common_mask_lines.json',dict(protocol=protocol,rows=rows))
    print('Scored',len(rows),'phase-refreshed common-mask RF positions.')


if __name__=='__main__':main()
