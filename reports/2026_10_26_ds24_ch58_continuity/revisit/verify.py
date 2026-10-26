"""Independent audit of frozen inputs, causal forecasting and opened-window parity."""
from pathlib import Path
import study

HERE = Path(__file__).resolve().parent


def main():
    protocol = study.load(HERE / 'protocol.json')
    for path, digest in protocol['files'].items():
        assert study.sha(path) == digest, path
    panel = study.load(HERE / 'panel.json')
    predictions = study.load(HERE / 'predictions.json')
    results = study.load(HERE / 'results.json')
    assert len(panel['slots']) == 48
    assert len(predictions['rows']) == 96
    assert len(results['rows']) == 48
    by_key = {(r['request_id'], r['receiver_id']): r for r in predictions['rows']}
    for slot in panel['slots']:
        a = slot['raw_authority']['index']['acquisition']
        assert a['sample_end'] - a['sample_start'] == 200000
        for cell in slot['cells']:
            h = cell['header']
            expected = study.forecast(h, cell['earlier'])
            assert by_key[(h['request_id'], h['receiver_id'])]['forecast'] == expected
            redacted = dict(h, candidates=[dict(fractional_tracking_cfo_hz=123456789)])
            assert expected == study.forecast(redacted, cell['earlier'])
            assert all(p['valid_start_counter'] + 200000 <= h['target_start_counter'] for p in cell['earlier'])
    for row in results['rows']:
        assert row['status'] == 'complete', row['request_id']
        assert row['parity']['full_reader_exhausted']
        assert all(v['all_passed'] for v in row['parity']['parity'].values())
    assert results['runtime_identity_unchanged']
    study.write(HERE / 'verification.json', dict(all_passed=True, frozen_inputs=len(protocol['files']),
        requested_windows=48, paired_windows_original_parity=48, forecast_cells=96,
        fresh_target_response_redaction_cells=96, causal_nonoverlap_cells=96,
        protocol_sha256=study.sha(HERE / 'protocol.json'), predictions_sha256=study.sha(HERE / 'predictions.json'),
        results_sha256=study.sha(HERE / 'results.json')))
    print('verification passed')


if __name__ == '__main__':
    main()
