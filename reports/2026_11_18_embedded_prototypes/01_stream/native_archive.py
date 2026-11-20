"""Incremental reader for the panel's compact, key-ordered native JSON exports."""

import json
import re


ARCHIVE_BLOCK_CHARS = 64 * 1024
SAMPLE_RATE_HZ = 10_000_000
ANCHOR_KEY = '{"clock_anchor":'
LAST_SAMPLE = re.compile(r'"last_sample_counter":(\d+),')
PROBES_START = re.compile(r'"probe_ms":(\d+),"probes":\[')
PROBE_END = re.compile(r'"valid_start_counter":(\d+),"visit_index":\d+}')
SAMPLE_RATE = re.compile(r'"sample_rate_hz":(\d+),')


class NativeArchive:
    def __init__(self, file):
        self.file = file
        self.buffer = file.read(ARCHIVE_BLOCK_CHARS)
        if not self.buffer.startswith(ANCHOR_KEY):
            raise ValueError('unexpected native archive header')
        anchor, _ = json.JSONDecoder().raw_decode(self.buffer, len(ANCHOR_KEY))
        self.first = int(anchor['sample_counter'])
        before, after = (anchor[key]['realtime_ns'] for key in ('before', 'after'))
        last_sample = None
        while self.buffer:
            match = LAST_SAMPLE.search(self.buffer)
            if match is not None:
                last_sample = int(match[1])
            start = PROBES_START.search(self.buffer)
            if start is not None:
                self.probe_s = int(start[1]) / 1000.
                self.offset = start.end()
                break
            extra = file.read(ARCHIVE_BLOCK_CHARS)
            if not extra:
                raise ValueError('native archive probe array not found')
            self.buffer = self.buffer[-256:] + extra
        if last_sample is None:
            raise ValueError('native archive last sample counter missing')
        self.meta = dict(causal_cutoff_utc_ns=before, anchor_utc_ns=(before+after)//2,
                         duration_s=(last_sample-self.first)/SAMPLE_RATE_HZ)

    def __iter__(self):
        while True:
            if self.offset == len(self.buffer):
                self.buffer = self.file.read(ARCHIVE_BLOCK_CHARS)
                self.offset = 0
                if not self.buffer:
                    raise ValueError('native archive missing the end of the probe array')
            if self.buffer[self.offset] == ']':
                tail = self.buffer[self.offset:] + self.file.read(ARCHIVE_BLOCK_CHARS)
                rate_match = SAMPLE_RATE.search(tail)
                if rate_match is None or int(rate_match[1]) != SAMPLE_RATE_HZ:
                    raise ValueError('unsupported native sample rate')
                return
            if self.buffer[self.offset] == ',':
                self.offset += 1
            match = PROBE_END.search(self.buffer, self.offset)
            if match is None:
                self.buffer = self.buffer[self.offset:] + self.file.read(ARCHIVE_BLOCK_CHARS)
                self.offset = 0
                match = PROBE_END.search(self.buffer)
                if match is None:
                    raise ValueError('native probe exceeds archive record budget or is truncated')
            start_s = (int(match[1])-self.first) / SAMPLE_RATE_HZ
            yield start_s + self.probe_s / 2, self.buffer[self.offset:match.end()]
            self.offset = match.end()
