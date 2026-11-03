"""Resume pre-numerical export errors, preserving the original failed receipts."""
from run_baselines import *
def repair(p):
    old=read(p);case=old['case'];folder=p.parent;out=WORK/'baselines'/case
    if old['state']!='failed' or not (out/'source-export/descriptor.json').exists() or (out/'launch.json').exists():return
    write(folder/'pre-numerical-export-failure.json',old)
    code=call(R5,ROOT/'offline_algo05.py',['--source-terminal',folder/'algo04/terminal.json','--source-recovery',folder/'algo04/recovery','--output',out],folder/'algo05-export-retry.log')
    t=read(out/'terminal.json');old.update(state=t['state'],decision=t['decision'],terminal=str(out/'terminal.json'),
        failure=t.get('failure'),export_retry_returncode=code,reason=None)
    write(p,old);print(case,old['state'],flush=True)
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(repair,sorted((WORK/'cases').glob('*/receipt.json'))))
