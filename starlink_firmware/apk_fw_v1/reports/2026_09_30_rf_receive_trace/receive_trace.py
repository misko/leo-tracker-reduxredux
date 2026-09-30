"""Re-read bounded receive-path instructions, imports and call edges; no device IO."""
import hashlib
import io
import json
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / '2026_09_29_firmware_cluster_reaudit'))
from raw_audit import FIRMWARE, inspect_binary  # noqa: E402

WINDOWS = {
    'phyfw': [
        ('adc_register_mapping', 0x4F3C0, 0x4F540),
        ('sample_capture_file', 0x552D0, 0x55520),
        ('demod_capture_initialization', 0x55A90, 0x55C40),
        ('capture_integer_accumulator', 0x5A400, 0x5A4A0),
        ('equalization_error', 0x5A6B0, 0x5A848),
        ('equalization_caller', 0x5B820, 0x5B894),
        ('capture_worker', 0x60420, 0x605F0),
        ('capture_worker_caller', 0x605F0, 0x60640),
        ('toa_fifo_access', 0x60D20, 0x60D64),
        ('toa_fifo_worker', 0x61560, 0x618A0),
        ('register_mapping_helper', 0x9EE80, 0x9EF30)],
    'rx_lmac': [
        ('receive_dequeue_and_status', 0x27100, 0x27360),
        ('descriptor_allocation', 0x65130, 0x651E8),
        ('work_fifo_dequeue', 0x63F50, 0x64020),
        ('descriptor_header_copy', 0x653E0, 0x6542C),
        ('control_route', 0x30E78, 0x30E94),
        ('control_body_call', 0x551C4, 0x551F0),
        ('control_dispatch', 0x78870, 0x78948)],
}


def plt_imports(binary):
    """Resolve standard AArch64 PLT stubs through their GOT relocation addresses."""
    from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
    elf = ELFFile(io.BytesIO(binary))
    relocations = elf.get_section_by_name('.rela.plt')
    symbols = elf.get_section(relocations['sh_link'])
    got = {int(r['r_offset']): symbols.get_symbol(r['r_info_sym']).name
           for r in relocations.iter_relocations()}
    plt = elf.get_section_by_name('.plt')
    instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(plt.data(), plt['sh_addr']))
    result = {}
    for first, second in zip(instructions, instructions[1:], strict=False):
        if first.mnemonic != 'adrp' or not first.op_str.startswith('x16, #'):
            continue
        if second.mnemonic != 'ldr' or not second.op_str.startswith('x17, [x16, #'):
            continue
        page = int(first.op_str.split('#')[1], 0)
        offset = int(second.op_str.split('#')[1].rstrip(']'), 0)
        if page + offset in got:
            result[hex(first.address)] = got[page + offset]
    return result


def run():
    results = []
    for name, windows in WINDOWS.items():
        row = inspect_binary('catson-bin--' + name, windows)
        imports = plt_imports((FIRMWARE / ('catson-bin--' + name)).read_bytes())
        binary = (FIRMWARE / ('catson-bin--' + name)).read_bytes()
        offsets = ([0xAAE28, 0xAAEC0, 0xAC8F8, 0xACBE0, 0xADC50, 0xB00A0]
                   if name == 'phyfw' else [0x107C28, 0x1139E0, 0x115BB8])
        row['selected_literal_strings'] = [
            dict(file_offset=hex(offset), text=binary[offset:binary.index(b'\0', offset)]
                 .decode('ascii')) for offset in offsets]
        calls = []
        for region in row['regions']:
            for ins in region['instructions']:
                if ins['mnemonic'] in ('bl', 'blr'):
                    target = ins['operands'].removeprefix('#')
                    calls.append(dict(region=region['label'], site=ins['address'],
                                      target=target, imported_name=imports.get(target)))
        row['window_call_edges'] = calls
        row['plt_imports'] = imports
        results.append(row)
    output = BASE / 'local'
    output.mkdir(exist_ok=True)
    receipt = dict(method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   binaries=results, scope='Static bounded instructions, not an end-to-end trace.')
    (output / 'receive-trace.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Recorded', sum(len(r['regions']) for r in results), 'instruction windows.')


if __name__ == '__main__':
    run()
