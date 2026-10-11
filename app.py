#!/usr/bin/env python3
"""
Web API + giao dien cho TOEIC Speaking builder (dung lai logic trong make_test.py).

    python app.py                       # roi mo http://127.0.0.1:8001 (doi bang TOEIC_HOST / TOEIC_PORT, xem settings.py)

    POST /api/jobs                      tao 1 de: form `data` (JSON, xem SpeakingTest) + 3 file anh -> job
    GET  /api/jobs/{id}                 trang thai va tien do
    GET  /api/jobs/{id}/video|audio     file ket qua (them ?download=1 de tai ve)
"""
import contextlib, io, queue, re, shutil, threading, time, traceback, uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, StringConstraints, ValidationError

import make_test
import settings

ROOT = Path(__file__).resolve().parent
JOBS_DIR = make_test.OUTPUT / 'jobs'
MAX_IMAGE_BYTES = settings.MAX_IMAGE_MB * 1024 * 1024
JOB_ID = re.compile(r'^[0-9a-f]{12}$')           # the folder names create_job makes: nothing else is ever deleted
JANITOR_EVERY = 600                              # seconds between two clean-ups
FILES = {'video': ('.mp4', 'video/mp4'), 'audio': ('.mp3', 'audio/mpeg')}
# Share of the whole build each stage takes, as (start, end) of the overall progress bar.
SPAN = {'model': (0.0, 0.0), 'audio': (0.0, 0.35), 'frames': (0.35, 0.55), 'encode': (0.55, 1.0)}

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True)]


class SpokenOverrides(BaseModel):
    """What the voice reads, where it must differ from the on-screen text (times, dates, prices, symbols).
    Empty = the voice reads the on-screen text as it is."""
    q5_7_intro: OptionalText = ''
    q5: OptionalText = ''
    q6: OptionalText = ''
    q7: OptionalText = ''
    q7_options: OptionalText = ''
    q11_lead: OptionalText = ''
    q11_statement: OptionalText = ''
    q11_instruction: OptionalText = ''


# What each part (1 = Q1-2, 2 = Q3-4, 3 = Q5-7, 4 = Q8-10, 5 = Q11) needs from the user.
PART_TEXT = {1: ['q1_text', 'q2_text'], 2: [], 3: ['q5_7_intro', 'q5', 'q6', 'q7'],
             4: ['q8_intro', 'q8', 'q9', 'q10'], 5: ['q11_lead', 'q11_statement', 'q11_instruction']}
PART_IMAGES = {1: [], 2: ['q3_image', 'q4_image'], 3: [], 4: ['q8_10_image'], 5: []}


class SpeakingTest(BaseModel):
    """Only the fields of the selected `parts` have to be filled in (checked in create_job)."""
    name: OptionalText = ''             # used for the file names
    parts: list[Literal[1, 2, 3, 4, 5]] = [1, 2, 3, 4, 5]   # consecutive parts to build; all five = the full test
    q1_text: OptionalText = ''          # Q1-2 are on screen only: the test taker reads them aloud
    q2_text: OptionalText = ''
    q5_7_intro: OptionalText = ''
    q5: OptionalText = ''
    q6: OptionalText = ''
    q7: OptionalText = ''
    q7_options: list[OptionalText] = []
    q8_intro: OptionalText = ''         # Q8-10 are spoken only: the screen shows the uploaded document
    q8: OptionalText = ''
    q9: OptionalText = ''
    q10: OptionalText = ''
    q11_lead: OptionalText = 'Do you agree or disagree with the following statement?'
    q11_statement: OptionalText = ''
    q11_instruction: OptionalText = 'Use specific reasons and details to support your opinion.'
    spoken: SpokenOverrides = SpokenOverrides()


