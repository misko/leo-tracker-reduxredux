"""Verify resolved receive method against isolated emulated register memory."""
from pathlib import Path
import hashlib
import json
import random
import struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_LR

p = Path(__file__).parent
source = p/'catson-bin--rx_lmac'
b = source.read_bytes()
with source.open('rb') as f:
    elf = ELFFile(f)
    matches = [r for r in elf.get_section_by_name('.rela.dyn').iter_relocations()
               if r['r_offset'] == 0x188ab0 and r['r_info_type'] == 1027]
    assert len(matches) == 1
    target = matches[0]['r_addend']
assert target == 0xbe5b0
u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
u.mem_map(0, 0x200000)
u.mem_write(0,b)
u.mem_map(0x300000, 0x10000)
u.mem_write(0x300008, struct.pack('<Q',0x301000))
u.mem_write(0x301008, struct.pack('<Q',0x302000))
accesses = []
def observe(uc, access, address, size, value, extra):
    accesses.append((address,size))
u.hook_add(UC_HOOK_MEM_READ, observe)
writes = []
u.hook_add(UC_HOOK_MEM_WRITE, lambda uc,a,addr,size,v,d: writes.append((addr,size)))
rng = random.Random(734)
rows=[]
for lane in [0,1]*50:
    value=rng.getrandbits(32)
    address=0x302000+0x34+4*lane
    u.mem_write(address,struct.pack('<I',value))
    u.reg_write(UC_ARM64_REG_X0,0x300000)
    u.reg_write(UC_ARM64_REG_X1,lane)
    u.reg_write(UC_ARM64_REG_LR,0x1f0000)
    accesses.clear()
    u.emu_start(target,0x1f0000,timeout=100000,count=20)
    assert u.reg_read(UC_ARM64_REG_X0)==value
    assert accesses==[(0x300008,8),(0x301008,8),(address,4)]
    assert not writes
    rows.append(dict(lane=lane,value=value,reads=list(accesses)))
result=dict(binary_sha256=hashlib.sha256(b).hexdigest(),vtable='0x188aa0',
            relocation='0x188ab0',target=hex(target),cases=rows,
            limitation='Memory model verifies CPU instructions, not register or FIFO hardware semantics')
(p/'receive-leaf-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('100 cases passed; three memory reads, no memory writes; return equals selected 32-bit value')
