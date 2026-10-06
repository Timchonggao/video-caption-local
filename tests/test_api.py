import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from caption_system.models.api import payload, parse

class ApiTests(unittest.TestCase):

    def test_doubao_images_and_pixel_budget(self):
        body, sizes = payload('doubao', 'test-model', 'prompt', [Image.new('RGB', (1600, 1300))], [0.5], 100000, 100)
        self.assertLessEqual(sizes[0][0] * sizes[0][1], 100000)
        parts = body['messages'][0]['content']
        self.assertIn('0.500000', parts[1]['text'])
        self.assertTrue(parts[2]['image_url']['url'].startswith('data:image/jpeg;base64,'))

    def test_gemini_content_and_thought_filter(self):
        body, _ = payload('gemini', 'test-model', 'prompt', [Image.new('RGB', (100, 100))], [1], 10000, 100)
        self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
        text, usage = parse('gemini', {'candidates': [{'content': {'parts': [{'text': 'private reasoning', 'thought': True}, {'text': '{}'}]}}], 'usageMetadata': {'totalTokenCount': 10}})
        self.assertEqual(text, '{}')
        self.assertEqual(usage['totalTokenCount'], 10)
if __name__ == '__main__':
    unittest.main()
