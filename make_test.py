#!/usr/bin/env python3
"""
TOEIC Speaking full test (Q1-11) builder: audio (Kokoro TTS) + video, from one config file.

    python make_test.py config/test_moi.json              # audio + video
    python make_test.py config/test_moi.json --audio-only # MP3 + timeline only
    python make_test.py config/test_moi.json --video-only # video from the audio already in output/

An optional "parts": [2, 3] in the config builds only those parts (consecutive ones; default all five).
The timeline (every gap, timer, tick and ding) copies the measured timing of SPEAKING_TEST_6.
Only the spoken content and the on-screen content come from the config file.
"""
import argparse, csv, json, math, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

import settings

ROOT = settings.ROOT
ASSETS = ROOT / 'assets'
MODELS = settings.MODELS_DIR
OUTPUT = settings.OUTPUT_DIR
SR = 44100
FPS = 25
VOICE, SPEED, LANG = settings.VOICE, settings.SPEED, settings.LANG
REF_RMS = 0.12662                     # active-speech RMS of the original narrator
MODEL_FILES = {
    'kokoro-v1.0.onnx': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx',
    'voices-v1.0.bin': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin',
}


class BuildError(Exception):
    """A problem the user can fix: missing content, missing image, no ffmpeg..."""


def log(msg):
    enc = sys.stdout.encoding or 'utf-8'        # a piped stdout on Windows is cp1252: never fail on a test name
    print(msg.encode(enc, 'replace').decode(enc), flush=True)


def ffmpeg_exe():
    exe = shutil.which('ffmpeg')
    if exe: return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise BuildError('Khong tim thay ffmpeg. Chay: pip install imageio-ffmpeg')


def run_ffmpeg(args, total=None, progress=None):
    """Run ffmpeg. With `progress`, it is called with the encoded fraction of `total` seconds."""
    cmd = [ffmpeg_exe(), '-v', 'error', '-y', '-progress', 'pipe:1', '-nostats'] + args
    with tempfile.TemporaryFile('w+', encoding='utf-8', errors='replace') as err:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        for line in p.stdout:
            k, _, v = line.strip().partition('=')
            if progress and total and k == 'out_time_us' and v.isdigit(): progress(min(1.0, int(v) / 1e6 / total))
        if p.wait():
            err.seek(0); raise BuildError('ffmpeg loi: ' + (err.read().strip()[-500:] or f'ma thoat {p.returncode}'))


# =====================================================================================
# 1. AUDIO
# =====================================================================================
FIXED_SPOKEN = {
    'P1_D1': 'In this part, you will be asked to read aloud the text on the screen.',
    'P1_D2': 'You will have forty-five seconds to prepare.',
    'P1_D3': 'Then you will have forty-five seconds to read the text out loud.',
    'BP': 'Begin preparing now.',
    'BR': 'Begin reading aloud now.',
    'BS': 'Begin speaking now.',
    'P2_D1': 'In this part, you will be asked to describe the picture on the screen in as much detail as possible.',
    'P2_D2': 'You will have forty-five seconds to prepare your response.',
    'P2_D3': 'Then you will have thirty seconds to talk about the picture.',
    'P3_D1': 'In this part, you will be asked to answer three questions.',
    'P3_D2': 'After listening to each question, you will have three seconds to prepare your response.',
    'P3_D3': 'You will have fifteen seconds to respond to questions five and six, and thirty seconds to respond to question seven.',
    'P4_D1': 'In this part, you will be asked to refer to information on the screen in order to answer three questions.',
    'P4_D2': 'The information will be shown for forty-five seconds before you hear the questions.',
    'P4_D3': 'After listening to each question, you will have three seconds to prepare your response.',
    'P4_D4': 'You will have fifteen seconds to respond to questions eight and nine, and thirty seconds to respond to question ten.',
    'P5_D1': 'In this part, you will be asked to give your thoughts on a certain topic.',
    'P5_D2': 'It is to your advantage to speak as much as possible in the time provided.',
    'P5_D3': 'You will have forty-five seconds to prepare your response and sixty seconds to speak.',
}
CONTENT_KEYS = ['Q5_INTRO', 'Q5', 'Q6', 'Q7_A', 'Q7_B', 'Q8_INTRO', 'Q8', 'Q9', 'Q10', 'Q11_A', 'Q11_B', 'Q11_C']
OPTIONAL_KEYS = {'Q7_B'}                   # may be left empty: the clip and its gap are dropped

