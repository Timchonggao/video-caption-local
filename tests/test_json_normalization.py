import importlib.util,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'scripts/normalize_window_json.py'
spec=importlib.util.spec_from_file_location('normalization',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class JsonNormalizationTests(unittest.TestCase):
    def test_complete_object_plus_one_quote_only(self):
        self.assertEqual(module.trailing_quote_object('{"generated_caption":"Visible"}"'),{'generated_caption':'Visible'})
        for text in ['{"a":1}', '{"a":1} trailing', '{"a":1}{"b":2}', '{"a":', '[1]"']:
            with self.assertRaises(ValueError):module.trailing_quote_object(text)
