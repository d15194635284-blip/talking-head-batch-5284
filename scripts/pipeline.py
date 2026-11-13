"""Local speech-led batch editing. Run --help for commands."""

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from customization import absolute_file, music_choice, read_srt, style_header, validate_style


SKILL = Path(__file__).resolve().parents[1]
DEFAULTS = SKILL / 'assets' / 'style.json'
MEDIA_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.m4v', '.webm'}

# A machine-specific module directory can reuse an existing compatible OpenCV build.
local_settings = SKILL / 'local-settings.json'
if local_settings.is_file():
    local = json.loads(local_settings.read_text(encoding='utf-8-sig'))
    if local.get('python_module_dir'):
        sys.path.insert(0, local['python_module_dir'])


def run(arguments, cwd=None):
    result = subprocess.run(
        [str(value) for value in arguments], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace',
    )
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode})\n{result.stderr[-5000:]}')
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def probe(path):
    info = json.loads(run([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path,
    ]).stdout)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    return {'duration': float(info['format']['duration']), 'video': video, 'audio': audio}


def doctor(args):
    checks = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe', 'whisper')}
    checks['python'] = sys.executable
    try:
        import cv2
        checks['opencv'] = hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'VideoCapture')
    except ImportError:
        checks['opencv'] = False
    checks['numpy'] = importlib.util.find_spec('numpy') is not None
    if checks['ffmpeg']:
        filters = run(['ffmpeg', '-hide_banner', '-filters']).stdout
        checks['ass_filter'] = ' ass ' in filters
    print(json.dumps(checks, ensure_ascii=False, indent=2))


def prepare(args):
    source = Path(args.source).resolve()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not source.is_dir():
        raise ValueError(f'Missing source directory: {source}')
    files = sorted(p for p in source.iterdir() if p.suffix.lower() in MEDIA_EXTENSIONS)
    if args.limit:
        files = files[:args.limit]
    if not files:
        raise ValueError('No supported video files found')
    for index, media in enumerate(files, 1):
        key = f'{index:03d}_{hashlib.sha256(media.name.encode()).hexdigest()[:8]}'
        folder = work / key
        folder.mkdir(exist_ok=True)
        signature = fingerprint(media)
        manifest = folder / 'analysis.json'
        transcription_settings = {'model': args.model, 'prompt': args.prompt}
        if manifest.exists():
            previous = read_json(manifest)
            cached_files = [folder / name for name in ('speech.json', 'speech.wav', 'contact.jpg')]
            if (previous.get('source_sha256') == signature
                    and previous.get('transcription_settings') == transcription_settings
                    and all(path.is_file() for path in cached_files)):
                print(f'REUSE {media.name}', flush=True)
                continue
        info = probe(media)
        if not info['video'] or not info['audio']:
            write_json(manifest, {'source': str(media), 'source_sha256': signature,
                                 'review': 'Missing video or audio stream', 'info': info})
            continue
        audio = folder / 'speech.wav'
        run(['ffmpeg', '-y', '-v', 'error', '-i', media, '-vn', '-ar', '16000', '-ac', '1', audio])
        model_path = Path(args.model_dir).expanduser() / (args.model + '.pt')
        if not model_path.is_file():
            raise ValueError(f'Local Whisper model missing: {model_path}. Install or copy it before transcription.')
        command = [args.whisper, audio, '--model', args.model, '--model_dir', model_path.parent,
                   '--device', 'cpu', '--fp16', 'False', '--language', 'zh',
                   '--word_timestamps', 'True', '--output_format', 'json',
                   '--output_dir', folder, '--threads', str(args.threads), '--verbose', 'False']
        if args.prompt:
            command.extend(['--initial_prompt', args.prompt])
        print(f'TRANSCRIBE {media.name}', flush=True)
        run(command)
        analysis = run(['ffmpeg', '-hide_banner', '-i', media,
                        '-af', 'silencedetect=n=-30dB:d=0.23',
                        '-vf', 'freezedetect=n=-60dB:d=0.25', '-f', 'null', os.devnull])
        interval = max(.1, info['duration'] / 5)
        run(['ffmpeg', '-y', '-v', 'error', '-i', media, '-vf',
             f'fps=1/{interval}:start_time=0,scale=144:256:force_original_aspect_ratio=decrease,'
             'pad=144:256:(ow-iw)/2:(oh-ih)/2,tile=5x1', '-frames:v', '1', folder / 'contact.jpg'])
        write_json(manifest, {
            'source': str(media), 'source_sha256': signature, 'info': info,
            'transcription_settings': transcription_settings,
            'transcript': str(folder / 'speech.json'), 'contact': str(folder / 'contact.jpg'),
            'silence_and_freeze': [line for line in analysis.stderr.splitlines()
                                   if 'silence_' in line or 'freeze_' in line],
        })
    print(f'Prepared {len(files)} sources in {work}')


