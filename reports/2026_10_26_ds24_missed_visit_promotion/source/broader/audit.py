"""Terminal non-geographic accounting for the frozen all24 coherent application."""
import collections
from pathlib import Path
import application as app

def main():
    raw=app.read(app.RAW/'protocol.json');forecast=app.read(app.HERE/'forecast_protocol.json')
    for p,h in raw['files'].items():assert app.sha(p)==h,p
    for p,h in forecast['files'].items():assert app.sha(p)==h,p
    nomination=app.read(app.HERE/'nominations.json');named={r['case']:r for r in nomination['cases']}
    reuse={r['case']:r for r in app.read(app.HERE/'reuse_audit.json')['cases']}
    rows=[];totals=collections.Counter();files={}
    for case in raw['cases']:
        folder=app.HERE/'graphs'/case;seal=app.read(folder/'terminal_seal.json')
        assert seal['all_passed'] and seal['application_protocol_sha256']==app.sha(app.RAW/'protocol.json')
        for p,h in seal['files'].items():assert app.sha(p)==h,p
        files.update(seal['files']);files[str(folder/'terminal_seal.json')]=app.sha(folder/'terminal_seal.json')
        audit=app.read(folder/'audit.json');ledger=app.read(audit['ledger_path'])
        for result in ledger['all_target_outcomes']:
            evidence=result.get('ordering_evidence')
            if evidence:
                path=evidence['selection_path'];assert app.sha(path)==evidence['selection_sha256']
                files[path]=app.sha(path)
        original=app.read(app.SOURCE/case/'observations.json');observations=app.read(folder/'observations.json')
        owners=app.read(folder/'new_native_owners.json')['observation_ids'];ids=[o['observation_id'] for o in observations]
        assert observations[:len(original)]==original and len(ids)==len(set(ids))
        assert set(owners)==set(ids)-{o['observation_id'] for o in original}
        assert audit['bank_support']['reuse_allowed'] and audit['bank_support']['complete_causal_catalogue']
        assert audit['no_sparse_union'] and audit['no_recovered_donors'] and not audit['geographic_inputs']
        n=named[case]
        if not n['paired_windows']:
            assert audit['no_eligible_lane'] and not owners
            assert app.sha(folder/'observations.json')==app.sha(app.SOURCE/case/'observations.json')
            assert app.sha(folder/'tracks.json')==app.sha(app.SOURCE/case/'tracks.json')
            outcome=None;seconds=0;origin='baseline_no_eligible_lane'
        elif case in reuse:
            outcome=Path(reuse[case]['outcome_path']);seconds=app.read(outcome)['seconds'];origin='exact_prior_reuse'
        else:
            outcome=app.RAW/'outcomes'/(case+'.json.gz');terminal=app.read(app.RAW/'terminal'/(case+'.json'))
            assert terminal['exit_code']==0 and terminal['seconds']<600
            seconds=app.read(outcome)['seconds'];assert seconds<580;origin='fresh_bounded_replay'
            files[str(app.RAW/'terminal'/(case+'.json'))]=app.sha(app.RAW/'terminal'/(case+'.json'))
        statuses=collections.Counter()
        if outcome:
            doc=app.read(outcome)
            assert len(doc['rows'])==n['paired_windows'] and all(r['status']=='complete' for r in doc['rows'])
            for window in doc['rows']:
                assert window['native_receipt']['full_reader_exhausted']
                assert window['native_receipt']['repeated_blind_acquisition_calls']==0
                assert not window['native_receipt']['fresh_per_window_paired_candidate_parity']
                statuses.update(c['result']['status'] for c in window['cells'])
            assert sum(statuses.values())==2*n['paired_windows']
            files[str(outcome)]=app.sha(outcome)
        counts=ledger['counts']
        row=dict(case=case,cohort=n['cohort'],origin=origin,paired_windows=n['paired_windows'],capped_blocks=n['capped_blocks'],
            new_native=len(owners),new_in_graph=audit['new_in_graph'],new_curved=audit['new_in_curved_graph'],
            new_outside_graph=audit['new_outside_graph'],original_GLRT_count=len(original),total_GLRT_count=len(observations),
            graph_tracks=len(app.read(folder/'tracks.json')),receiver_statuses=dict(statuses),
            search_admitted=counts.get('search_admitted',0),point_admitted=counts.get('point_admitted',0),
            search_pilot_confirmed=counts.get('search_pilot_confirmed',0),raw_seconds=seconds,
            observations_sha256=audit['observations_sha256'],tracks_sha256=audit['tracks_sha256'],
            bank_candidate_count=audit['bank_support']['candidate_count'],terminal_seal_sha256=app.sha(folder/'terminal_seal.json'))
        rows.append(row)
        for key in ['paired_windows','new_native','new_in_graph','new_curved','new_outside_graph','search_admitted','point_admitted','search_pilot_confirmed']:
            totals[key]+=row[key]
    assert len(rows)==24 and sum(r['paired_windows'] for r in rows)==nomination['paired_windows']
    summary=dict(all24_accounted=True,all_source_input_hashes_unchanged=True,all_graph_handoffs_passed=True,
        original_prefix_and_unique_owners_all_pass=True,full_causal_bank_support_all_pass=True,
        metadata_handoff_version=2,no_sparse_union=True,no_recovered_donors=True,no_position_or_geographic_outcomes=True,
        raw_protocol_sha256=app.sha(app.RAW/'protocol.json'),forecast_protocol_sha256=app.sha(app.HERE/'forecast_protocol.json'),
        intended_cases=24,eligible_cases=sum(r['paired_windows']>0 for r in rows),no_eligible_cases=sum(not r['paired_windows'] for r in rows),
        fresh_cases=len(raw['fresh_cases']),reused_cases=len(reuse),new_raw_paired_windows=sum(r['paired_windows'] for r in rows if r['origin']=='fresh_bounded_replay'),
        unavailable_inventory=nomination['unavailable'],cases=rows,totals=dict(totals),
        graph_infrastructure_attempts_preserved=['handoff.py','graph_protocol.json','graph_logs','graph_terminal'],
        graph_infrastructure_continuation='handoff_v2.py uses a separate UID1000 graph process; identical scientific ports, ledgers and config; no acquisition rerun')
    app.write(app.HERE/'summary.json',summary)
    for key in ['reserved','development']:
        selected=[r for r in rows if r['cohort']==key]
        print(key,{k:sum(r[k] for r in selected) for k in ['paired_windows','new_native','new_curved','new_outside_graph']},flush=True)
    lines=['# Frozen R01 coherent application across 24 DS24 scans','',
        f"All 24 intended cases have sealed graph handoffs. {summary['eligible_cases']} scans nominated coherent blocks; {summary['no_eligible_cases']} retained byte-identical baseline observations and tracks. {totals['paired_windows']} paired native windows were evaluated: {summary['new_raw_paired_windows']} fresh and 263 reused after exact source/input/native/serialized-forecast equality audit. No block reached its cap.",'',
        f"The coherent-only candidate adds {totals['new_native']} native owners; {totals['new_in_graph']} enter the RF graph and {totals['new_curved']} enter actively curved support. These are acquisition/graph outcomes, not localization or satellite-identification results. This branch did not open geographic errors or run positions.",'',
        '| Case | Cohort | Windows | New | In graph | Curved | Outside | Input origin |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"|{r['case']}|{r['cohort']}|{r['paired_windows']}|{r['new_native']}|{r['new_in_graph']}|{r['new_curved']}|{r['new_outside_graph']}|{r['origin']}|")
    lines+=['','The original selector ranks CH5–8 lanes by new curved count, new native count, channel and native receiver. At most two lanes per recording seed the same closed ±12-second processed-visit blocks, both receivers, earliest80 visits per block before deduplication. Sparse additions nominate blocks only; final candidate observations contain original winners plus coherent-block additions only. Donors remain earlier original tracking candidates. The original R01 predictor, adapter, timing search, independent confirmation and gates are unchanged; v2 JSON isolation precedes native enrichment.','',
        'Each graph handoff preserves the exact original observation prefix, uses unique native ownership, and verifies the full causal catalogue and sufficient time support. NEW-owner IDs, ledgers, observation/track hashes, upstream protocols and terminal seals accompany every case. The position owner derives graph noise and the NEW-only one-bin uncertainty floor, retaining matched c=0/fitted-c jobs.','',
        'Two raw workers used the historical frozen runtime, BLAS1 and580-second per-case caps. No fresh RF, QNAP writes, geographical inputs, recovered-donor feedback, forced satellite identities or acquisition retry occurred. An initial graph orchestration import failure is retained; the corrected orchestration invokes unchanged graph code in a separate UID1000 process. This does not reset raw budgets or rerun raw scoring.','',
        'Ten original DS24 inventory members are unavailable and remain explicit scope limitations. Root separately inventoried DS23: native2.5MS/s is incompatible with unchanged R01 timing, which requires10MS/s; no resampling or port is included here.','',
        f"Raw protocol SHA256: `{summary['raw_protocol_sha256']}`. Forecast/source-input protocol SHA256: `{summary['forecast_protocol_sha256']}`. Per-case terminal seals bind exact public graph inputs. All artifact hashes are in `artifact_seal.json`."]
    with (app.HERE/'REPORT.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    names=['application.py','replay.py','handoff.py','handoff_v2.py','graph_build.py','handoff_dispatch.py','handoff_dispatch_v2.py','audit.py',
        'test_application.py','test_replay.py','test_handoff.py','nominations.json','nominated_pairs.json','panel.json','predictions.json',
        'prediction_packets_v2.json','donor_authority.json','metadata_audit.json','forecast_protocol.json','reuse_audit.json','raw_test_results.json',
        'graph_protocol.json','graph_protocol_v2.json','handoff_summary_v2.json','HANDOFF_READY_01.json','HANDOFF_READY.json','summary.json','REPORT.md']
    files.update({str(app.HERE/n):app.sha(app.HERE/n) for n in names})
    for directory in ['graph_logs','graph_terminal','graph_logs_v2','graph_terminal_v2','raw/logs','raw/terminal']:
        for path in (app.HERE/directory).glob('*'):
            if path.is_file():files[str(path)]=app.sha(path)
    files[str(app.RAW/'protocol.json')]=app.sha(app.RAW/'protocol.json')
    files[str(app.RAW/'run_authorization.json')]=app.sha(app.RAW/'run_authorization.json')
    app.write(app.HERE/'artifact_seal.json',dict(all_passed=True,files=files,raw_IQ_exported=False,no_geographic_outcomes=True))
    print(dict(summary=app.sha(app.HERE/'summary.json'),artifact_seal=app.sha(app.HERE/'artifact_seal.json')),flush=True)

if __name__=='__main__':main()
