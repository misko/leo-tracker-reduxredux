"""Explicit TLE catalogue selection for native snapshot replay, without scores."""
import math
import struct


def catalogue_id(field):
    if len(field)!=5:raise ValueError('invalid TLE catalogue field')
    if field[0].isalpha():
        alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ'
        if field[0] not in alphabet or not field[1:].isdigit():raise ValueError('invalid Alpha-5 identifier')
        return (alphabet.index(field[0])+10)*10000+int(field[1:])
    if not field.strip().isdigit():raise ValueError('invalid numeric catalogue identifier')
    value=int(field)
    if value<=0:raise ValueError('invalid catalogue number')
    return value


def select_tles(payload, ids):
    """IDs describe a pinned response-independent eligibility selection."""
    lines=payload.splitlines();pairs={};i=0
    while i<len(lines):
        if not lines[i].startswith('1 '):
            i+=1;continue
        if i+1==len(lines) or not lines[i+1].startswith('2 '):raise ValueError('unpaired TLE')
        a,b=lines[i:i+2]
        if len(a)!=69 or len(b)!=69:raise ValueError('invalid TLE line length')
        first,second=catalogue_id(a[2:7]),catalogue_id(b[2:7])
        if first!=second or first in pairs:raise ValueError('duplicate or mismatched TLE identity')
        pairs[first]=(a,b);i+=2
    if not ids or len(set(ids))!=len(ids):raise ValueError('empty or duplicated selected catalogue')
    if any(s not in pairs for s in ids):raise ValueError('selected satellite missing from snapshot')
    return str(len(ids))+'\n'+'\n'.join(line for s in ids for line in pairs[s])+'\n'


def replace_authority_states(authority_bytes, authority_meta, native_bytes, native_meta):
    """Bind native states to the same response-free LOC1 sites and catalogue."""
    for key in ('start_utc_ns','knot_start_s','knot_step_s','knot_count','satellite_ids'):
        if native_meta[key]!=authority_meta[key]:raise ValueError(f'orbit authority mismatch: {key}')
    if len(authority_bytes)<36:raise ValueError('truncated orbit authority')
    magic,satellites,knots,tracks,sites,start,step=struct.unpack_from('<5I2d',authority_bytes)
    if magic!=0x31434f4c or tracks!=0 or satellites!=len(native_meta['satellite_ids']) or knots!=native_meta['knot_count'] or start!=native_meta['knot_start_s'] or step!=native_meta['knot_step_s']:
        raise ValueError('inconsistent or response-bearing authority fixture')
    offset=36+sites*48+satellites*4
    length=satellites*knots*48
    if len(native_bytes)!=length or len(authority_bytes)!=offset+length:raise ValueError('orbit payload length mismatch')
    ids=list(struct.unpack_from('<'+str(satellites)+'i',authority_bytes,36+sites*48))
    if ids!=native_meta['satellite_ids']:raise ValueError('orbit payload catalogue mismatch')
    if not all(math.isfinite(v[0]) for v in struct.iter_unpack('<d',native_bytes)):
        raise ValueError('nonfinite native orbit state')
    return authority_bytes[:offset]+native_bytes