def validate_item(item):
    source = Path(item['source']).resolve()
    info = probe(source)
    if not info['video'] or not info['audio']:
        raise ValueError(f'Video and audio required: {source}')
    if not re.fullmatch(r'[\w\-\u4e00-\u9fff]+', item['id']):
        raise ValueError('Item id must contain letters, digits, hyphens or underscores')
    speed = float(item['speed'])
    if not math.isfinite(speed) or not .5 <= speed <= 2:
        raise ValueError('Speed must be between 0.5 and 2')
    previous = 0.0
    for start, end in item['keep']:
        if not all(math.isfinite(v) for v in (start, end)):
            raise ValueError('Non-finite cut time')
        if start < previous or end <= start or end > info['duration'] + .03:
            raise ValueError(f'Invalid or overlapping keep range: {start}, {end}')
        previous = end
    if not item['keep']:
        raise ValueError('At least one keep range required')
    cue_limit = info['duration']
    if item.get('subtitle_timebase', 'source') == 'output':
        cue_limit = sum(end-start for start, end in item['keep']) / speed
    for start, end, text in item['cues']:
        if not 0 <= start < end <= cue_limit + .03 or not isinstance(text, str):
            raise ValueError('Invalid subtitle cue')
    if not 0 <= item.get('overall', 0) <= .06 or not 0 <= item.get('face', 0) <= 20:
        raise ValueError('Brightness parameters out of range')
    if not 0 <= item.get('speaker_x', .5) <= 1:
        raise ValueError('Speaker position must be between 0 and 1')
    top, bottom = item.get('face_roi', [.15, .65])
    if not 0 <= top < bottom <= 1:
        raise ValueError('Face ROI must be inside the frame')
    if (not isinstance(item.get('review', []), list)
            or not all(isinstance(note, str) for note in item.get('review', []))):
        raise ValueError('Review must be an array of strings')
    return source, info


def ass_time(value):
    whole, hundredths = divmod(round(value * 100), 100)
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{hundredths:02d}'


def escaped_text(text):
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')


def make_subtitles(item, style, duration, folder):
    template = (SKILL / 'assets' / 'captions.ass').read_text(encoding='utf-8-sig')
    header = style_header(template, style)
    events = []
    def line(start, end, name, y, text):
        events.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},{name},,0,0,0,,{{\\pos(360,{y})}}{escaped_text(text)}\n')
    positions = item.get('title_y', style['title_y'])
    if style.get('show_title', True):
        if len(positions) != 3:
            raise ValueError('Three title positions required')
        for y, text in zip(positions, style['title']):
            line(0, duration, 'Title', y, text)
    if style.get('show_cta', True):
        line(0, duration, 'CTA', item.get('cta_y', style['cta_y']), style['cta'])
    mapped = []
    cues = item['cues'] if style.get('show_captions', True) else []
    for start, end, text in cues:
        if item.get('subtitle_timebase', 'source') == 'output':
            mapped.append((start, end, text))
            continue
        offset = 0
        for left, right in item['keep']:
            a, b = max(start, left), min(end, right)
            if b > a:
                mapped.append(((offset + a-left)/item['speed'],
                               (offset + b-left)/item['speed'], text))
            offset += right-left
    for start, end, text in sorted(mapped):
        line(start, end, 'Caption', item.get('caption_y', style['caption_y']), text)
    (folder / 'captions.ass').write_text(header + ''.join(events), encoding='utf-8-sig')


def cut_video(source, item, folder):
    filters = []
    for index, (start, end) in enumerate(item['keep']):
        filters.extend([
            f'[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{index}]',
            f'[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,'
            f'afade=t=in:d=0.006,afade=t=out:st={max(0,end-start-.006)}:d=0.006[a{index}]',
        ])
    labels = ''.join(f'[v{i}][a{i}]' for i in range(len(item['keep'])))
    filters.extend([
        f'{labels}concat=n={len(item["keep"])}:v=1:a=1[v][a]',
        f'[v]setpts=PTS/{item["speed"]},fps=30,'
        'scale=720:1280:force_original_aspect_ratio=decrease,'
        'pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[outv]',
        f'[a]atempo={item["speed"]}[outa]',
    ])
    destination = folder / 'cut.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-i', source, '-filter_complex', ';'.join(filters),
         '-map', '[outv]', '-map', '[outa]', '-c:v', 'libx264', '-preset', 'fast',
         '-crf', '17', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', destination])
    return destination


