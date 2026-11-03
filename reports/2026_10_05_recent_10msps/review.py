"""Read-only four-hour capture and persisted Doppler-result audit; no IQ reads."""
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path('/srv/bulk/leo')
END = datetime.fromisoformat('2026-10-05T13:59:31+00:00')
START = END - timedelta(hours=4)


def read(path, provenance):
    raw = path.read_bytes()
    provenance.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest()))
    return json.loads(raw)


def main():
    rows, provenance, errors = [], [], []
    versions = sorted(ROOT.glob('scanner-shared-tracking-v*'),
                      key=lambda p: int(p.name.split('-v')[-1]), reverse=True)
    for path in (ROOT/'v052-adaptive-live').glob('adaptive-seven-minute-*.json'):
        if path.stat().st_mtime < START.timestamp()-600:
            continue
        try:
            d = read(path, provenance)
            finished = datetime.fromisoformat(d['created_at'])
            if not START <= finished <= END + timedelta(minutes=6):
                continue
            sid = Path(d['iq_archive']).name
            pub = ROOT/'scanner-adaptive-recordings'/sid/'manifest.json'
            archive = Path(d['iq_archive'])/'manifest.json'
            a = read(archive, provenance) if archive.exists() else None
            p = read(pub, provenance)['manifest'] if pub.exists() else None
            if p:
                epoch = p['timing']['first_sample_estimate_utc_ns']/1e9
            elif a:
                epoch = a['evidence']['utc_timing']['begin_after_realtime_ns']/1e9
            else:
                raise ValueError('No source or publication timing')
            if not START.timestamp() <= epoch <= END.timestamp():
                continue
            m = d['run']['metrics']
            terminal = a['terminal'] if a else p['receipt']['terminal']
            r = dict(session_id=sid, start_utc=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                     start_pacific=datetime.fromtimestamp(epoch, ZoneInfo('America/Los_Angeles')).isoformat(),
                     rate_hz=d['rate_hz'], edge=d['selected_edge'],
                     duration_s=m['source_span_samples']/d['rate_hz'],
                     planned=m['planned'], delivered=m['delivered'], skipped=m['skipped'],
                     invalid=m['invalid'], cancelled=m['cancelled'], error=terminal.get('error',terminal.get('error_code')),
                     deadline_forced=m['deadline_forced'], classification_dropped=d['run']['classification_dropped'],
                     delivery_gate=d['run']['gate']['passed'], iq_bytes=m['iq_bytes'],
                     published=bool(p), timing_qualified=p['timing'].get('qualified') if p else None,
                     analysis_manifest=(ROOT/'scanner-adaptive-analysis'/sid/'manifest.json').exists(),
                     tracking_version=None, trajectory_state=None, reviews=0, rms_median_hz=None)
            for folder in versions:
                tracking = folder/sid/'manifest.json'
                if not tracking.exists(): continue
                t = read(tracking,provenance)['document']
                reviews = t.get('track_reviews',[])
                values = [next(c for c in v['candidates'] if c['rank']==1)['randomized_evaluation_rms_hz'] for v in reviews]
                r.update(tracking_version=t['schema_version'], trajectory_state=t['trajectory_state'],
                         reviews=len(reviews), rms_median_hz=median(values) if values else None,
                         rms_values=values, tracking_config=t['configuration_digest'])
                break
            rows.append(r)
        except Exception as exc:
            errors.append(dict(path=str(path),error=str(exc)))
    rows.sort(key=lambda r:r['start_utc'])
    out=dict(start=START.isoformat(),end=END.isoformat(),rows=rows,errors=errors,provenance=provenance)
    Path('/var/tmp/leo-recent-10msps.json').write_text(json.dumps(out,indent=2))
    for r in rows:
        print(json.dumps({k:v for k,v in r.items() if k not in ('rms_values','tracking_config')}))
    print('ERRORS',errors)


if __name__=='__main__': main()
