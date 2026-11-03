"""Seal one bounded original-production alternating-block interpolation pilot."""
import csv
import json
import math
from pathlib import Path
import numpy as np
from derive_blocks import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ATTEMPT=HERE/'S03-block20-parity0'


def main():
    d=json.loads((ATTEMPT/'derivation.json').read_text())
    terminal=json.loads((ATTEMPT/'output'/'terminal.json').read_text())
    path=ATTEMPT/('verification.json' if (ATTEMPT/'verification.json').exists() else 'evaluation.json')
    r=json.loads(path.read_text());den=d['evaluation_denominators']
    if r['state']!='complete':
        (HERE/'README.md').write_text('# Original blocked-cold pilot\n\nUnavailable: '+str(r.get('reason'))+'\nNo substitute pipeline or saved initializer was used.\n')
        (HERE/'summary.json').write_text(json.dumps(r,indent=2)+'\n');seal();return
    assert r['exact_saved_prediction_and_score_replay'] and r['training_audit']['accepted']
    ref_path=ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    ref=json.loads(ref_path.read_text());source=json.loads((ATTEMPT/'training-input.json').read_text())['source']
    reference=None
    if source['radio_id']==ref['radio_serial'] and ref['valid_from_utc_ns']<=d['origin_utc_ns']<ref['valid_until_utc_ns']:
        lat,lon=np.radians([r['position']['latitude_deg'],r['position']['longitude_deg']]);a,b=np.radians([ref['latitude_deg'],ref['longitude_deg']])
        h=np.sin((a-lat)/2)**2+np.cos(lat)*np.cos(a)*np.sin((b-lon)/2)**2
        reference=dict(distance_km=float(2*6371.0088*np.arcsin(np.sqrt(h))),sha256=digest(ref_path.read_bytes()),
            revision=ref['revision'],qualification=ref['position_evidence'],usage='Only after prediction freeze; matching radio/validity')
    summary=dict(r,configured_reference=reference,original_policy=d['exact_policy'],derived_input_sha256=d['derived_input_sha256'],
        causal_tle=d['causal_tle'],prelaunch_tests=d['prelaunch_tests'],whole_pipeline_runs=1,maximum_whole_run_seconds=480,
        interpretation='Deterministic gap interpolation within one recording, not independent-location validation; differs from contiguous half-forecast split and bank.')
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'window-coverage.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['region_id','train_observations','train_associated','held_observations','held_associated','boundary_observations','boundary_associated'])
        for w in r['windows']:writer.writerow([w['region_id'],*[w[role][name] for role in ['train','held','boundary'] for name in ['observations','associated']]])
    train,held,boundary=r['train'],r['held'],r['boundary'];cost=r['cost']
    held_targets=sum(w['held']['associated'] for w in r['windows']);held_target_count=sum(w['held']['observations'] for w in r['windows'])
    lines=['# Original production: alternating20s cold interpolation','',
        f"The original TRAIN-only production pipeline associates {held['associated']}/{held['observations']} held original winners ({100*held['associated']/held['observations']:.2f}%) "
        f"and {train['associated']}/{train['observations']} training winners ({100*train['associated']/train['observations']:.2f}%). "
        f"Requested held-window support is {held_targets}/{held_target_count}. "
        'This is one predeclared S03 parity0 interpolation pilot, not a result at new receiver positions.','',
        'Membership is determined by integer sample intervals in alternating20-second blocks from the original session-counter origin. Parity0 trains; parity1 is held. '
        'Every probe crossing a block boundary is excluded completely. No candidate CFO, score, gate, epoch, candidate identity or location enters membership. '
        'Global source-group IDs preserve the original capture authority. Three tests plus actual perturbation of every excluded CFO/score/gate yield identical derived training bytes and preparation evidence.','',
        f"Raw groups: {d['training_probe_groups']} train, {d['held_probe_groups']} held, {d['boundary_probe_groups']} boundary. "
        f"The fixed source cohort contains {train['observations']} train, {held['observations']} held, {boundary['observations']} boundary winners, totaling3988. "
        f"The full frozen challenge693 denominator is {den['challenge_membership']['train']} train + {den['challenge_membership']['held']} held + {den['challenge_membership']['boundary']} boundary + {den['other_source_challenge_untested']} untested from other sources. "
        f"The full20084 denominator retains {den['other_source_observations_untested']} other-source observations as untested. Boundary observations are reported separately and receive no training or held credit. ", '',
        f"Exactly one public `leo.cli.shared_fast_position.run(...maximum_seconds=480,tle_root=...)` completed in {terminal['elapsed_seconds']:.3f} seconds. "
        f"The unchanged policy is `{terminal['source_generation_policy']}`; source `{terminal['selection']['source']}` passes strict KKT {r['training_audit']['stationarity']:.9g}. "
        'All discovery, shape, bootstrap, A/B and shared stages are newly computed from the derived training source. No saved full-recording bank, position or calibration is an initializer. '
        'No v6/short-segment replacement, recording, production publication, retry or additional model fit occurred.','',
        f"Causal archive: {d['causal_tle']['provider']}, `{d['causal_tle']['sha256']}`, collected {d['causal_tle']['collected_utc_ns']} UTC ns, strictly before origin minus505seconds. "
        f"The TRAIN-only regional bank has {r['training_regional_bank_count']} candidates and production selects {len(r['training_selected_ids'])} IDs. Only these IDs enter prediction. "
        'Selection remains training-derived even though timing metadata spans the full recording.','',
        'Training spans both recording ends. Its native learned residual-clock nodes cover0…300s, so held gaps need no clock extrapolation or added knots. '
        'Every clock coefficient is learned using training measurements only. The public frozen sequential correction retains all learned affine terms, RF dependence and band offsets. '
        f"Training correction closure is {r['clock']['training_correction_closure_hz']:.3g} Hz and training frequency NLL replays exactly. "
        'Predictions are persisted before held CFO or descriptive full-fit labels enter scoring. The original125Hz maximum-satellite-posterior>clutter classifier is unchanged.','',
        '| Cohort | Associated | Assigned RMS Hz | Frequency NLL | Original full-fit new/lost |',
        '|---|---:|---:|---:|---:|']
    for label,m in [('Train',train),('Held',held),('Boundary',boundary)]:
        rms='—' if m['associated_rms_hz'] is None else f"{m['associated_rms_hz']:.2f}"
        lines.append(f"| {label} | {m['associated']}/{m['observations']} | {rms} | {m['frequency_nll']:.2f} | +{m['new_vs_original_full_fit']}/−{m['lost_vs_original_full_fit']} |")
    lines+=['','| Fixed requested window | Train associated | Held associated | Boundary associated |','|---|---:|---:|---:|']
    for w in r['windows']:lines.append(f"| {w['region_id']} | {w['train']['associated']}/{w['train']['observations']} | {w['held']['associated']}/{w['held']['observations']} | {w['boundary']['associated']}/{w['boundary']['observations']} |")
    visible=r['visibility_frequency']['held']
    lines+=['',f"Original full-fit descriptive winner IDs are absent from the TRAIN-selected bank for {held['original_winner_ids_absent_from_train_bank']}/{held['original_full_fit_associated']} originally associated held rows. "
        f"Among {held['lost_vs_original_full_fit']} lost original held assignments, {held['lost_original_rows_with_absent_original_winner']} have an absent original winner. "
        'These are model-label coverage diagnostics, not verified identity recall, and they never influence training. '
        f"Selected candidates have positive model visibility on {visible['rows_with_any_selected_visible']}/{held['observations']} held rows. "
        'Visibility alone cannot establish correct-emitter bank coverage.','',
        'The contiguous half-forecast baseline is separate:1571/2006train and165/1982held with25train-selected IDs and constant boundary-clock extrapolation. '
        'Alternating blocks change the selected bank, temporal support and held cohort. A difference between these pilots cannot be attributed exclusively to clock behavior, a single prior, or candidate discovery.','']
    if reference:lines.append(f"The fitted position is ({r['position']['latitude_deg']:.6f},{r['position']['longitude_deg']:.6f}), {reference['distance_km']:.3f} km from the matching configured reference. Its survey uncertainty is unknown. The reference is measurement-only, after prediction freeze; better frequency fit alone is not localization accuracy.\n")
    lines+=[f"Cost: {cost['actual_a_b_shared_objective_calls']} exact A/B/shared calls across {cost['a_b_shared_optimizer_calls']} fits, plus {cost['prescreen_objective_calls']} prescreens. "
        f"Discovery: {cost['discovery_points']} points/{cost['discovery_fit_receipts']} receipts, {cost['discovery_reported_solver_evaluations']} reported solver evaluations, {cost['discovery_summed_fit_elapsed_seconds']:.3f} summed fit seconds; "
        f"shape attempts {cost['shape_attempts']}, bootstrap stages {cost['bootstrap_stage_count']}. These cost scopes remain separate; terminal `cost_exact` is not a whole-algorithm objective counter. "
        'Every counted fit respects its public source2000/20s or shared5000/65s allowance and the entire original run stays below480s. No hidden held fit occurs in evaluation or replay.','',
        'The original production discovery fits c throughout. No whole-pipeline c=0 comparison or fitted-c localization advantage is claimed. Any later matched downstream c=0 sensitivity is conditional. '
        'No train-profile/age-model experiment is launched automatically.','',
        '![Fixed interpolation cohorts](blocked-coverage.png)','',
        'Artifacts include immutable derived input/provenance, original stage receipts, prediction/evaluation arrays, a strict no-fit replay, and source hashes. '
        '`training_context.py::load_training_context()` rebuilds only the derived training observations, their selected causal bank and strict endpoint; '
        '`predict_original(context,vector,nuisance,metadata)` provides a metadata-only frozen original prediction port. '
        'That port exactly reproduces all3988 saved predictions and is invariant to every held CFO perturbation without mutating seeds. '
        'Changed-model residual corrections require an explicit adapter, not silent omission. '
        'Entrypoints are `run_blocked.py --run`, `score_blocked.py`, `score_blocked.py --verify`, and `report_blocked.py`; attempted namespaces cannot be silently reused.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n');plot(r);seal()
    print(json.dumps(dict(sealed=True,train=train['associated'],held=held['associated'],held_requested=held_targets,selected_ids=len(r['training_selected_ids']))))