# Timeline measured from SPEAKING_TEST_6 (seconds).
#   say(key, gap)            -> voice clip, `gap` s after the previous clip/beep ends
#   say(key, at=(anchor, s)) -> voice clip at an anchor: 'abs', 'next' (timer end) or 'ding'
#   beep(gap)                -> 0.261 s tone
#   window(W, ticks_at, next_at, kind) -> timer; times are s after the BEEP ENDS
#       ticks_at = where the tick clip is placed, next_at = next voice ('v') / DING ('d') / end ('end')
#   Parts: 1 = Q1-2, 2 = Q3-4, 3 = Q5-7, 4 = Q8-10, 5 = Q11. Each part opens with its own directions,
#   so a run of consecutive parts plays exactly as it does inside the full test.
PART_IDS = (1, 2, 3, 4, 5)
SEQ = {n: [] for n in PART_IDS}
_part = 1
def part(n):
    global _part; _part = n
def say(key, gap=None, at=None, label=None): SEQ[_part].append(('say', key, gap, at, label or key))
def beep(gap): SEQ[_part].append(('beep', gap))
def window(w, ticks_at, next_at, nk, label): SEQ[_part].append(('win', w, ticks_at, next_at, nk, label))
NEXT = ('next', 0)

part(1)
say('P1_D1', at=('abs', 0.0)); say('P1_D2', 0.515); say('P1_D3', 0.694)
say('BP', 1.219, label='Q1 Begin preparing'); beep(0.634); window(45, 41.053, 45.034, 'v', 'Q1 prep')
say('BR', at=NEXT, label='Q1 Begin reading'); beep(0.587); window(45, 41.236, 46.036, 'd', 'Q1 response')
say('BP', at=('ding', 0.438), label='Q2 Begin preparing'); beep(0.634); window(45, 41.247, 45.224, 'v', 'Q2 prep')
say('BR', at=NEXT, label='Q2 Begin reading'); beep(0.588); window(45, 41.463, 45.530, 'd', 'Q2 response')
part(2)
say('P2_D1', at=('ding', 1.002)); say('P2_D2', 0.861); say('P2_D3', 0.494)
say('BP', 1.148, label='Q3 Begin preparing'); beep(0.634); window(45, 40.963, 44.944, 'v', 'Q3 prep')
say('BS', at=NEXT, label='Q3 Begin speaking'); beep(0.602); window(30, 25.783, 29.850, 'd', 'Q3 response')
say('BP', at=('ding', 0.374), label='Q4 Begin preparing'); beep(0.634); window(45, 40.678, 44.660, 'v', 'Q4 prep')
say('BS', at=NEXT, label='Q4 Begin speaking'); beep(0.603); window(30, 25.931, 30.165, 'd', 'Q4 response')
part(3)
say('P3_D1', at=('ding', 0.776)); say('P3_D2', 0.492); say('P3_D3', 0.883)
say('Q5_INTRO', 1.152); say('Q5', 1.084)
say('BP', 1.093, label='Q5 Begin preparing'); beep(0.634); window(3, -1.627, 3.054, 'v', 'Q5 prep')
say('BS', at=NEXT, label='Q5 Begin speaking'); beep(0.602); window(15, 11.001, 15.935, 'd', 'Q5 response')
say('Q6', at=('ding', 0.298)); say('BP', 1.046, label='Q6 Begin preparing'); beep(0.634); window(3, -1.525, 3.156, 'v', 'Q6 prep')
say('BS', at=NEXT, label='Q6 Begin speaking'); beep(0.602); window(15, 11.068, 16.002, 'd', 'Q6 response')
say('Q7_A', at=('ding', 0.182)); say('Q7_B', 0.600); say('BP', 1.126, label='Q7 Begin preparing'); beep(0.634); window(3, -1.558, 3.123, 'v', 'Q7 prep')
say('BS', at=NEXT, label='Q7 Begin speaking'); beep(0.594); window(30, 25.237, 30.170, 'd', 'Q7 response')
part(4)
say('P4_D1', at=('ding', 1.542)); say('P4_D2', 0.515); say('P4_D3', 0.668); say('P4_D4', 0.924)
say('BP', 1.140, label='Q8-10 Begin preparing (reading)'); beep(0.634); window(45, 40.837, 44.819, 'v', 'Q8-10 reading time')
say('Q8_INTRO', at=NEXT); say('Q8', 0.685)
say('BP', 1.094, label='Q8 Begin preparing'); beep(0.633); window(3, -1.433, 3.248, 'v', 'Q8 prep')
say('BS', at=NEXT, label='Q8 Begin speaking'); beep(0.595); window(15, 11.061, 15.995, 'd', 'Q8 response')
say('Q9', at=('ding', 0.252)); say('BP', 1.112, label='Q9 Begin preparing'); beep(0.634); window(3, -1.660, 3.331, 'v', 'Q9 prep')
say('BS', at=NEXT, label='Q9 Begin speaking'); beep(0.594); window(15, 10.801, 15.935, 'd', 'Q9 response')
say('Q10', at=('ding', 0.270)); say('BP', 1.206, label='Q10 Begin preparing'); beep(0.634); window(3, -1.536, 3.145, 'v', 'Q10 prep')
say('BS', at=NEXT, label='Q10 Begin speaking'); beep(0.594); window(30, 25.625, 30.558, 'd', 'Q10 response')
part(5)
say('P5_D1', at=('ding', 0.722)); say('P5_D2', 0.830); say('P5_D3', 0.863)
say('Q11_A', 1.712); say('Q11_B', 0.480); say('Q11_C', 0.426)
say('BP', 1.005, label='Q11 Begin preparing'); beep(0.634); window(45, 41.056, 45.737, 'v', 'Q11 prep')
say('BS', at=NEXT, label='Q11 Begin speaking'); beep(0.603); window(60, 55.310, 60.113, 'end', 'Q11 response')