def to_config(t: SpeakingTest, images: dict, parts: list[int]) -> dict:
    """Map the API input to the spoken/screen config that make_test expects."""
    sp, options = t.spoken, [o for o in t.q7_options if o]
    spoken = {
        'Q5_INTRO': sp.q5_7_intro or t.q5_7_intro, 'Q5': sp.q5 or t.q5, 'Q6': sp.q6 or t.q6, 'Q7_A': sp.q7 or t.q7,
        'Q7_B': sp.q7_options or ' '.join(o.rstrip('.') + '.' for o in options),
        'Q8_INTRO': t.q8_intro, 'Q8': t.q8, 'Q9': t.q9, 'Q10': t.q10,
        'Q11_A': sp.q11_lead or t.q11_lead, 'Q11_B': sp.q11_statement or t.q11_statement,
        'Q11_C': sp.q11_instruction or t.q11_instruction,
    }
    screen = {
        'q1_text': t.q1_text, 'q2_text': t.q2_text, 'q5_7_intro': t.q5_7_intro, 'q5': t.q5, 'q6': t.q6, 'q7': t.q7,
        'q7_options': options, 'q11_lead': t.q11_lead, 'q11_statement': t.q11_statement,
        'q11_instruction': t.q11_instruction, **{k: str(p) for k, p in images.items()},
    }
    return {'spoken': {k: ' '.join(v.split()) for k, v in spoken.items()}, 'screen': screen, 'parts': parts}


@dataclass
class Job:
    id: str
    name: str
    dir: Path
    status: str = 'queued'              # queued -> running -> done | error
    stage: str = ''                     # model | audio | frames | encode
    stage_progress: float = 0.0
    error: str = ''

    def report(self, stage, fraction): self.stage, self.stage_progress = stage, fraction

    def file(self, kind): return self.dir / (self.name + FILES[kind][0])

    def public(self):
        done = self.status == 'done'
        start, end = SPAN.get(self.stage, (0.0, 0.0))
        out = dict(id=self.id, name=self.name, status=self.status, stage=self.stage, error=self.error,
                   stage_progress=round(self.stage_progress, 3),
                   progress=1.0 if done else round(start + (end - start) * self.stage_progress, 3))
        for kind in FILES:
            out[f'{kind}_url'] = f'/api/jobs/{self.id}/{kind}' if done and self.file(kind).exists() else None
        return out


JOBS: dict[str, Job] = {}
TODO: queue.Queue = queue.Queue()


def worker():
    """Builds run one at a time: each one keeps the CPU busy for minutes."""
    while True:
        job, cfg = TODO.get()
        job.status = 'running'
        try:
            make_test.build_audio(cfg, job.name, out_dir=job.dir, progress=job.report)
            make_test.build_video(cfg, job.name, out_dir=job.dir, progress=job.report)
            job.status = 'done'
        except Exception as ex:
            traceback.print_exc()
            job.error, job.status = str(ex) or type(ex).__name__, 'error'
        with contextlib.suppress(OSError):                                  # ~140 MB, only needed to build the video
            (job.dir / f'{job.name}_audio.wav').unlink(missing_ok=True)


threading.Thread(target=worker, daemon=True).start()


def purge_expired(ttl_hours: float, now: float | None = None) -> int:
    """Delete the folders of jobs last written more than `ttl_hours` ago (never one that is queued or running).
    Returns how many were removed."""
    if not JOBS_DIR.is_dir(): return 0
    cutoff = (time.time() if now is None else now) - ttl_hours * 3600
    removed = 0
    for d in JOBS_DIR.iterdir():
        if not (d.is_dir() and JOB_ID.match(d.name)): continue
        job = JOBS.get(d.name)
        if job and job.status in ('queued', 'running'): continue
        try:
            if d.stat().st_mtime > cutoff: continue
        except OSError:
            continue
        shutil.rmtree(d, ignore_errors=True)
        JOBS.pop(d.name, None)
        removed += 1
    return removed


