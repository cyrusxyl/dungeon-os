"""TTS service. Run: uv run uvicorn service.app:app --port 8770"""
import asyncio
import os
from pathlib import Path

import numpy as np
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .cache import Cache, make_key
from .engine import Engine, UnknownVoice, load_engine
from .queue import LIVE, WARM, Job, Scheduler
from .text import normalize, split_sentences

ROOT = Path(__file__).resolve().parent.parent


def sentences_for(text: str) -> list[str]:
    return [s for s in split_sentences(normalize(text)) if s.strip()]


def synth(engine: Engine, cache: Cache, sentences, voice, style, cancel, emit):
    """Synthesize sentences in order. emit(bytes) gets each piece; emit None only fills the cache. Stop after the current chunk on cancel."""
    for s in sentences:
        if cancel.is_set():
            return
        key = make_key(engine.name, engine.model_ver, voice, style, s)
        if emit is None:
            if cache.has(key):
                continue
        elif (hit := cache.get(key)) is not None:
            emit(hit)
            continue
        parts = []
        for arr in engine.stream(s, voice, style):
            b = np.asarray(arr, dtype="<i2").tobytes()
            parts.append(b)
            if emit:
                emit(b)
            if cancel.is_set():
                return  # partial audio is never cached
        meta = dict(text=s, voice=voice, style=style, engine=engine.name,
                    model_ver=engine.model_ver, sample_rate=engine.sample_rate)
        cache.put(key, b"".join(parts), meta)


def create_app(engine: Engine | None = None, cache_dir=None) -> Starlette:
    engine = engine or load_engine()
    cache = Cache(cache_dir or os.environ.get("TTS_CACHE", ROOT / "cache"))
    sched = Scheduler()

    async def health(request):
        return JSONResponse({"ok": True, "engine": engine.name,
                             "sample_rate": engine.sample_rate, "voices": sorted(engine.library())})

    async def voices(request):
        return JSONResponse({"voices": engine.library()})

    async def speak(request: Request):
        try:
            body = await request.json()
            text = body["text"]
            assert isinstance(text, str)
        except Exception:
            return JSONResponse({"error": "bad body"}, status_code=400)
        voice = body.get("voice") or "narrator"
        try:
            style = engine.resolve(voice, body.get("style"))
        except UnknownVoice:
            return JSONResponse({"error": f"unknown voice: {voice}"}, status_code=404)
        sents = sentences_for(text)
        hit = all(cache.has(make_key(engine.name, engine.model_ver, voice, style, s)) for s in sents)
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def run(job):
            try:
                synth(engine, cache, sents, voice, style, job.cancel,
                      lambda b: loop.call_soon_threadsafe(q.put_nowait, b))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        job = Job(LIVE, run, name=str(body.get("id", "")))
        app.state.last_live = job
        sched.submit(job)

        async def gen():
            try:
                while True:
                    b = await q.get()
                    if b is None:
                        return
                    yield b
            finally:
                job.cancel.set()  # no-op after normal end

        return StreamingResponse(gen(), media_type="application/octet-stream", headers={
            "X-Sample-Rate": str(engine.sample_rate), "X-Cache": "hit" if hit else "miss"})

    async def warm(request: Request):
        try:
            items = (await request.json())["items"]
        except Exception:
            return JSONResponse({"error": "bad body"}, status_code=400)
        for it in items:
            sents = sentences_for(it.get("text", ""))
            voice = it.get("voice") or "narrator"
            try:
                style = engine.resolve(voice, it.get("style"))
            except UnknownVoice:
                continue
            sched.submit(Job(WARM, lambda job, s=sents, v=voice, st=style: synth(
                engine, cache, s, v, st, job.cancel, None), name="warm"))
        return Response(status_code=202)

    async def test_page(request):
        return FileResponse(ROOT / "service" / "static" / "test.html", media_type="text/html")

    app = Starlette(routes=[Route("/test", test_page), Route("/health", health), Route("/speak", speak, methods=["POST"]),
                            Route("/voices", voices), Route("/warm", warm, methods=["POST"])])
    app.state.scheduler = sched
    app.state.cache = cache
    return app


app = create_app()
