#!/usr/bin/python2.7
# coding=utf-8

import os
import sys
import struct
from binascii import hexlify
from datetime import datetime
import zlib
from abc import ABCMeta, abstractmethod
import argparse
import itertools

def mk_date (int_ts):
    return str(datetime.utcfromtimestamp(int_ts).strftime('%Y-%m-%d %H:%M:%S')) + " GMT"

def warn(msg):
    color_red = '\033[31m'
    reset = '\033[0m'
    print(color_red + msg + reset)

def printable_ascii(s):
    return ''.join((c if 0x20 <= ord(c) < 0x7f else '·' for c in s))


BLOCK_SIZE = 0x4000
RECS_PER_BLOCK = 0x4000 / 11


class Block:
    def __init__(self, buffer, offset):
        self.buffer = buffer
        self.offset = offset

    def get_raw(self, with_tail=True):
        size = BLOCK_SIZE
        if not with_tail:
            size -= 5
        return self.buffer[self.offset:self.offset + size]

    def __repr__(self):
        return "Block[offset={:x}]".format(self.offset)

    def check(self):
        tail_bytes = self.buffer[self.offset+BLOCK_SIZE-5:self.offset+BLOCK_SIZE]
        tail, ff = struct.unpack(">IB", tail_bytes)
        if ff != 0xff:
            raise RuntimeError("final byte should be ff")
        crc = ~zlib.crc32(self.get_raw(with_tail=False)) & 0xffffffff
        if crc != tail:
            raise RuntimeError("bad crc")

    def get_rec(self, index):
        start = self.offset + 11 * index
        data = self.buffer[start:start + 11]
        if ord(data[0]) & 0xc0 != 0:
            return ControlFrame(data)
        else:
            return Record(data)

    def get_recs(self):
        i = 0
        while i < RECS_PER_BLOCK:
            yield self.get_rec(i)
            i += 1


class ControlFrame(object):
    def __init__(self, data):
        assert ord(data[0]) & 0xc0 != 0
        self.data = data

    def __repr__(self):
        return "CFrame {}   {}".format(hexlify(self.data), printable_ascii(self.data))


class Record(object):
    def __init__(self, data):
        assert len(data) == 11
        self.counting, self.op = struct.unpack('>BH', data[:3])
        if self.counting > 0x40:
            warn("Unexpected counting number: {:02x} {}".format(self.counting, hexlify(data)))
        self.rest = data[3:]

    def __repr__(self):
        if self.op in _record_interpreters:
            interpreter = _record_interpreters[self.op]
            return "Record {:02x}   {}: {}".format(self.counting, interpreter.__class__.__name__, interpreter.to_str(self))
        return "Record {:02x} / {:04x} {}  {}".format(self.counting, self.op, hexlify(self.rest), printable_ascii(self.rest))


class RecordInterpreter(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def to_str(self, rec):
        pass


class TimeStampRecord(RecordInterpreter):
    def to_str(self, rec):
        ts, zero = struct.unpack('>II', rec.rest)
        if zero != 0:
            raise RuntimeError("unexpected non-zero:" + str(zero))
        return mk_date(ts)


class VINRecord(RecordInterpreter):
    def to_str(self, rec):
        type = ord(rec.rest[0])
        if type == 0x11:
            return "Model: " + rec.rest[1:]
        elif type == 0x12:
            return "Serial: " + rec.rest[1:]
        elif type == 0x10:
            assert rec.rest[1:5] == '\0\0\0\0'
            return "Manufacturer: " + rec.rest[5:]
        else:
            raise RuntimeError("unexpected VIN record type: {:02x} '{}'".format(type, rec.rest[1:]))

def parse_hrl_file(filename):
    with open(filename, "r") as fd:
        data = fd.read()
        file_length = len(data)

    # filename is a unix timestamp
    hextimestamp = os.path.basename(filename)[:-4]
    print "[++] %s is 0x%x bytes long" % (hextimestamp + ".HRL", file_length)
    print "[++] Creation date: %s" % mk_date (int(hextimestamp, 16))

    return [Block(data, offset) for offset in range(
        BLOCK_SIZE, # Skip the first block, it appears to have different format
        len(data),
        BLOCK_SIZE)]


_record_interpreters = {
    0x1d28: TimeStampRecord(),
    0x3c05: VINRecord(),
    0xbc05: VINRecord(),
}

parser = argparse.ArgumentParser(description='Interpret Teslas HRL files.')
parser.add_argument('files', metavar='files', type=str, nargs='+', help='HRL files')
args = parser.parse_args()
files = args.files
# Sort by filename as the name is a unix timestamp
files.sort(key=lambda name: os.path.basename(name))

blocks = itertools.chain(*[parse_hrl_file(filename) for filename in files])

op_first_bytes = {}

for block in blocks:
    block.check()
    # raw = bytes(block.get_raw())
    # l, seq, x1, x2, x3 = struct.unpack(">BIIHB", raw[:1+4+4+2+1]) # Guess: First two bytes length; second two bytes some kind of sequence
    # print("{} @ 0x{:06x}: 0x{:02x} 0x{:08x} 0x{:08x} 0x{:02x} 0x{:02x} {}".format(os.path.basename(filename), block.offset, l, seq, x1, x2, x3, binascii.hexlify(raw[12:32])))
    print("B{:02d}".format(block.offset / BLOCK_SIZE))
    last_counting = 0x40
    for rec in block.get_recs():
        if isinstance(rec, Record):
            assert last_counting <= rec.counting or last_counting == 0x40, "{:02x} -> {:02x}".format(last_counting, rec.counting)
            last_counting = rec.counting
            if rec.op not in op_first_bytes:
                op_first_bytes[rec.op] = {}
            fb = ord(rec.rest[0])
            if fb not in op_first_bytes[rec.op]:
                op_first_bytes[rec.op][fb] = 0
            op_first_bytes[rec.op][fb] += 1
        else:
            last_counting = 0
        print(" " + str(rec))

for op, fbm in sorted(op_first_bytes.items(), key=lambda t: sum(t[1].values()), reverse=True):
    print("op {:04x}".format(op))
    for k, v in sorted(fbm.items(), key=lambda t: t[1], reverse=True)[:15]:
        print("  {:02x}: {:>5d} ".format(k, v))
    if len(fbm) > 15:
        print("  ...")