def janitor():
    while True:
        try:
            n = purge_expired(settings.JOB_TTL_HOURS)
            if n: print(f'Da xoa {n} job cu (qua {settings.JOB_TTL_HOURS:g} gio).', flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(JANITOR_EVERY)


if settings.JOB_TTL_HOURS > 0: threading.Thread(target=janitor, daemon=True).start()


def invalid(field, msg, kind='value_error'):
    return RequestValidationError([{'loc': ('body', *field), 'msg': msg, 'type': kind}])


def read_image(field, upload: UploadFile):
    """Decode an uploaded picture as upright RGB, with any transparency flattened onto white."""
    raw = upload.file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES: raise invalid([field], f'Ảnh lớn hơn {MAX_IMAGE_BYTES // 2 ** 20} MB.')
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGBA')
    except Exception:
        raise invalid([field], 'Không đọc được file ảnh.')
    flat = Image.new('RGB', im.size, 'white'); flat.paste(im, mask=im.getchannel('A'))
    return flat


def get_job(job_id):
    if job_id not in JOBS: raise HTTPException(404, 'Không tìm thấy job (server đã khởi động lại hoặc job đã hết hạn).')
    return JOBS[job_id]


# TOEIC_DOCS=0 switches off the generated API pages (/docs, /redoc, /openapi.json) on a public server.
DOCS = {} if settings.DOCS else dict(docs_url=None, redoc_url=None, openapi_url=None)
app = FastAPI(title='TOEIC Speaking Builder', **DOCS)
MESSAGES = {'missing': 'Chưa nhập nội dung.', 'string_too_short': 'Chưa nhập nội dung.', 'json_invalid': 'JSON không hợp lệ.'}


@app.post('/api/jobs', status_code=202)
def create_job(data: Annotated[str, Form(description='Nội dung đề, dạng JSON theo schema SpeakingTest')],
               q3_image: UploadFile | None = None, q4_image: UploadFile | None = None,
               q8_10_image: UploadFile | None = None):
    try:
        test = SpeakingTest.model_validate_json(data)
    except ValidationError as ex:
        raise RequestValidationError([{'loc': ('body', 'data', *e['loc']), 'msg': MESSAGES.get(e['type'], e['msg']),
                                       'type': e['type']} for e in ex.errors()])
    try:
        if not test.parts: raise make_test.BuildError()
        parts = make_test.selected_parts({'parts': test.parts})
    except make_test.BuildError:
        raise invalid(['data', 'parts'], 'Hãy chọn ít nhất một phần, và chỉ chọn các phần liền nhau (vd. 1–2, 2–4). '
                                        'Muốn tạo phần cách quãng thì hãy tạo 2 video riêng.')
    uploads = {'q3_image': q3_image, 'q4_image': q4_image, 'q8_10_image': q8_10_image}
    problems = [{'loc': ('body', 'data', k), 'msg': MESSAGES['missing'], 'type': 'missing'}
                for n in parts for k in PART_TEXT[n] if not getattr(test, k)]
    problems += [{'loc': ('body', k), 'msg': 'Chưa chọn ảnh.', 'type': 'missing'}
                 for n in parts for k in PART_IMAGES[n] if uploads[k] is None]
    if problems: raise RequestValidationError(problems)
    # pictures of the parts that were not selected are ignored
    pictures = {k: read_image(k, uploads[k]) for n in parts for k in PART_IMAGES[n]}
    job_id = uuid.uuid4().hex[:12]
    name = re.sub(r'[^\w\-]+', '_', test.name).strip('_') or 'TOEIC_Speaking_Test'
    if len(parts) < len(make_test.PART_IDS):
        name += f'_Part{parts[0]}' + (f'-{parts[-1]}' if len(parts) > 1 else '')
    job = Job(id=job_id, name=name, dir=JOBS_DIR / job_id)
    job.dir.mkdir(parents=True)
    images = {}
    for k, im in pictures.items():
        images[k] = job.dir / f'{k}.png'; im.save(images[k])
    JOBS[job_id] = job
    TODO.put((job, to_config(test, images, parts)))
    return job.public()


@app.get('/api/jobs/{job_id}')
def job_status(job_id: str):
    return get_job(job_id).public()


@app.get('/api/jobs/{job_id}/{kind}')
def job_file(job_id: str, kind: Literal['video', 'audio'], download: bool = False):
    job = get_job(job_id)
    path = job.file(kind)
    if job.status != 'done' or not path.exists(): raise HTTPException(404, 'Chưa có file này.')
    return FileResponse(path, media_type=FILES[kind][1], filename=path.name if download else None)


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(ROOT / 'web' / 'index.html', headers={'Cache-Control': 'no-cache'})


if __name__ == '__main__':
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, access_log=False)     # the page polls every 1.5 s
