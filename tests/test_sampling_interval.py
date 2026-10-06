import tempfile, unittest
from pathlib import Path
from fractions import Fraction
import av, numpy as np
from caption_system.video.sampling import sample

class SamplingInterval(unittest.TestCase):

    def test_full_video_respects_original_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.mp4'
            with av.open(str(path), 'w') as out:
                stream = out.add_stream('libx264', rate=10)
                stream.width = 64
                stream.height = 64
                stream.pix_fmt = 'yuv420p'
                stream.time_base = Fraction(1, 10)
                for i in range(50):
                    frame = av.VideoFrame.from_ndarray(np.full((64, 64, 3), i, dtype=np.uint8), format='rgb24')
                    frame.pts = i
                    frame.time_base = Fraction(1, 10)
                    for packet in stream.encode(frame):
                        out.mux(packet)
                for packet in stream.encode():
                    out.mux(packet)
            frames, times, sizes, duration = sample(path, 4, 2.0, 3.0)
            self.assertEqual(duration, 1.0)
            self.assertTrue(all((0 <= t < 1 for t in times)))
            self.assertLess(abs(times[0]), 0.01)
            self.assertTrue(all((18 <= np.asarray(f).mean() <= 32 for f in frames)))
