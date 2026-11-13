"""Regression checks for configurable captions and music. Uses only the standard library."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from customization import music_choice, read_srt, validate_style
from pipeline import make_subtitles


class CustomizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.style = json.loads((ROOT / 'assets' / 'style.json').read_text(encoding='utf-8'))

    def tearDown(self):
        self.directory.cleanup()

    def item(self, timebase):
        return {'keep': [[.5, 1.5], [2, 3]], 'speed': 1.25,
                'cues': [[1, 2, '测试字幕']], 'subtitle_timebase': timebase}

    def test_original_timestamps_are_cut_and_retimed(self):
        make_subtitles(self.item('source'), self.style, 3, self.folder)
        text = (self.folder / 'captions.ass').read_text(encoding='utf-8-sig')
        self.assertIn('0:00:00.40,0:00:00.80,Caption', text)

    def test_output_timestamps_remain_on_output_timeline(self):
        make_subtitles(self.item('output'), self.style, 3, self.folder)
        text = (self.folder / 'captions.ass').read_text(encoding='utf-8-sig')
        self.assertIn('0:00:01.00,0:00:02.00,Caption', text)

    def test_custom_style_and_switches_reach_ass(self):
        self.style.update(show_title=False, show_cta=False, caption_color='#E9DCC8',
                          caption_size=44, caption_font='Test Font', caption_y=980)
        validate_style(self.style)
        make_subtitles(self.item('output'), self.style, 3, self.folder)
        text = (self.folder / 'captions.ass').read_text(encoding='utf-8-sig')
        self.assertIn('Style: Caption,Test Font,44,&H00C8DCE9', text)
        dialogue = [line for line in text.splitlines() if line.startswith('Dialogue:')]
        self.assertEqual(len(dialogue), 1)
        self.assertIn(r'\pos(360,980)', dialogue[0])

    def test_srt_bom_and_multiline(self):
        file = self.folder / '字幕.srt'
        file.write_text('1\n00:00:01,200 --> 00:00:02,400\n第一行\n第二行\n', encoding='utf-8-sig')
        self.assertEqual(read_srt(file), [[1.2, 2.4, '第一行\n第二行']])

    def test_invalid_configuration_is_reported(self):
        self.style['caption_color'] = 'invalid'
        with self.assertRaises(ValueError):
            validate_style(self.style)
        with self.assertRaises(ValueError):
            music_choice({'file': 'missing.mp3', 'gap_db': 6}, self.folder)

    def test_music_disabled_and_relative_path(self):
        self.assertIsNone(music_choice(None, self.folder))
        (self.folder / 'music.wav').touch()
        choice = music_choice({'file': 'music.wav', 'gap_db': 8, 'fade_out': 1}, self.folder)
        self.assertEqual(choice['file'], str((self.folder / 'music.wav').resolve()))
        self.assertEqual(choice['gap_db'], 8)


if __name__ == '__main__':
    unittest.main()
