#!/usr/bin/python2.7

import sys, struct, binascii, os
from datetime import datetime

filename = sys.argv[1]
with open(filename, "r") as fd:
    data = fd.read()

file_length= len(data)

def mk_date (int_ts):
    return str(datetime.utcfromtimestamp(int_ts).strftime('%Y-%m-%d %H:%M:%S')) + " GMT"

def matches_timestamp (index):
    return ord(data[index]) == ts_1 and ord(data[index+1]) == ts_2 # and ord(data[index+2]) == ts_3 and ord(data[index+3]) == ts_4

def matches_vin (index):
    return data[index:index+4] == "5YJ3"

def matches_coord (index):
    return data[index] == 'N' and data [index + 5] == 'E'

def matches_coord_long (index):
    return data[index] == 'N' and data [index + 0x10] == 'E'


def to_u16 (j):
    b0 = ord(data[j+0]) * 256
    b1 = ord(data[j+1])
    return b0 + b1

def to_u32 (j):
    b0 = ord(data[j+0]) * 256 * 256 * 256
    b1 = ord(data[j+1]) * 256 * 256
    b2 = ord(data[j+2]) * 256
    b3 = ord(data[j+3])
    res = b0 + b1 + b2 + b3
    # print "to_u32: 0x%x" % (res)
    return res


class Block:
    def __init__(self, buffer, offset):
        self.buffer = buffer
        self.offset = offset

    def get_raw(self):
        return self.buffer[self.offset:self.offset+BLOCK_SIZE]

    def __repr__(self):
        return "Block[offset={:x}]".format(self.offset)
 

BLOCK_SIZE = 0x4000
blocks = [Block(data, offset) for offset in range(
    BLOCK_SIZE, # Skip the first block, it appears to have different format
    len(data),
    BLOCK_SIZE)]

for block in blocks:
    raw = bytes(block.get_raw())
    l, seq = struct.unpack(">HH", raw[:4]) # Guess: First two bytes length; second two bytes some kind of sequence
    print("{}: 0x{:04x} 0x{:04x} {}".format(os.path.basename(filename), l, seq, binascii.hexlify(raw[4:32])))

sys.exit(0)

hextimestamp = filename [filename.rfind("/") + 1 : -4]
print "[++] %s is %d bytes long" % (hextimestamp + ".HRL", file_length)
ts = int(hextimestamp, 16)

ts_1 = int (hextimestamp [0:2], 16)
ts_2 = int (hextimestamp [2:4], 16)
ts_3 = int (hextimestamp [4:6], 16)
ts_4 = int (hextimestamp [6:8], 16)
print "[++] Creation date:      %s" % mk_date (ts)


i = 0
timestamp_counter = 0
cord_counter = 0
cord_long_counter = 0

work_in_progress = False

while i < file_length:
    if i < 200 and matches_vin(i):
        print "[++] VIN: %s\n" % data[i:i+17]
    elif matches_timestamp(i):
        print "date %3d at index 0x%06x: %s" % (timestamp_counter, i, mk_date(to_u32(i)))
        if to_u16(i - 2) != 0x1d28:
            print "unexpected prolog, it's: 0x%04x" % to_u16(i - 2)
        timestamp_counter += 1
    elif matches_coord(i) and work_in_progress:
        print "gps: %3d at index 0x%06x, N 0x%08x E 0x%08x" % (cord_counter, i, to_u32(i+1), to_u32(i+6))
        cord_counter += 1
    elif matches_coord_long(i) and work_in_progress:
        print "gps LONG: %3d at index 0x%06x, N 0x%08x E 0x%08x" % (cord_long_counter, i, to_u32(i+1), to_u32(i+0x11))
        cord_long_counter += 1
    i += 1
