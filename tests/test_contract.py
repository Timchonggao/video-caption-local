import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caption_system.results.contract import validate
from caption_system.video.sampling import sample

class ContractTests(unittest.TestCase):

    def value(self):
        return {'generated_caption': 'A person picks up a cup.', 'scene': 'Table', 'entities': [{'id': 'p'}, {'id': 'c'}], 'actions': [{'start_s': 0, 'end_s': 1, 'actor': 'p', 'object': 'c', 'evidence_times_s': [0, 1]}], 'state_changes': [], 'observed_outcome': 'Cup held', 'uncertainties': []}

    def test_valid_observation(self):
        validate(self.value(), 2, [0, 1])

    def test_reject_invented_evidence(self):
        v = self.value()
        v['actions'][0]['evidence_times_s'] = [0.5]
        with self.assertRaises(ValueError):
            validate(v, 2, [0, 1])

    def test_reject_unknown_entity(self):
        v = self.value()
        v['actions'][0]['object'] = 'missing'
        with self.assertRaises(ValueError):
            validate(v, 2, [0, 1])

    def test_reject_outside_clip(self):
        v = self.value()
        v['actions'][0]['end_s'] = 3
        with self.assertRaises(ValueError):
            validate(v, 2, [0, 1])
if __name__ == '__main__':
    unittest.main()