def mean_level(path, duration, loop=False):
    input_options = ['-stream_loop', '-1'] if loop else []
    log = run(['ffmpeg', '-hide_banner', *input_options, '-i', path, '-t', duration,
               '-vn', '-af', 'volumedetect', '-f', 'null', os.devnull]).stderr
    value = float(re.search(r'mean_volume:\s*([-\w.]+)', log)[1])
    if not math.isfinite(value):
        raise ValueError(f'Cannot measure silent audio: {path}')
    return value


def render_item(item, style, output, work, music, rebuild):
    source, info = validate_item(item)
    folder = work / item['id']
    folder.mkdir(parents=True, exist_ok=True)
    final = output / (item['id'] + ('_待复核' if item.get('review') else '_成片') + '.mp4')
    receipt = folder / 'result.json'
    identity = {'source': fingerprint(source), 'item': item, 'style': style,
                'music': {'sha256': fingerprint(music['file']), **music} if music else None,
                'pipeline': 2}
    if final.exists() and not rebuild:
        if receipt.exists():
            record = read_json(receipt)
            if record['identity'] == identity and record.get('sha256') == fingerprint(final):
                print(f'REUSE {final.name}', flush=True)
                return record
        raise FileExistsError(f'{final} exists with different settings. Use a new id or --rebuild.')
    duration = sum(end-start for start, end in item['keep']) / item['speed']
    make_subtitles(item, style, duration, folder)
    cut = cut_video(source, item, folder)
    warnings = []
    if item.get('face', 0) or item.get('overall', 0):
        from portrait import render_grade
        cut, warnings = render_grade(cut, folder, item)
    video = probe(cut)
    duration = float(video['video']['duration'])
    temporary = folder / 'encoded.mp4'
    command = ['ffmpeg', '-y', '-v', 'error', '-i', cut]
    filters = '[0:v]ass=captions.ass[v]'
    gain = None
    if music:
        gain = mean_level(cut, duration) - music['gap_db'] - mean_level(music['file'], duration, loop=True)
        command.extend(['-stream_loop', '-1', '-i', music['file']])
        fade = min(music['fade_out'], duration)
        fade_filter = f',afade=t=out:st={duration-fade}:d={fade}' if fade else ''
        filters += (f';[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume={gain:.3f}dB{fade_filter}[m];'
                    '[0:a][m]amix=inputs=2:duration=first:normalize=0,'
                    'alimiter=limit=0.97:level=0:latency=1[a]')
    command.extend(['-filter_complex', filters, '-map', '[v]', '-map', '[a]' if music else '0:a:0',
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', temporary])
    run(command, cwd=folder)
    run(['ffmpeg', '-v', 'error', '-xerror', '-i', temporary, '-f', 'null', os.devnull])
    quality = probe(temporary)
    if abs(float(quality['audio']['duration']) - float(quality['video']['duration'])) > .15:
        raise ValueError('Output audio/video duration mismatch')
    run(['ffmpeg', '-y', '-v', 'error', '-i', temporary, '-vf',
         f'fps=1/{max(.05,duration/5)}:start_time=0,scale=180:320,tile=5x1',
         '-frames:v', '1', folder / 'review.jpg'])
    # Copy to the destination filesystem before atomic replacement.
    staging = final.with_suffix('.partial.mp4')
    shutil.copyfile(temporary, staging)
    staging.replace(final)
    record = {'identity': identity, 'output': str(final), 'sha256': fingerprint(final),
              'duration': duration, 'source_duration': info['duration'],
              'music_gain_db': gain, 'warnings': warnings, 'item': item,
              'music': music, 'style': style,
              'review_image': str(folder / 'review.jpg')}
    write_json(receipt, record)
    print(f'FINISHED {final}', flush=True)
    return record


def report(output, records, failures):
    lines = ['# 口播批剪 5284 成片清单', '',
             '以下是本轮所选素材的处理结果。删减时间均为原素材时间。', '']
    for record in records:
        item = record['item']
        cursor = 0
        deleted = []
        for start, end in item['keep']:
            if start > cursor + .01:
                deleted.append(f'{cursor:.2f}–{start:.2f} 秒')
            cursor = end
        if record['source_duration'] > cursor + .01:
            deleted.append(f'{cursor:.2f}–{record["source_duration"]:.2f} 秒')
        lines.extend([f'## {item["id"]}', '', f'[播放成片]({Path(record["output"]).as_posix()})',
                      f'- 原片 {item["source"]}',
                      f'- 时长 {record["duration"]:.2f} 秒，倍速 {item["speed"]:.2f}',
                      '- 删除 ' + ('、'.join(deleted) or '无'),
                      '- 原因 ' + item.get('cut_notes', '见剪辑计划'),
                      '- 提亮 ' + f'整体 {item.get("overall",0)}，脸部 {item.get("face",0)}',
                      '- 配乐 ' + (f'{record["music"]["file"]}，低于人声 {record["music"]["gap_db"]} dB，淡出 {record["music"]["fade_out"]} 秒'
                                  if record['music_gain_db'] is not None else '无配乐'),
                      '- 待复核 ' + ('；'.join(item.get('review', []) + record['warnings']) or '逐条抽查剪接与字幕'), ''])
    for failure in failures:
        lines.extend([f'## 处理失败 · {failure["id"]}', '', failure['error'], ''])
    (output / '本轮成片清单.md').write_text('\n'.join(lines), encoding='utf-8')


def render_batch(args):
    output = Path(args.output).resolve()
    work = Path(args.work).resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    plan = read_json(args.plan)
    plan_base = Path(args.plan).resolve().parent
    style = read_json(DEFAULTS)
    style.update(plan.get('style', {}))
    if args.style:
        style.update(read_json(args.style))
    validate_style(style)
    music_value = plan.get('music')
    if args.music:
        music_value = {'file': str(Path(args.music).resolve())}
    if music_value is not None:
        music_value = {'file': music_value} if isinstance(music_value, str) else dict(music_value)
        if args.music_gap is not None:
            music_value['gap_db'] = args.music_gap
        if args.music_fade_out is not None:
            music_value['fade_out'] = args.music_fade_out
    items = plan['items'][:args.limit] if args.limit else plan['items']
    ids = [item['id'] for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate item ids')
    if any(absolute_file(item['source'], plan_base).parent == output for item in items):
        raise ValueError('Use different source and output directories')
    records, failures = [], []
    for item in items:
        try:
            item = dict(item)
            item['source'] = str(absolute_file(item['source'], plan_base))
            item_style = {**style, **item.get('style', {})}
            for key in ('title_y', 'cta_y', 'caption_y'):
                if key in item:
                    item_style[key] = item[key]
            validate_style(item_style)
            subtitles = item.get('subtitles')
            if not item_style.get('show_captions', True):
                item['cues'] = []
                item['subtitle_timebase'] = 'source'
            elif subtitles:
                file = absolute_file(subtitles['file'], plan_base)
                item['cues'] = read_srt(file)
                item['subtitle_sha256'] = fingerprint(file)
                item['subtitle_timebase'] = subtitles.get('timebase', 'source')
            item.setdefault('cues', [])
            if item_style.get('show_captions', True) and not item['cues']:
                raise ValueError('Captions enabled but no cues or SRT supplied')
            if item.get('subtitle_timebase', 'source') not in ('source', 'output'):
                raise ValueError('Subtitle timebase must be source or output')
            choice = None if args.no_music else item.get('music', music_value)
            music = music_choice(choice, plan_base)
            records.append(render_item(item, item_style, output, work, music, args.rebuild))
        except Exception as error:
            failures.append({'id': item['id'], 'error': str(error)})
            print(f'FAILED {item["id"]}: {error}', flush=True)
        write_json(output / '本轮处理结果.json', {'results': records, 'failures': failures})
        report(output, records, failures)
    if failures:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('doctor', help='Check installed local tools')
    check.set_defaults(function=doctor)
    prep = commands.add_parser('prepare', help='Transcribe locally and collect review material')
    prep.add_argument('--source', required=True)
    prep.add_argument('--work', required=True)
    prep.add_argument('--model', default='small')
    prep.add_argument('--model-dir', default=str(Path.home() / '.cache' / 'whisper'))
    prep.add_argument('--whisper', default='whisper')
    prep.add_argument('--threads', type=int, default=6)
    prep.add_argument('--prompt', default='')
    prep.add_argument('--limit', type=int)
    prep.set_defaults(function=prepare)
    render = commands.add_parser('render', help='Render reviewed per-video decisions')
    render.add_argument('--plan', required=True)
    render.add_argument('--output', required=True)
    render.add_argument('--work', required=True)
    music_options = render.add_mutually_exclusive_group()
    music_options.add_argument('--music', help='Local BGM file for this batch')
    music_options.add_argument('--no-music', action='store_true', help='Disable BGM for all items')
    render.add_argument('--music-gap', type=float, help='Average BGM level below voice, default 6 dB')
    render.add_argument('--music-fade-out', type=float, help='BGM fade-out seconds, default 0.5')
    render.add_argument('--style', help='JSON style overrides for this run')
    render.add_argument('--limit', type=int)
    render.add_argument('--rebuild', action='store_true')
    render.set_defaults(function=render_batch)
    args = parser.parse_args()
    args.function(args)


if __name__ == '__main__':
    main()
