"""Retain the fresh upstream failure independently of successful-scan metrics."""
from common import *
def main():
    folder=WORK/'failed-retry/DS28-0001';t=read(folder/'terminal.json');log=(folder/'algo02.log').read_text()
    assert t['state']=='failed' and 'ValueError: orbit phase interpolation never extrapolates' in log
    failure=dict(case='DS28-0001',state='failed',stage='ALGO02 regional discovery',
        reason='Orbit phase prediction exceeds the interpolation domain; preparation passed, discovery failed',
        exact_exception='ValueError: orbit phase interpolation never extrapolates',
        retry_seconds=t['elapsed_seconds'],terminal=str(folder/'terminal.json'),terminal_sha256=digest(folder/'terminal.json'),
        log=str(folder/'algo02.log'),log_sha256=digest(folder/'algo02.log'),
        retry_policy='unchanged installed algorithm; 1200 second cap',all_variants_unavailable=True)
    write(ROOT/'upstream-failure.json',failure)
    p=read(ROOT/'protocol.json');p['unavailable']=[failure if r['case']=='DS28-0001' else r for r in p['unavailable']]
    write(ROOT/'protocol.json',p)
    # Keep portable scientific error evidence with this report.
    (ROOT/'upstream-failure.log').write_text(log)
if __name__=='__main__':main()