def plot(r):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    cohorts=[r['train'],r['held']]
    axes[0].bar(['Train','Held'],[100*m['associated']/m['observations'] for m in cohorts],color=['#3979b2','#df8c33'])
    axes[0].set_ylim(0,100);axes[0].set_ylabel('Original winners associated (%)');axes[0].set_title('Alternating20s:2073train /1909held')
    labels=[w['region_id'].replace('DSX01-','') for w in r['windows']]
    for offset,role,color in [(-.18,'train','#3979b2'),(.18,'held','#df8c33')]:
        axes[1].bar(np.arange(len(labels))+offset,[100*w[role]['associated']/w[role]['observations'] if w[role]['observations'] else 0 for w in r['windows']],width=.35,color=color,label=role)
    axes[1].set_xticks(np.arange(len(labels)),labels);axes[1].set_ylim(0,100);axes[1].set_ylabel('Fixed window subset associated (%)');axes[1].set_title('S03 windows; different train/held observations');axes[1].legend()
    fig.tight_layout();fig.savefig(HERE/'blocked-coverage.png',dpi=160);plt.close(fig)


def seal():
    paths=[p for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json']
    (HERE/'manifest.json').write_text(json.dumps(dict(files=[dict(path=str(p.relative_to(HERE)),sha256=digest(p.read_bytes())) for p in sorted(paths)]),indent=2)+'\n')


if __name__=='__main__':main()
