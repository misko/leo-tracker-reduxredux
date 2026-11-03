"""Self-contained CLI contract check: score-at uses full association semantics."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def main():
    binary=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as directory:
        fixture=Path(directory)/'synthetic.loc1'
        data=struct.pack('<5I2d',0x31434f4c,1,2,1,1,-10.,30.)
        data+=struct.pack('<6d',6378.137,0,0,1,0,0)
        data+=struct.pack('<2I',6,5)
        data+=struct.pack('<6d',0,1,2,3,4,5)+struct.pack('<6d',*([0]*6))+bytes([0,1,0,1,0,1])
        data+=struct.pack('<i',123)+struct.pack('<12d',7000,0,0,0,0,0,7000,0,0,0,0,0)
        fixture.write_bytes(data)
        def run(mode,args):
            return subprocess.run([str(binary),mode,str(fixture),*args],capture_output=True,text=True,timeout=10)
        reference=run('score',['1']);assert reference.returncode==0,reference.stderr
        for workers in ['1','2']:
            result=run('score-at',['0','0','0','0',workers]);assert result.returncode==0,result.stderr
            assert json.loads(result.stdout)==json.loads(reference.stdout)
            assert json.loads(result.stdout)['points'][0]['tracks'][0]['candidate_id']==123
        for args in [['nan','0','0','0'],['91','0','0','0'],['0','181','0','0'],
                     ['0','0','inf','0'],['0','0','0','bad'],['0','0','0'],['0','0','0','0','3']]:
            assert run('score-at',args).returncode==2,args
    print('score-at CLI tests passed')


if __name__=='__main__':main()
