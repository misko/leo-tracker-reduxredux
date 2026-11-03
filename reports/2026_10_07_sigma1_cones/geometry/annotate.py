"""Attach selected-fit numerical status to generated marker receipts; no fitting."""
import argparse,csv,json
from pathlib import Path

def run(case):
    p=Path(__file__).resolve().parent;selected=json.loads((p.parent/case/'polished.json').read_text())['selections'];lookup={(r['option'],r['arm']):r for r in selected}
    path=p/('markers-'+case+'.csv')
    with path.open() as f:reader=csv.DictReader(f);rows=list(reader);fields=list(reader.fieldnames)
    for field in ('selected_fit_converged','selected_fit_stationarity','selected_fit_boundary'):
        if field not in fields:fields.append(field)
    for row in rows:
        r=lookup[row['option'],row['arm']]
        for key in ('converged','stationarity','boundary'):row['selected_fit_'+key]=r.get(key)
    with path.open('w') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    path=p/('markers-'+case+'.json');d=json.loads(path.read_text())
    for row in d['audits']:
        r=lookup[row['option'],row['arm']]
        for key in ('converged','stationarity','boundary'):row[key]=r.get(key)
    for examples in d['examples'].values():
        for items in examples.values():
            for row in items:
                r=lookup[row['option'],row['arm']]
                for key in ('converged','stationarity','boundary'):row['selected_fit_'+key]=r.get(key)
    path.write_text(json.dumps(d,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1939','2139'),required=True);run(parser.parse_args().case)
