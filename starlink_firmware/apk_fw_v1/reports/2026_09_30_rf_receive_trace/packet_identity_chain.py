"""Execute a constructed packet from parser entry to received SYSINFO stores."""
import argparse
import hashlib
import json
import struct

from control_buffer_chain import BASE, BUFFER, CANARY, SOURCE, call, machine
from parser_gate import STOP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn import arm64_const as registers


def run(controls=False, wrapped=False, descriptor=False, caller=0, fifo=False,
        through_update=False, primary=False, notification=False):
    if notification:
        primary = through_update = fifo = True
    if fifo and not caller:
        caller = 0x28D50
    assert caller in (0, 0x28B80, 0x28D50)
    descriptor = descriptor or bool(caller)
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    root, new, node, backing, record, aux, outer, stats = (
        0x800000, 0x802000, 0x804000, 0x806000, 0x808000, 0x80A000, 0x810000, 0x812000)
    recv = outer + 0x280
    selected = root + (0x41538 if primary else 0x415A0)
    uc.mem_map(root, 0x90000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    for address in (0x1A9BE8, 0x1AAF90):
        uc.mem_write(address, struct.pack('<I', 0x1234))
    uc.mem_write(0x1FD4E0, bytes([0]))
    visited = []
    rejection = {}
    allocation = [0]
    descriptor_address, pool = root + 0x82000, root + 0x83000
    fifo_object, fifo_private, fifo_bank, mappings = (
        root + 0x84000, root + 0x84100, root + 0x85000, root + 0x86000)
    bank_reads = []

    def on_read(engine, access, address, size, value, user):
        if fifo_bank <= address < fifo_bank + 0x1000:
            bank_reads.append((address - fifo_bank, size))

    def hook(engine, address, size, user):
        gates = {0x3132C: 'reader', 0x31400: 'prefix',
                 0x314B4: 'header_length', 0x551EC: 'sysinfo'}
        if controls and (address == 0xC77B0 or
                         (address in gates and
                          engine.reg_read(registers.UC_ARM64_REG_X0))):
            rejection.update(stage=gates.get(address, 'payload_length'),
                             x0_at_stop=engine.reg_read(registers.UC_ARM64_REG_X0),
                             pc=hex(address))
            engine.emu_stop()
            return
        if address in (0xC6240, 0xC6870, 0xC6A40, 0x30E20, 0x78870, 0xD7990, 0x44DA0):
            visited.append(hex(address))
        if descriptor and not fifo and address == 0x63F50:
            holder = engine.reg_read(registers.UC_ARM64_REG_X1)
            engine.mem_write(holder, struct.pack('<Q', descriptor_address))
            engine.reg_write(registers.UC_ARM64_REG_X0, 0)
        elif address == 0x105540:
            engine.reg_write(registers.UC_ARM64_REG_X0, 1)
        elif address == 0xEEE60:
            engine.reg_write(registers.UC_ARM64_REG_X0,
                             node if descriptor and allocation[0] == 0 else new)
            allocation[0] += 1
        elif address == 0x21E70:
            dst = engine.reg_read(registers.UC_ARM64_REG_X0)
            src = engine.reg_read(registers.UC_ARM64_REG_X1)
            count = engine.reg_read(registers.UC_ARM64_REG_X2)
            assert (dst, src, count) == (new, node, 0x80) or (
                descriptor and src == descriptor_address and count == 16) or (
                notification and count == 0x9E2)
            engine.mem_write(dst, bytes(engine.mem_read(src, count)))
        else:
            return
        engine.reg_write(registers.UC_ARM64_REG_PC,
                         engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    if fifo:
        uc.hook_add(UC_HOOK_MEM_READ, on_read)
    cases = []
    configs = [(f'identity_{identity:08x}', identity, 20, 8, 8) for identity in
               [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]]
    if controls:
        configs = [(label, 0x12345678, size, header, payload) for
                   label, size, header, payload in [
                       ('valid', 20, 8, 8), ('header_too_small', 20, 3, 8),
                       ('header_too_large', 20, 17, 8),
                       ('payload_too_large', 20, 8, 9),
                       ('truncated_buffer', 16, 8, 8),
                       ('short_sysinfo', 16, 8, 4)]]
    for label, identity, size, header, payload in configs:
        uc.mem_write(root, bytes(0x90000))
        # All feature queries execute against the same explicit mode-one record.
        uc.mem_write(0x1D3958, bytes(0xC0))
        uc.mem_write(0x1D3960, struct.pack('<Q', root + 0x88000))
        uc.mem_write(root + 0x88044, struct.pack('<I', 1))
        packet = bytearray(20)
        packet[4:6] = header.to_bytes(2, 'little')
        packet[6:9] = (6 | (payload << 4)).to_bytes(3, 'little')
        packet[12:20] = ((3 << 8) | (identity << 11) | (7 << 43) | (9 << 51)).to_bytes(
            8, 'little')
        uc.mem_write(BUFFER, bytes(packet))
        for address, value in ((node + 8, backing), (node + 0x28, node),
                               (node + 0x30, BUFFER), (recv, root),
                               (root + 8, root), (root + 0x87088, stats),
                               (root + 0xF088, stats),
                               (recv + 0x5B0, stats), (recv + 0x5B8, aux),
                               (recv + 0x80, record), (record, root),
                               (root + 0xE5A0 + 0xAE8, stats), (root + 0x53378, aux)):
            uc.mem_write(address, struct.pack('<Q', value))
        uc.mem_write(node + 0x16, struct.pack('<I', size))
        uc.mem_write(backing + 2, struct.pack('<H', 1))
        uc.mem_write(recv + 0x88, struct.pack('<H', 123))
        uc.mem_write(record + 0x12, struct.pack('<H', 123))
        uc.mem_write(aux + 0x2C4, bytes([not primary]))
        uc.mem_write(selected + 0x48, bytes([1]))
        uc.mem_write(root + 0x4164C, struct.pack('<I', 0xC35A5AC3))
        if notification:
            uc.mem_write(root + 0x462B0, struct.pack('<Q', root + 0xC000))
            uc.mem_write(root + 0x41610, struct.pack('<I', 0x13579BDF))
        uc.mem_write(selected, struct.pack('<I', 0xDEADBEEF))
        allocation[0] = 0
        rejection.clear()
        if descriptor:
            uc.mem_write(node, bytes(0x100))
            uc.mem_write(backing, bytes(0x100))
            uc.mem_write(descriptor_address, struct.pack('<I', size) + bytes(12) +
                         struct.pack('<Q', BUFFER))
            uc.mem_write(pool + 0x10, struct.pack('<Q', backing))
            uc.mem_write(0x188D60, struct.pack('<Q', pool))
            uc.mem_write(0x180910, bytes([0]))
            uc.mem_write(0x1A7CD8, struct.pack('<I', 0x1234))
            if fifo:
                uc.mem_write(0x188AB0, struct.pack('<Q', 0xBE5B0))
                uc.mem_write(0x188AD0, struct.pack('<Q', 0xBE5E0))
                uc.mem_write(0x180910, bytes([1, 1]))
                uc.mem_write(0x180928, struct.pack('<II', 2, 2))
                uc.mem_write(0x180900, struct.pack('<Q', fifo_object))
                uc.mem_write(fifo_object, struct.pack('<QQ', 0x188AA0, fifo_private))
                uc.mem_write(fifo_private + 8, struct.pack('<Q', fifo_bank))
                uc.mem_write(0x190708, struct.pack('<Q', mappings))
                uc.mem_write(mappings + 2 * 0x60 + 0x18,
                             struct.pack('<Q', descriptor_address))
                uc.mem_write(mappings + 2 * 0x60 + 0x30, struct.pack('<Q', 0x10020000))
                uc.mem_write(fifo_bank + 0x34, struct.pack('<I', 0x10020000))
            if caller:
                uc.mem_write(outer + 8, struct.pack('<Q', root))
            else:
                call(uc, 0x27100, (recv, 0))
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
                assert int.from_bytes(uc.mem_read(recv + 8, 8), 'little') == node
                assert allocation[0] == 1
        elif wrapped:
            # Actual allocation-success initializer; no descriptor producer is emulated.
            uc.mem_write(node, bytes(0x100))
            uc.mem_write(backing, bytes(0x100))
            initial = {9: 0, 19: BUFFER, 20: size, 21: 0x1234,
                       22: 0x5B1, 23: 0x123456789, 24: 0x267D0,
                       25: 0, 26: 0, 27: node, 28: backing}
            for number, value in initial.items():
                uc.reg_write(getattr(registers, f'UC_ARM64_REG_X{number}'), value)
            uc.emu_start(0xF0C58, 0xF0D18, count=100)
            assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0xF0D18
            call(uc, 0x311E0, (recv, node, 0, 0, 0))
            assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
            assert int.from_bytes(uc.mem_read(recv + 8, 8), 'little') == node
            assert uc.mem_read(recv + 0x15, 1)[0] == 1
        else:
            uc.mem_write(recv + 8, struct.pack('<Q', node))
            uc.mem_write(recv + 0x15, bytes([1]))
        visited.clear()
        rejection.clear()
        bank_reads.clear()
        stop = (0x5674C if primary else 0x5522C) if through_update else 0x44E18
        if notification:
            stop = 0xED500
        call(uc, caller or 0x312B0, (outer, 1 if caller else root), stop=stop)
        pc = uc.reg_read(registers.UC_ARM64_REG_PC)
        if notification and not rejection and pc != stop:
            # The longer connected path may exceed the shared 2,500-instruction cap.
            uc.emu_start(pc, stop, count=1000, timeout=100000)
            pc = uc.reg_read(registers.UC_ARM64_REG_PC)
        if fifo:
            assert bank_reads.count((0x34, 4)) == 1
            assert bank_reads.count((0x30, 4)) >= 1
            assert all(item in ((0x30, 4), (0x34, 4)) for item in bank_reads)
        if rejection:
            assert int.from_bytes(uc.mem_read(selected, 4), 'little') == 0xDEADBEEF
            assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == 0xC35A5AC3
            assert bytes(uc.mem_read(BUFFER, 20)) == packet
            cases.append(dict(label=label, rejection=dict(rejection), visited=list(visited)))
            continue
        assert pc == stop, (hex(pc), visited)
        if through_update:
            assert int.from_bytes(uc.mem_read(stats + (0x38 if primary else 0x3C), 4),
                                  'little') == 1
        assert int.from_bytes(uc.mem_read(selected, 4), 'little') == identity
        assert bytes(uc.mem_read(selected + 0x5A, 2)) == bytes([7, 9])
        assert uc.mem_read(selected + 7, 1)[0] == 1
        if primary and through_update:
            assert uc.mem_read(root + 0x41594, 1)[0] == 1
        if notification:
            assert uc.reg_read(registers.UC_ARM64_REG_X0) == root + 0xC000
            assert uc.reg_read(registers.UC_ARM64_REG_X2) == 2
            vectors = uc.reg_read(registers.UC_ARM64_REG_X1)
            head, head_len, body, body_len = struct.unpack(
                '<QQQQ', bytes(uc.mem_read(vectors, 32)))
            assert (head_len, body_len) == (8, 0x1418)
            assert bytes(uc.mem_read(head, 8)) == struct.pack('<II', 0x14200006, 0x13579BDF)
            assert uc.mem_read(body, 1)[0] == 0
            assert uc.mem_read(body + 8, 1)[0] == 0
            assert int.from_bytes(uc.mem_read(body + 9, 4), 'little') == identity
            assert bytes(uc.mem_read(body + 13, 2)) == bytes([7, 9])
        assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == 0xC35A5AC3
        assert bytes(uc.mem_read(BUFFER, 20)) == packet
        cases.append(dict(label=label, identity=identity, packet_hex=packet.hex(),
                          visited=list(visited)))
    return dict(binary_sha256=digest, cases=cases, real_wrapper_and_install=wrapped,
                descriptor_receive=descriptor,
                receive_parser_caller=hex(caller) if caller else None,
                actual_fifo_dequeue=fifo,
                through_update=through_update,
                primary_context=primary,
                notification_constructed=notification,
                successful_stop=('0xed500 transport entry, before sending' if notification else
                                 '0x5674c before follow-up construction' if
                                 primary and through_update else
                                 '0x5522c before buffer cleanup, complete minimal updater '
                                 'returned' if through_update else '0x44e18 initial stores'),
                fifo_setup=('Actual virtual queue/status reads and type2 address translation. '
                            'Synthetic register bank and address-map records; no FIFO pop '
                            'side effects or hardware producer modeled.' if fifo else None),
                descriptor_setup=(
                    ('Actual FIFO dequeue supplies descriptor; port query enabled. ' if fifo else
                     'FIFO dequeue stub supplies descriptor; port query global disabled. ')
                    + 'Real feature queries use configuration enum1; queue=0; descriptor '
                    'flags zero. Node allocator '
                    'stub, synthetic backing-pool free list, metadata copy stub. '
                    + ('Actual receive/parser caller executed continuously to store or gate; '
                       'caller completion and hardware not executed.' if caller else
                       'Receive returns before harness separately calls parser; '
                       'scheduler and hardware not executed.') if descriptor else None),
                limitation='Constructed packet, configured routing record and enum1 record. '
                'Allocator, metadata-copy and diagnostic-query stubs. See successful_stop '
                'for executed extent; full handler completion remains untested. Controls stop at '
                'failed gates, before error handling. x0_at_stop is a status only at helper '
                'returns, not at the payload-length error branch. No CRC/FEC/RF proof.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--wrapped', action='store_true')
    parser.add_argument('--descriptor', action='store_true')
    parser.add_argument('--fifo', action='store_true')
    parser.add_argument('--through-update', action='store_true')
    parser.add_argument('--primary', action='store_true')
    parser.add_argument('--notification', action='store_true')
    parser.add_argument('--caller', type=lambda value: int(value, 0),
                        choices=(0x28B80, 0x28D50), default=0)
    args = parser.parse_args()
    result = run(controls=args.controls, wrapped=args.wrapped, descriptor=args.descriptor,
                 caller=args.caller, fifo=args.fifo, through_update=args.through_update,
                 primary=args.primary, notification=args.notification)
    name = 'packet-identity-controls.json' if args.controls else 'packet-identity-chain.json'
    if args.wrapped:
        name = name.replace('.json', '-wrapped.json')
    if args.descriptor:
        name = name.replace('.json', '-descriptor.json')
    if args.caller:
        name = name.replace('.json', f'-caller-{args.caller:x}.json')
    if args.fifo:
        name = name.replace('.json', '-fifo.json')
    if args.through_update:
        name = name.replace('.json', '-updated.json')
    if args.primary:
        name = name.replace('.json', '-primary.json')
    if args.notification:
        name = name.replace('.json', '-notification.json')
    (BASE / 'local' / name).write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'packet-to-identity cases passed.')
