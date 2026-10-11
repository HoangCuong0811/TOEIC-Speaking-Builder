"""
Deployment settings, read once at start-up from environment variables (all named TOEIC_*).

With nothing set, every value is what the code used before it was configurable, so running it on the
developer's machine does not change. A value that cannot be understood stops the program with a clear message.

    TOEIC_HOST             address to listen on             127.0.0.1  (0.0.0.0 inside Docker / on a server)
    TOEIC_PORT             port                             8001
    TOEIC_DATA_DIR         folder for models/ and output/   the folder of this file
    TOEIC_MODELS_DIR       voice model files                <TOEIC_DATA_DIR>/models
    TOEIC_OUTPUT_DIR       finished jobs                    <TOEIC_DATA_DIR>/output
    TOEIC_MAX_IMAGE_MB     biggest accepted picture, in MB  20
    TOEIC_VOICE            Kokoro voice                     af_heart
    TOEIC_SPEED            speaking speed, 0.5 - 2.0        1.0
    TOEIC_LANG             pronunciation                    en-us
    TOEIC_JOB_TTL_HOURS    delete a job's files this many hours after it was last written; 0 = never    0
    TOEIC_DOCS             1/0: serve /docs, /redoc and /openapi.json                                   1
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_TRUE, _FALSE = {'1', 'true', 'yes', 'on'}, {'0', 'false', 'no', 'off'}


def _read(name, default, cast, ok=lambda v: True, expect=''):
    raw = (os.environ.get(name) or '').strip()
    if not raw: return default
    try:
        value = cast(raw)
        if ok(value): return value
    except ValueError:
        pass
    raise SystemExit(f'Cau hinh sai: {name}={raw!r}' + (f' (can {expect})' if expect else ''))


def _bool(raw):
    if raw.lower() in _TRUE: return True
    if raw.lower() in _FALSE: return False
    raise ValueError(raw)


def _dir(name, default):
    raw = (os.environ.get(name) or '').strip()
    return Path(raw).expanduser().resolve() if raw else default


HOST = _read('TOEIC_HOST', '127.0.0.1', str)
PORT = _read('TOEIC_PORT', 8001, int, lambda v: 0 < v < 65536, 'so tu 1 den 65535')
DATA_DIR = _dir('TOEIC_DATA_DIR', ROOT)
MODELS_DIR = _dir('TOEIC_MODELS_DIR', DATA_DIR / 'models')
OUTPUT_DIR = _dir('TOEIC_OUTPUT_DIR', DATA_DIR / 'output')
MAX_IMAGE_MB = _read('TOEIC_MAX_IMAGE_MB', 20, int, lambda v: v >= 1, 'so nguyen tu 1 tro len')
VOICE = _read('TOEIC_VOICE', 'af_heart', str)
SPEED = _read('TOEIC_SPEED', 1.0, float, lambda v: 0.5 <= v <= 2.0, 'so tu 0.5 den 2.0')
LANG = _read('TOEIC_LANG', 'en-us', str)
JOB_TTL_HOURS = _read('TOEIC_JOB_TTL_HOURS', 0.0, float, lambda v: v >= 0, 'so gio >= 0, 0 la khong tu xoa')
DOCS = _read('TOEIC_DOCS', True, _bool, expect='1 hoac 0')
