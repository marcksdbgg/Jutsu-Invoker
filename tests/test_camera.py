import json
from pathlib import Path
import struct
import tempfile
import unittest
from jutsu_invoker.camera import read_message, Packet, Session, LatestFrame, MAX_PACKET_BYTES
from jutsu_invoker.nvdec import PtsMapper
from jutsu_invoker.live import VideoHub, Recorder

class Fragmented:
    def __init__(self,data):self.data=data
    def recv(self,n):
        chunk,self.data=self.data[:min(n,3)],self.data[min(n,3):]
        return chunk

class CameraTests(unittest.TestCase):
    def test_fragmented_session_and_packet_flags(self):
        self.assertEqual(read_message(Fragmented(struct.pack('>III',0x80000000,1280,720))),Session(1280,720))
        flags=123456|(1<<62)|(1<<61)
        p=read_message(Fragmented(struct.pack('>QI',flags,5)+b'hello'))
        self.assertEqual((p.pts_us,p.data,p.config,p.keyframe),(123456,b'hello',True,True))

    def test_truncated_and_oversized_packets_fail(self):
        with self.assertRaises(EOFError):read_message(Fragmented(struct.pack('>QI',0,10)+b'a'))
        for n in (0,MAX_PACKET_BYTES+1):
            with self.assertRaises(ValueError):read_message(Fragmented(struct.pack('>QI',0,n)))
        with self.assertRaises(ValueError):read_message(Fragmented(struct.pack('>III',0x80000000,0,720)))

    def test_latest_decoded_only(self):
        latest=LatestFrame();latest.put('one');latest.put('two')
        self.assertEqual(latest.take(0),'two');self.assertEqual(latest.dropped,1)
        self.assertIsNone(latest.take(0))

    def test_relative_clock_detects_queue_growth_and_reset(self):
        clock=PtsMapper()
        self.assertEqual(clock.map(1_000_000,5000),5000)
        self.assertEqual(clock.map(1_033_000,5083),5033)
        self.assertEqual(clock.map(1_066_000,5060),5060)
        with self.assertRaises(ValueError):clock.map(1_066_000,5100)
        self.assertEqual(PtsMapper().map(0,999),999)

    def test_preview_batches_start_at_keyframe_and_recover_after_lag(self):
        hub=VideoHub()
        hub.publish(Packet(0,b'config',True,False,0))
        hub.publish(Packet(1,b'delta',False,False,0))
        self.assertEqual(hub.batch()[0],b'')
        key=Packet(2,b'key',False,True,0);hub.publish(key)
        data,cursor,generation=hub.batch()
        self.assertEqual(data,hub.wire(Packet(0,b'config',True,False,0))+hub.wire(key))
        self.assertEqual(hub.batch(cursor,generation)[0],b'')
        delta=Packet(3,b'delta',False,False,0);hub.publish(delta)
        self.assertEqual(hub.batch(cursor,generation)[0],hub.wire(delta))
        for i in range(70):hub.publish(Packet(i+4,b'next',False,i%30==0,0))
        self.assertEqual(len(hub.history),64)
        batch=hub.batch(cursor,generation)[0]
        self.assertEqual(batch[12:18],b'config')
        hub.reset();self.assertIsNone(hub.config);self.assertNotEqual(hub.generation,generation)

    def test_recording_keyframe_offsets_and_timestamps(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Recorder(Path(folder),'unknown','back',30,b'config')
            r.packet(Packet(0,b'delta',False,False,0))
            r.packet(Packet(100,b'key',False,True,0))
            r.packet(Packet(200,b'delta',False,False,0))
            path=Path(r.close('test'))
            self.assertEqual(path.read_bytes(),b'configkeydelta')
            meta=json.loads(path.with_suffix('.json').read_text())
            self.assertEqual(meta['first_pts_us'],100);self.assertEqual(meta['frames'],2)
            self.assertEqual([p['offset_bytes'] for p in meta['packets']],[6,9])
            self.assertEqual([p['pts_us'] for p in meta['packets']],[100,200])
            with self.assertRaises(ValueError):Recorder(Path(folder),'fake','back',30,None)

if __name__=='__main__':unittest.main()
