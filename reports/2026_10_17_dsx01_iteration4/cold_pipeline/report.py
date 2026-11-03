"""Read-only report/seal of one faithful original cold temporal-half pilot."""
import csv
import json
import math
from pathlib import Path
import numpy as np
from derive import digest

HERE=Path(__file__).resolve().parent
ATTEMPT=HERE/'S03-early_to_late'
ROOT=HERE.parents[2]


def main():
    r=json.loads((ATTEMPT/'evaluation-replay.json').read_text())
    d=json.loads((ATTEMPT/'derivation.json').read_text())
    support=json.loads((ATTEMPT/'held_diagnostics.json').read_text())
    terminal=json.loads((ATTEMPT/'output'/'terminal.json').read_text())
    assert r['training_audit']['accepted'] and r['exact_prediction_and_evaluation_arrays_replayed']
    station_path=ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station=json.loads(station_path.read_text())
    source=json.loads((ATTEMPT/'training-input.json').read_text())['source']
    reference=None
    if (source['radio_id']==station['radio_serial'] and
        station['valid_from_utc_ns']<=d['origin_utc_ns']<station['valid_until_utc_ns']):
        lat,lon=map(math.radians,[r['position']['latitude_deg'],r['position']['longitude_deg']])
        a,b=map(math.radians,[station['latitude_deg'],station['longitude_deg']])
        h=math.sin((a-lat)/2)**2+math.cos(a)*math.cos(lat)*math.sin((b-lon)/2)**2
        reference=dict(distance_km=2*6371.0088*math.asin(math.sqrt(h)),
            sha256=digest(station_path.read_bytes()),revision=station['revision'],
            binding='Matching source radio serial and prospective validity interval',
            qualification=station['position_evidence'],usage='Measurement only, after training and prediction freeze')
    summary=dict(source_id='S03',direction='early_to_late',whole_pipeline_runs=1,
        maximum_whole_run_seconds=480,actual_pipeline_seconds=terminal['elapsed_seconds'],
        exact_original_policy=terminal['source_generation_policy'],strict_training_audit=r['training_audit'],
        train=r['train'],held=r['held'],windows=r['windows'],
        training_selected_ids=r['training_selected_numbers'],
        training_regional_bank_count=r['training_full_regional_candidates'],
        learned_band_offsets_hz=r['learned_band_offsets_hz'],position=r['position'],configured_reference=reference,
        clock_transport=r['clock_transport'],cost=r['cost'],visibility_frequency_diagnostics=support,
        cut_s=d['cut_s'],old_median_timestamp_s=r['original_median_timestamp_s'],
        derived_input_sha256=d['derived_input_sha256'],causal_tle=d['causal_tle'],
        tests=dict(prelaunch_unit_tests=4,final_unit_tests=6,
            actual_held_cfo_score_gate_invariance=True,exact_prediction_and_metric_replay=True),
        qualification=r['qualification'],
        c_control='Original production source generation is fitted-c throughout; no whole-pipeline c0 comparison or localization advantage is claimed. Any future downstream matchedc0 is conditional.')
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'window-coverage.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['region_id','train_observations','train_associated','held_observations','held_associated'])
        for w in r['windows']:writer.writerow([w['region_id'],w['train']['observations'],w['train']['associated'],w['held']['observations'],w['held']['associated']])
    t,h=r['train'],r['held'];st,sh=support['train'],support['held'];cost=r['cost']
    lines=['# Faithful original S03 cold-half baseline','',
        f"The original production pipeline passes strict training admission but associates only {h['associated']}/{h['observations']} held observations ({100*h['associated']/h['observations']:.2f}%), "
        f"versus {t['associated']}/{t['observations']} training observations ({100*t['associated']/t['observations']:.2f}%). "
        'The two held requested windows retain 2/84 observations. This is negative prediction evidence from one source/fold, not a result on new recording positions.','',
        f"One unmodified `leo.cli.shared_fast_position.run(...maximum_seconds=480,tle_root=...)` completed in {terminal['elapsed_seconds']:.3f} seconds. "
        f"Policy: `{terminal['source_generation_policy']}`. Selected source `{terminal['selection']['source']}` has strict KKT {r['training_audit']['stationarity']:.9g}; "
        f"training objective {r['training_audit']['objective']:.6f} and frequency NLL {r['training_audit']['likelihood_nll']:.6f}. "
        'No local-segment/v6 replacement, saved full-fit position/calibration/bank, production write, or RF collection was used.','',
        f"The split uses complete probe intervals around the immutable capture-counter midpoint ({d['cut_s']:.7f} s). "
        f"It retains {d['training_probe_groups']} probes and excludes {d['held_probe_groups']} held probes; {d['boundary_probe_groups']} straddle the cut. "
        'Every candidate measurement in an excluded probe is removed before preparation, bootstrap or discovery. Original clock anchor, delivery clocks, counter/RF and parent provenance authorities remain fixed. '
        'Four prelaunch tests and a real-source perturbation of every excluded CFO, score and gate gave identical training bytes and preparation evidence. '
        f"Training digest: `{d['derived_input_sha256']}`. All 2006 train IDs occur in the frozen original 3988-observation S03 cohort. "
        f"The previous median-observation split used {r['original_median_timestamp_s']:.9f} s and 1994/1994 observations; it is a different protocol. Historical 63/66-target-probe exclusions are also different. Holding the complete timing authority is metadata conditioning, not access to held CFO. No held CFO enters a seed, calibration or discovery. ", '',
        f"The public latest-before-origin-minus-505-seconds archive policy selects **{d['causal_tle']['provider']}**, `{d['causal_tle']['sha256']}`, collected at {d['causal_tle']['collected_utc_ns']} UTC ns. "
        f"A fresh TRAIN-only regional bank has {r['training_full_regional_candidates']} candidates; discovery selects {len(r['training_selected_numbers'])} IDs. "
        'Only these selected IDs are propagated for full-domain evaluation. The full prediction bank exactly reproduces its training overlap; every held row receives finite predictions. '
        'This experiment is training-discovered, whereas previous restricted prototypes were conditioned on the full-recording selected bank.','',
        f"The learned high-minus-low offsets are {r['learned_band_offsets_hz'][0]:.3f} and {r['learned_band_offsets_hz'][1]:.3f} Hz. "
        'The original calibration class is present; offsets are not forced to zero. Residual-clock nodes 0,30,…,150 s extend to 300 s with the boundary residual held constant. '
        'Every learned affine term, slope and RF dependence remains unchanged; no new held knot is fitted. '
        f"Complete training correction closes within {r['clock_transport']['training_closure_max_error_hz']:.3g} Hz, and training frequency NLL replays exactly. "
        'Constant residual-clock extrapolation is a declared prediction assumption, not evidence that the hardware clock remains constant.','',
        '| Evaluation cohort | Associated | Assigned RMS Hz | Conditional CFO NLL |',
        '|---|---:|---:|---:|',
        f"| Train | {t['associated']}/{t['observations']} | {t['associated_rms_hz']:.2f} | {t['conditional_cfo_nll']:.2f} |",
        f"| Held | {h['associated']}/{h['observations']} | {h['associated_rms_hz']:.2f} | {h['conditional_cfo_nll']:.2f} |",'',
        '| Fixed requested window | Train associated | Held associated |',
        '|---|---:|---:|']
    for w in r['windows']:lines.append(f"| {w['region_id']} | {w['train']['associated']}/{w['train']['observations']} | {w['held']['associated']}/{w['held']['observations']} |")
    lines+=['',
        f"All {support['selected_ids']} selected IDs have positive model visibility in both halves. No held row has zero visible selected candidates; visible q mass is 1.6 throughout. "
        f"All {support['ids_with_assigned_train_support']} IDs with assigned training support remain visible held. "
        f"Nearest circular residual to any visible selected prediction has median {st['nearest_visible_residual_hz']['median']:.2f} Hz train and {sh['nearest_visible_residual_hz']['median']:.2f} Hz held; "
        f"{st['nearest_visible_within_375_hz']}/{t['observations']} train versus {sh['nearest_visible_within_375_hz']}/{h['observations']} held lie within 375 Hz. "
        'Thus empty visibility or an uncovered propagation interval does not explain the failure. Positive visibility does not prove that the actual emitter is among the selected IDs. '
        'The audit cannot uniquely separate missing correct identities from timing/calibration extrapolation. Assigned labels are model hypotheses, not verified identities. Per-ID and 30-second-bin diagnostics are saved without any refit.','']
    if reference:lines.append(f"The fitted location is ({r['position']['latitude_deg']:.6f}, {r['position']['longitude_deg']:.6f}), {reference['distance_km']:.3f} km from the matching configured station reference. The reference is uncertain, unsurveyed and used only after prediction freeze. Frequency fit does not establish localization accuracy.\n")
    lines+=[f"Cost: {cost['actual_a_b_shared_objective_calls']} exact A/B/shared objective calls across {cost['a_b_shared_optimizer_calls']} fits, plus {cost['prescreen_objective_calls']} prescreens. "
        f"Discovery has {cost['discovery_points']} points/{cost['discovery_fit_receipts']} fit receipts ({cost['discovery_converged_fits']} converged), {cost['discovery_reported_solver_evaluations']} reported solver evaluations and {cost['discovery_summed_fit_elapsed_seconds']:.3f} summed fit seconds. "
        f"There are {cost['shape_attempts']} shape attempts and {cost['bootstrap_stage_count']} bootstrap stages. Discovery/shape/bootstrap counters are separate; the terminal's `cost_exact=true` covers its stated A/B/shared scope, not every algorithm call. "
        'All counted fits respect their declared 2000-call/20-second source or 5000-call/65-second shared allocation. The original whole policy reserves discovery 240 seconds, bank 180, shape 20 per view, bootstrap 5 per stage, and 130 seconds for finals under the 480-second outer cap. All actual stage receipts remain available; no unfinished stage or retry occurred.','',
        'The original pipeline fits c during source generation. There is no whole-pipeline c=0 comparison here, and no fitted-c localization advantage is claimed. A later matched downstream c=0 sensitivity would be conditional on this fitted-c discovery. The earlier zero-contrast stress tests and donor/grid prototypes remain separately labeled.','',
        'Six final component tests pass. A no-fit independent replay exactly reproduces saved predictions, associations, residuals, strict endpoint metrics, prior/clock closure and separately scoped cost bounds. Raw attempt receipts remain immutable.','',
        '![Training versus held coverage](cold-coverage.png)','',
        'Entrypoints: `run_original.py --run` creates the one immutable attempt and refuses reuse; `evaluate.py` freezes predictions before loading held CFO for scoring; `evaluate.py --verify` audits saved output without fitting; `support_diagnostics.py` is a fixed-prediction visibility/frequency audit. No additional pipeline run is authorized by this report.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    plot(r,support)
    files=[p for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json']
    (HERE/'manifest.json').write_text(json.dumps(dict(files=[dict(path=str(p.relative_to(HERE)),sha256=digest(p.read_bytes())) for p in sorted(files)]),indent=2)+'\n')
    print(json.dumps(dict(sealed=True,files=len(files),train=t['associated'],held=h['associated'],reference_km=None if reference is None else reference['distance_km'])))


def plot(r,support):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,3.7))
    a,b=r['train'],r['held']
    axes[0].bar(['Train','Held'],[100*a['associated']/a['observations'],100*b['associated']/b['observations']],color=['#3979b2','#df8c33'])
    axes[0].set_ylim(0,100);axes[0].set_ylabel('Original winners associated (%)')
    axes[0].set_title(f"S03: {a['observations']} train / {b['observations']} held")
    for label,color in [('train','#3979b2'),('held','#df8c33')]:
        bins=[v for v in support['time_bins'] if v[label]['observations']]
        axes[1].plot([(v['start_s']+v['end_s'])/2 for v in bins],
            [100*v[label]['associated']/v[label]['observations'] for v in bins],'o-',color=color,label=label)
    axes[1].axvline(r['cut_s'],color='#777777',linestyle='--');axes[1].set_xlim(0,300);axes[1].set_ylim(0,100)
    axes[1].set_xlabel('Seconds from session counter origin');axes[1].set_ylabel('Associated (%) in 30 s bin');axes[1].legend()
    fig.tight_layout();fig.savefig(HERE/'cold-coverage.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
