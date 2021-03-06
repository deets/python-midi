from .containers import (
    Pattern,
    Track,
    )

from .events import *
from struct import unpack, pack
from .constants import *
from .util import read_varlen, write_varlen

class FileReader(object):
    def read(self, midifile):
        pattern = self.parse_file_header(midifile)
        for track in pattern:
            self.parse_track(midifile, track)
        return pattern

    def parse_file_header(self, midifile):
        # First four bytes are MIDI header
        magic = midifile.read(4)
        if magic != b'MThd':
            raise TypeError("Bad header in MIDI file.")
        # next four bytes are header size
        # next two bytes specify the format version
        # next two bytes specify the number of tracks
        # next two bytes specify the resolution/PPQ/Parts Per Quarter
        # (in other words, how many ticks per quater note)
        data = unpack(">LHHH", midifile.read(10))
        hdrsz = data[0]
        format = data[1]
        tracks = [Track() for x in range(data[2])]
        resolution = data[3]
        # XXX: the assumption is that any remaining bytes
        # in the header are padding
        if hdrsz > DEFAULT_MIDI_HEADER_SIZE:
            midifile.read(hdrsz - DEFAULT_MIDI_HEADER_SIZE)
        return Pattern(tracks=tracks, resolution=resolution, format=format)

    def parse_track_header(self, midifile):
        # First four bytes are Track header
        magic = midifile.read(4)
        if magic != b'MTrk':
            raise TypeError("Bad track header in MIDI file: " + magic)
        # next four bytes are track size
        trksz = unpack(">L", midifile.read(4))[0]
        return trksz

    def parse_track(self, midifile, track):
        self.RunningStatus = None
        trksz = self.parse_track_header(midifile)
        trackdata = iter(midifile.read(trksz))
        while True:
            try:
                event = self.parse_midi_event(trackdata)
                track.append(event)
            except StopIteration:
                break

    def parse_midi_event(self, trackdata):
        # first datum is varlen representing delta-time
        tick = read_varlen(trackdata)
        # next byte is status message
        stsmsg = trackdata.__next__()
        # is the event a MetaEvent?
        if MetaEvent.is_event(stsmsg):
            cmd = trackdata.__next__()
            if cmd not in EventRegistry.MetaEvents:
                raise Warning("Unknown Meta MIDI Event: " + repr(cmd))
            cls = EventRegistry.MetaEvents[cmd]
            datalen = read_varlen(trackdata)
            data = [trackdata.__next__() for x in range(datalen)]
            return cls(tick=tick, data=data)
        # is this event a Sysex Event?
        elif SysexEvent.is_event(stsmsg):
            data = []
            while True:
                datum = trackdata.__next__()
                if datum == 0xF7:
                    break
                data.append(datum)
            return SysexEvent(tick=tick, data=data)
        # not a Meta MIDI event, must be a general message
        else:
            key = stsmsg & 0xF0
            if key not in EventRegistry.Events:
                assert self.RunningStatus, "Bad byte value"
                data = []
                key = self.RunningStatus & 0xF0
                cls = EventRegistry.Events[key]
                channel = self.RunningStatus & 0x0F
                data.append(stsmsg)
                data += [trackdata.__next__() for x in range(cls.length - 1)]
                return cls(tick=tick, channel=channel, data=data)
            else:
                self.RunningStatus = stsmsg
                cls = EventRegistry.Events[key]
                channel = self.RunningStatus & 0x0F
                data = [trackdata.__next__() for x in range(cls.length)]
                return cls(tick=tick, channel=channel, data=data)
        raise Warning("Unknown MIDI Event: " + repr(stsmsg))

class FileWriter(object):
    def write(self, midifile, pattern):
        self.write_file_header(midifile, pattern)
        for track in pattern:
            self.write_track(midifile, track)

    def write_file_header(self, midifile, pattern):
        # First four bytes are MIDI header
        packdata = pack(">LHHH", 6,
                            pattern.format,
                            len(pattern),
                            pattern.resolution)
        midifile.write(b'MThd')
        midifile.write(packdata)


    def write_track(self, midifile, track):
        buf = b''
        self.RunningStatus = None
        for event in track:
            buf += self.encode_midi_event(event)
        buf = self.encode_track_header(len(buf)) + buf
        midifile.write(buf)

    def encode_track_header(self, trklen):
        return b'MTrk' + pack(">L", trklen)

    def encode_midi_event(self, event):
        ret = b''
        ret += write_varlen(event.tick)
        # is the event a MetaEvent?
        if isinstance(event, MetaEvent):
            ret += bytes([event.statusmsg]) + bytes([event.metacommand])
            ret += write_varlen(len(event.data))
            ret += b''.join([bytes([c]) for c in event.data])
        # is this event a Sysex Event?
        elif isinstance(event, SysexEvent):
            ret += bytes([0xF0])
            ret += b''.join(bytes([c]) for c in event.data)
            ret += bytes([0xF7])
        # not a Meta MIDI event, must be a general message
        elif isinstance(event, Event):
            if not self.RunningStatus or \
                self.RunningStatus.statusmsg != event.statusmsg or \
                self.RunningStatus.channel != event.channel:
                    self.RunningStatus = event
                    ret += bytes([event.statusmsg | event.channel])
            ret += b''.join([bytes([c]) for c in event.data])
        else:
            raise ValueError("Unknown MIDI Event: " + repr(event))
        return ret

def write_midifile(midifile, pattern):
    if isinstance(midifile, str):
        midifile = open(midifile, 'wb')
    writer = FileWriter()
    return writer.write(midifile, pattern)

def read_midifile(midifile):
    if isinstance(midifile, str):
        midifile = open(midifile, 'rb')
    reader = FileReader()
    return reader.read(midifile)