BEEP_LEN, BEEP_LEAD, DING_LEAD = 0.261, 0.005, 0.008
STOP_HOLD = 2.0       # when the video ends on a part's closing ding, the STOP screen stays this long


def selected_parts(cfg):
    """The parts to build, sorted. They must be consecutive: a gap would need a second video."""
    parts = sorted(set(cfg.get('parts') or PART_IDS))
    if not set(parts) <= set(PART_IDS): raise BuildError('parts chi gom cac so tu 1 den 5.')
    if parts != list(range(parts[0], parts[-1] + 1)):
        raise BuildError('Cac phan phai lien nhau (vd. 1-2, 2-4). Muon tao phan cach quang thi hay tao 2 video rieng.')
    return parts


def ensure_models(log=log, progress=None):
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_FILES.items():
        p = MODELS / name
        if p.exists() and p.stat().st_size > 1_000_000: continue
        log(f'Dang tai {name} (chi lan dau, khoang {"310" if name.endswith("onnx") else "27"} MB)...')
        tmp = p.with_suffix(p.suffix + '.part')
        def hook(n, bs, total):
            if total <= 0 or n % 200: return
            if progress: progress('model', min(1.0, n * bs / total))
            else: print(f'\r  {min(100, n * bs * 100 // total)}%', end='', flush=True)
        urllib.request.urlretrieve(url, tmp, hook)
        if not progress: print()
        tmp.replace(p)


