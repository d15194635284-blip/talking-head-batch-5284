"""Per-run music choices, caption styles and SRT sidecars."""

from pathlib import Path
import math
import re


def validate_style(style):
    allowed = {'title', 'title_y', 'cta', 'cta_y', 'caption_y', 'font',
               'show_title', 'show_cta', 'show_captions'}
    for group in ('title', 'cta', 'caption'):
        allowed.update(group + '_' + field for field in ('font', 'size', 'color', 'outline_color', 'outline'))
    if style.keys() - allowed:
        raise ValueError(f'Unknown style fields: {sorted(style.keys() - allowed)}')
    for flag in ('show_title', 'show_cta', 'show_captions'):
        if not isinstance(style.get(flag, True), bool):
            raise ValueError(f'{flag} must be true or false')
    if style.get('show_title', True):
        if len(style['title']) != 3 or not all(isinstance(text, str) for text in style['title']):
            raise ValueError('Title must contain exactly three text lines')
        if len(style['title_y']) != 3:
            raise ValueError('Three title positions required')
    for name in ('title', 'cta', 'caption'):
        size = style[name + '_size']
        if not isinstance(size, (int, float)) or not math.isfinite(size) or not 8 <= size <= 160:
            raise ValueError(f'{name}_size must be between 8 and 160')
        font = style.get(name + '_font', style['font'])
        if not isinstance(font, str) or not font.strip() or any(c in font for c in ',\r\n'):
            raise ValueError('Font must be an installed font family name')
        for suffix in ('color', 'outline_color'):
            value = style[name + '_' + suffix]
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
                raise ValueError(f'{name}_{suffix} must use #RRGGBB')
        outline = style[name + '_outline']
        if not isinstance(outline, (int, float)) or not math.isfinite(outline) or not 0 <= outline <= 12:
            raise ValueError('Text outline must be between 0 and 12')
    coordinates = style['title_y'] + [style['cta_y'], style['caption_y']]
    if any(not isinstance(y, (int, float)) or not math.isfinite(y) or not 0 <= y < 1280 for y in coordinates):
        raise ValueError('Text positions must be within the 1280-pixel canvas')
    if not isinstance(style['cta'], str):
        raise ValueError('CTA must be text')


def ass_color(rgb):
    return '&H00' + rgb[5:7] + rgb[3:5] + rgb[1:3]


def style_header(template, style):
    lines = []
    for line in template.splitlines():
        if line.startswith('Style: '):
            fields = line[7:].split(',')
            name = fields[0].lower()
            fields[1] = style.get(name + '_font', style['font'])
            fields[2] = str(style[name + '_size'])
            fields[3] = fields[4] = ass_color(style[name + '_color'])
            fields[5] = ass_color(style[name + '_outline_color'])
            fields[16] = str(style[name + '_outline'])
            line = 'Style: ' + ','.join(fields)
        lines.append(line)
    return '\n'.join(lines) + '\n'


def read_srt(path):
    text = Path(path).read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()
    cues = []
    timestamp = r'(\d+):(\d{2}):(\d{2})[,.](\d{3})'
    for block in re.split(r'\n[ \t]*\n', text):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if len(lines) < 2:
            raise ValueError(f'Invalid SRT block in {path}')
        match = re.fullmatch(timestamp + r'\s*-->\s*' + timestamp, lines[0].strip())
        if not match:
            raise ValueError(f'Invalid SRT timestamp: {lines[0]}')
        values = list(map(int, match.groups()))
        start = values[0]*3600 + values[1]*60 + values[2] + values[3]/1000
        end = values[4]*3600 + values[5]*60 + values[6] + values[7]/1000
        if values[1] >= 60 or values[2] >= 60 or values[5] >= 60 or values[6] >= 60 or end <= start:
            raise ValueError('Invalid SRT time range')
        cues.append([start, end, '\n'.join(lines[1:])])
    if not cues:
        raise ValueError(f'No subtitle cues found: {path}')
    return cues


def absolute_file(value, base):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def music_choice(value, base):
    if value is None:
        return None
    choice = {'file': value} if isinstance(value, str) else dict(value)
    unknown = choice.keys() - {'file', 'gap_db', 'fade_out'}
    if unknown:
        raise ValueError(f'Unknown music settings: {sorted(unknown)}')
    choice.setdefault('gap_db', 6)
    choice.setdefault('fade_out', .5)
    choice['file'] = str(absolute_file(choice['file'], base))
    if not Path(choice['file']).is_file():
        raise ValueError(f'Missing music: {choice["file"]}')
    for name in ('gap_db', 'fade_out'):
        number = choice[name]
        if not isinstance(number, (float, int)) or not math.isfinite(number):
            raise ValueError(f'Music {name} must be a finite number')
    if not 0 <= choice['gap_db'] <= 60 or not 0 <= choice['fade_out'] <= 30:
        raise ValueError('Music gap or fade duration out of range')
    return choice