def build_audio(cfg, name, out_dir=OUTPUT, log=log, progress=None):
    """progress(stage, fraction) is called with stage 'model' (first-run download) then 'audio'."""
    from kokoro_onnx import Kokoro
    from scipy.signal import resample_poly
    steps = [st for n in selected_parts(cfg) for st in SEQ[n]]
    used = {st[1] for st in steps if st[0] == 'say'}
    spoken = dict(FIXED_SPOKEN)
    for k in CONTENT_KEYS:
        v = (cfg['spoken'].get(k) or '').strip()
        if not v and k in used and k not in OPTIONAL_KEYS: raise BuildError(f'Config thieu noi dung spoken.{k}')
        spoken[k] = v
    ensure_models(log, progress)
    sfx = {n: sf.read(ASSETS / 'sfx' / f'{n}.wav', dtype='float32')[0] for n in ('beep', 'ticks', 'ding')}
    kok = Kokoro(str(MODELS / 'kokoro-v1.0.onnx'), str(MODELS / 'voices-v1.0.bin'))
    cache = {}

    def tts(text):
        if text in cache: return cache[text]
        s, sr = kok.create(text, voice=VOICE, speed=SPEED, lang=LANG)
        s = resample_poly(np.asarray(s, np.float64), 147, 80).astype(np.float32)   # 24 kHz -> 44.1 kHz
        fr = int(0.01 * SR); e = np.array([np.sqrt(np.mean(s[i:i + fr] ** 2)) for i in range(0, len(s) - fr, fr)])
        on = np.where(e > e.max() * 10 ** (-45 / 20))[0]
        s = s[max(0, on[0] * fr - int(0.02 * SR)): min(len(s), (on[-1] + 1) * fr + int(0.04 * SR))].copy()
        f = int(0.005 * SR); s[:f] *= np.linspace(0, 1, f); s[-f:] *= np.linspace(1, 0, f)
        cache[text] = s
        return s

    log('Dang tao giong doc (Kokoro)...')
    place, events, anchors, cur = [], [], {}, 0.0
    for n, st in enumerate(steps):
        if progress: progress('audio', n / len(steps))
        if st[0] == 'say':
            _, key, gap, at, label = st
            text = spoken[key]
            if not text: continue                                   # optional clip left empty
            clip = tts(text)
            if n == 0: t = 0.0                                      # the first part's directions open the video
            else: t = cur + gap if at is None else (at[1] if at[0] == 'abs' else anchors[at[0]] + at[1])
            place.append((t, clip, True)); d = len(clip) / SR
            events.append(dict(t=t, end=t + d, kind='voice', label=label, key=key, text=text))
            cur = t + d
        elif st[0] == 'beep':
            t = cur + st[1]; place.append((t - BEEP_LEAD, sfx['beep'], False))
            anchors['beep_start'], anchors['beep_end'] = t, t + BEEP_LEN
            events.append(dict(t=t, end=t + BEEP_LEN, kind='beep', label='BEEP'))
            cur = t + BEEP_LEN
        else:
            _, w, ticks_at, next_at, nk, label = st
            be = anchors['beep_end']; tpos, tend = be + ticks_at, be + next_at
            s0 = max(tpos, anchors['beep_start'])
            tk = sfx['ticks'][int((s0 - tpos) * SR): int((tend - tpos) * SR)].copy()
            f = int((0.03 if nk == 'end' else 0.01) * SR); tk[-f:] *= np.linspace(1, 0, f)
            place.append((s0, tk, False))
            events.append(dict(t=be, end=tend, kind='timer', label=f'{label} (timer {w}s)', ticks=round(tpos + 0.013, 3)))
            if nk == 'v': anchors['next'] = tend
            elif nk == 'd':
                place.append((tend - DING_LEAD, sfx['ding'], False)); anchors['ding'] = tend
                events.append(dict(t=tend, end=tend + 0.24, kind='ding', label='DING'))
            cur = tend
    if events[-1]['kind'] == 'ding':                                # a part ends on its ding: hold STOP for a moment
        events.append(dict(t=events[-1]['t'], end=events[-1]['t'] + STOP_HOLD, kind='stop', label='STOP'))

    def active_rms(x):
        fr = int(0.02 * SR); e = np.array([np.mean(x[i:i + fr] ** 2) for i in range(0, len(x) - fr, fr)])
        e = e[e > 1e-5]; return np.sqrt(e.mean())
    g = REF_RMS / active_rms(np.concatenate(list(cache.values())))

    def limit(x, knee=0.8, room=0.18):
        y = x.copy(); m = np.abs(y) > knee
        y[m] = np.sign(y[m]) * (knee + room * np.tanh((np.abs(y[m]) - knee) / room)); return y
    total = max(max(t + len(c) / SR for t, c, _ in place), events[-1]['end'])
    mix = np.zeros(int(total * SR) + 10, np.float32)
    for t, c, is_voice in place:
        i = int(round(t * SR)); mix[i:i + len(c)] += limit(c * g) if is_voice else c
    peak = float(np.abs(mix).max())
    if peak > 0.99: mix *= 0.99 / peak

    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f'{name}_audio.wav'
    sf.write(wav, np.stack([mix, mix], 1), SR, subtype='PCM_16')
    with open(out_dir / f'{name}_timeline.json', 'w', encoding='utf-8') as f: json.dump(events, f, indent=1, ensure_ascii=False)
    try:
        run_ffmpeg(['-i', str(wav), '-codec:a', 'libmp3lame', '-b:a', '192k', str(out_dir / f'{name}.mp3')])
    except Exception as ex:
        log(f'  (khong xuat duoc MP3: {ex}; van co file WAV)')
    mmss = lambda t: f'{int(t // 60):02d}:{t % 60:05.2f}'
    with open(out_dir / f'{name}_cue_sheet.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['Start', 'End', 'Type', 'Item', 'Text / note'])
        for e in events: w.writerow([mmss(e['t']), mmss(e['end']), e['kind'].upper(), e['label'], e.get('text', '')])
    log(f'Audio xong: {mmss(total)} -> {out_dir.name}/{name}.mp3')


# =====================================================================================
# 2. VIDEO
# =====================================================================================
W, H = 1920, 1080
hexc = lambda x: tuple(int(x[i:i + 2], 16) for i in (1, 3, 5))
THEME = dict(hdr1=hexc('#0A4D9C'), hdr2=hexc('#1A7FD6'), hdr_text=(255, 255, 255), accent=hexc('#F2B632'),
             panel_border=hexc('#A9C8EA'), t_label_bg=hexc('#0A4D9C'), t_label_text=(255, 255, 255),
             t_border=hexc('#1A7FD6'), t_digits=hexc('#0A3F80'), stop=hexc('#0A4D9C'))   # "Ocean Blue"
INK, MUTED, LINE = (40, 40, 48), (95, 95, 110), (190, 198, 222)
PANEL = (230, 270, 1690, 775)          # content card
_fonts = {}
def font(weight, size):
    k = (weight, size)
    if k not in _fonts: _fonts[k] = ImageFont.truetype(str(ASSETS / 'fonts' / f'Inter-{weight}.otf'), size)
    return _fonts[k]

DIRS = {
 'dir1': ('Questions 1-2: Read a text aloud', 'In this part, you will be asked to read aloud the text on the screen. You will have 45 seconds to prepare. Then you will have 45 seconds to read the text out loud.'),
 'dir2': ('Questions 3-4: Describe a picture', 'In this part, you will be asked to describe the picture on the screen in as much detail as possible. You will have 45 seconds to prepare your response. Then you will have 30 seconds to talk about the picture.'),
 'dir3': ('Questions 5-7: Respond to questions', 'In this part, you will be asked to answer three questions. After listening to each question, you will have three seconds to prepare your response. You will have 15 seconds to respond to Questions 5 and 6 and 30 seconds to respond to Question 7.'),
 'dir4': ('Questions 8-10: Respond to questions using information provided', 'In this part, you will be asked to refer to information on the screen in order to answer three questions. The information will be shown for 45 seconds before you hear the questions. After listening to each question, you will have three seconds to prepare your response. You will have 15 seconds to respond to Questions 8 and 9 and 30 seconds to respond to Question 10.'),
 'dir5': ('Question 11: Express an opinion', 'In this part, you will be asked to give your thoughts on a certain topic. It is to your advantage to speak as much as possible in the time provided. You will have 45 seconds to prepare your response and 60 seconds to speak.'),
}


def wrap(d, text, f, maxw):
    out = []
    for para in text.split('\n'):
        line = ''
        for w in para.split(' '):
            t = (line + ' ' + w).strip()
            if d.textlength(t, font=f) <= maxw: line = t
            else: out.append(line); line = w
        out.append(line)
    return out


class Painter:
    def __init__(self):
        logo = Image.open(ASSETS / 'images' / 'logo.png').convert('RGBA')
        lh = 120; self.logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
        self._img = {}

    def image(self, path):
        if path not in self._img: self._img[path] = Image.open(path).convert('RGB')
        return self._img[path]

    def base(self, qlabel=''):
        T = THEME
        im = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(im)
        im.paste(self.logo, ((W - self.logo.width) // 2, 40), self.logo)
        x0, y0, x1, y1 = PANEL[0], 200, PANEL[2], 270
        for x in range(x0, x1):
            t = (x - x0) / (x1 - x0)
            d.line([(x, y0), (x, y1)], fill=tuple(int(T['hdr1'][i] * (1 - t) + T['hdr2'][i] * t) for i in range(3)))
        d.rectangle([x0, y1 - 5, x1, y1], fill=T['accent'])
        d.text((x0 + 30, (y0 + y1) // 2), 'TOEIC Speaking', font=font('Medium', 26), fill=T['hdr_text'], anchor='lm')
        if qlabel: d.text((W // 2, (y0 + y1) // 2), qlabel, font=font('Medium', 24), fill=T['hdr_text'], anchor='mm')
        d.rectangle([PANEL[0], 270, PANEL[2], PANEL[3]], outline=T['panel_border'], width=2)
        return im, d

    def timer(self, d, label, secs):
        T = THEME
        if label == 'STOP':
            d.text((W // 2, 880), 'STOP', font=font('Bold', 110), fill=T['stop'], anchor='mm'); return
        bx0, bx1, by0 = W // 2 - 170, W // 2 + 170, 805
        d.rectangle([bx0, by0, bx1, by0 + 62], fill=T['t_label_bg'])
        d.text((W // 2, by0 + 31), label, font=font('SemiBold', 28), fill=T['t_label_text'], anchor='mm')
        d.rectangle([bx0, by0 + 62, bx1, by0 + 160], fill='white', outline=T['t_border'], width=3)
        d.text((W // 2, by0 + 111), f'{secs // 60:02d}:{secs % 60:02d}', font=font('Bold', 66), fill=T['t_digits'], anchor='mm')

    def directions(self, title, body):
        im, d = self.base()
        size = 30
        while True:                                   # shrink if a long text would overflow the card
            f, fb = font('Regular', size), font('Bold', size)
            lines = wrap(d, 'Directions: ' + body, f, 1300)
            if 490 + len(lines) * int(size * 1.53) < PANEL[3] - 20 or size <= 22: break
            size -= 2
        d.text((W // 2, 420), title, font=font('Bold', 40), fill=INK, anchor='mm')
        y = 490
        for i, ln in enumerate(lines):
            x = (W - 1300) // 2
            if i == 0:
                d.text((x, y), 'Directions:', font=fb, fill=INK)
                x += d.textlength('Directions: ', font=fb); ln = ln[len('Directions: '):]
            d.text((x, y), ln, font=f, fill=INK); y += int(size * 1.53)
        return im

    def text_screen(self, qlabel, blocks, tstate):
        """blocks: (text, style) with style regular / bold (centred) / italic / bullet."""
        im, d = self.base(qlabel)
        mx = 1300; x = (W - mx) // 2
        for size in (32, 30, 28, 26, 24, 22):           # biggest size that fits the card
            sty = {k: font(v, size) for k, v in (('regular', 'Regular'), ('bold', 'Bold'), ('italic', 'Italic'), ('bullet', 'Regular'))}
            lh = int(size * 1.5); h = 0
            for text, s in blocks:
                h += lh if s == 'bullet' else len(wrap(d, text, sty[s], mx)) * lh + 16
            if 310 + h < PANEL[3] - 15: break
        y = 310
        for text, s in blocks:
            f = sty[s]
            if s == 'bullet':
                d.text((x + 60, y), '•  ' + text, font=f, fill=INK); y += lh; continue
            for ln in wrap(d, text, f, mx):
                if s == 'bold': d.text((W // 2, y), ln, font=f, fill=INK, anchor='ma')
                else: d.text((x, y), ln, font=f, fill=INK)
                y += lh
            y += 16
        if tstate: self.timer(d, *tstate)
        return im

    def picture_screen(self, qlabel, path, tstate, box=(400, 290, 1520, 755)):
        im, d = self.base(qlabel)
        if path:
            p = self.image(path); s = min((box[3] - box[1]) / p.height, (box[2] - box[0]) / p.width)
            p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
            im.paste(p, ((W - p.width) // 2, box[1] + (box[3] - box[1] - p.height) // 2))
        else:
            d.rectangle(box, fill=(238, 240, 246), outline=LINE, width=2)
            d.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), '[ Picture ]', font=font('Medium', 36), fill=MUTED, anchor='mm')
        if tstate: self.timer(d, *tstate)
        return im


def build_video(cfg, name, keep_frames=False, out_dir=OUTPUT, log=log, progress=None):
    """progress(stage, fraction) is called with stage 'frames' then 'encode'."""
    tl_path = out_dir / f'{name}_timeline.json'; wav = out_dir / f'{name}_audio.wav'
    if not tl_path.exists() or not wav.exists(): raise BuildError('Chua co audio. Chay lai khong kem --video-only.')
    with open(tl_path, encoding='utf-8') as f: TL = json.load(f)
    sc = cfg['screen']
    img = lambda k: str((ROOT / sc[k]).resolve()) if sc.get(k) else None
    parts = selected_parts(cfg)
    for n, k in ((2, 'q3_image'), (2, 'q4_image'), (4, 'q8_10_image')):      # only the pictures the chosen parts show
        if n in parts and sc.get(k) and not Path(img(k)).exists(): raise BuildError(f'Khong tim thay anh {k}: {sc[k]}')
    intro = sc.get('q5_7_intro', '')
    painter = Painter()

    def draw(screen, ts):
        if screen in DIRS: return painter.directions(*DIRS[screen])
        if screen == 'Q1': return painter.text_screen('Question 1 of 11', [(sc['q1_text'], 'regular')], ts)
        if screen == 'Q2': return painter.text_screen('Question 2 of 11', [(sc['q2_text'], 'regular')], ts)
        if screen == 'Q3': return painter.picture_screen('Question 3 of 11', img('q3_image'), ts)
        if screen == 'Q4': return painter.picture_screen('Question 4 of 11', img('q4_image'), ts)
        if screen == 'intro5': return painter.text_screen('', [(intro, 'regular')], ts)
        if screen == 'Q5': return painter.text_screen('Question 5 of 11', [(intro, 'regular'), (sc['q5'], 'bold')], ts)
        if screen == 'Q6': return painter.text_screen('Question 6 of 11', [(intro, 'regular'), (sc['q6'], 'bold')], ts)
        if screen == 'Q7': return painter.text_screen('Question 7 of 11', [(intro, 'regular'), (sc['q7'], 'bold')] +
                                                      [(o, 'bullet') for o in sc.get('q7_options', [])], ts)
        if screen == 'info': return painter.picture_screen('Questions 8-10', img('q8_10_image'), ts, box=(300, 280, 1620, 765))
        if screen in ('info8', 'info9', 'info10'):
            return painter.picture_screen(f'Question {screen[4:]} of 11', img('q8_10_image'), ts, box=(300, 280, 1620, 765))
        if screen == 'Q11': return painter.text_screen('Question 11 of 11', [(sc['q11_lead'], 'regular'), (sc['q11_statement'], 'italic'),
                                                                             (sc['q11_instruction'], 'regular')], ts)
        raise KeyError(screen)

    # --- screen schedule anchored on the audio timeline
    V = {}
    for e in TL:
        if e['kind'] == 'voice': V.setdefault(e['label'], e['t'])
    DUR = max(e['end'] for e in TL)
    SCREEN_AT = {                       # part -> (voice label it follows, seconds it leads by, screen)
        1: [('P1_D1', 0.0, 'dir1'), ('Q1 Begin preparing', 0.5, 'Q1'), ('Q2 Begin preparing', 0.0, 'Q2')],
        2: [('P2_D1', 0.2, 'dir2'), ('Q3 Begin preparing', 0.5, 'Q3'), ('Q4 Begin preparing', 0.0, 'Q4')],
        3: [('P3_D1', 0.2, 'dir3'), ('Q5_INTRO', 0.2, 'intro5'), ('Q5', 0.5, 'Q5'), ('Q6', 0.0, 'Q6'), ('Q7_A', 0.0, 'Q7')],
        4: [('P4_D1', 0.2, 'dir4'), ('Q8-10 Begin preparing (reading)', 0.5, 'info'),
            ('Q8_INTRO', 0.0, 'info8'), ('Q9', 0.0, 'info9'), ('Q10', 0.0, 'info10')],
        5: [('P5_D1', 0.2, 'dir5'), ('Q11_A', 0.5, 'Q11')],
    }
    SCREENS = sorted((max(0.0, V[k] - lead), scr) for n in parts for k, lead, scr in SCREEN_AT[n])
    SCREENS[0] = (0.0, SCREENS[0][1])
    DIR_STARTS = [t for t, s in SCREENS if s in DIRS]
    BP_STARTS = sorted(e['t'] for e in TL if e['kind'] == 'voice' and 'Begin preparing' in e['label'])
    beeps = [e for e in TL if e['kind'] == 'beep']; timers = [e for e in TL if e['kind'] == 'timer']
    WIN = []
    for i, (b, tm) in enumerate(zip(beeps, timers)):
        w = int(tm['label'].split('timer ')[1].rstrip('s)'))
        resp, reading = 'response' in tm['label'], 'reading' in tm['label']
        hold = None if resp else (tm['end'] if reading else beeps[i + 1]['t'])
        WIN.append(dict(bs=b['t'], be=b['end'], end=tm['end'], W=w, resp=resp, hold=hold))
    DINGS = [e['t'] for e in TL if e['kind'] == 'ding']

    def timer_state(t):
        for k, wn in enumerate(WIN):
            last = wn['end'] if wn['resp'] else wn['hold']
            if k == len(WIN) - 1 and not any(d >= wn['end'] for d in DINGS): last = DUR + 1    # no ding follows
            if wn['bs'] <= t < last:
                rem = wn['W'] - max(0.0, t - wn['be'])
                return ('RESPONSE TIME' if wn['resp'] else 'PREPARATION TIME', max(0, min(wn['W'], math.ceil(rem - 1e-9))))
        for d in DINGS:                        # STOP from the ding until the next 'Begin preparing' / directions
            nxt = min([x for x in BP_STARTS + DIR_STARTS if x > d], default=DUR + 1)
            if d <= t < nxt: return ('STOP', 0)
        return None

    def screen_at(t):
        cur = SCREENS[0][1]
        for s, k in SCREENS:
            if s <= t: cur = k
            else: break
        return cur

    nfr = int(math.ceil(DUR * FPS)); segs = []
    for i in range(nfr):
        t = (i + 0.5) / FPS; s = screen_at(t)
        st = (s, None if s in DIRS else timer_state(t))
        if segs and segs[-1][0] == st: segs[-1][1] += 1
        else: segs.append([st, 1])

    out_dir.mkdir(parents=True, exist_ok=True)
    fdir = Path(tempfile.mkdtemp(prefix=f'frames_{name}_', dir=out_dir)); cache = {}
    uniq = len({s for s, _ in segs}); t0 = time.time()
    log(f'Dang ve {uniq} khung hinh...')
    try:
        for st, _ in segs:
            if st in cache: continue
            p = fdir / f'f{len(cache):04d}.png'
            draw(*st).save(p, compress_level=1); cache[st] = p
            if progress: progress('frames', len(cache) / uniq)
            if len(cache) % 100 == 0: log(f'  {len(cache)}/{uniq}')
        concat = fdir / 'concat.txt'
        with open(concat, 'w', encoding='utf-8') as f:
            for st, n in segs: f.write(f"file '{cache[st].as_posix()}'\nduration {n / FPS:.2f}\n")
            f.write(f"file '{cache[segs[-1][0]].as_posix()}'\n")
        log('Dang ghep video (ffmpeg)...')
        out = out_dir / f'{name}.mp4'
        run_ffmpeg(['-f', 'concat', '-safe', '0', '-i', str(concat), '-i', str(wav), '-map', '0:v', '-map', '1:a', '-r', str(FPS),
                    '-c:v', 'libx264', '-preset', 'medium', '-tune', 'stillimage', '-crf', '20', '-pix_fmt', 'yuv420p',
                    # -frames:v, not -t: -t stops reading before the last (repeated) frame of the concat list, which
                    # cuts a long final screen (the STOP hold) down to about a second.
                    '-c:a', 'aac', '-b:a', '192k', '-frames:v', str(nfr), '-movflags', '+faststart', str(out)],
                   total=DUR, progress=progress and (lambda x: progress('encode', x)))
    finally:
        if not keep_frames: shutil.rmtree(fdir, ignore_errors=True)
    log(f'Video xong ({time.time() - t0:.0f} s) -> {out_dir.name}/{name}.mp4')
    return out


def main():
    ap = argparse.ArgumentParser(description='TOEIC Speaking full test builder (audio + video)')
    ap.add_argument('config', help='duong dan file config, vd config/test_moi.json')
    ap.add_argument('--audio-only', action='store_true', help='chi tao audio (MP3 + timeline)')
    ap.add_argument('--video-only', action='store_true', help='chi dung video tu audio da co trong output/')
    ap.add_argument('--keep-frames', action='store_true', help='giu lai cac khung hinh PNG')
    a = ap.parse_args()
    cfg_path = Path(a.config)
    if not cfg_path.is_absolute(): cfg_path = (Path.cwd() / cfg_path)
    with open(cfg_path, encoding='utf-8') as f: cfg = json.load(f)
    name = cfg.get('output_name') or cfg_path.stem
    try:
        if not a.video_only: build_audio(cfg, name)
        if not a.audio_only: build_video(cfg, name, a.keep_frames)
    except BuildError as ex:
        sys.exit(str(ex))


if __name__ == '__main__':
    main()
