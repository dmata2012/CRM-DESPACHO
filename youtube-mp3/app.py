"""Convertidor YouTube -> audio (uso interno).

Servidor Flask que usa yt-dlp para descargar el audio y ffmpeg para
convertirlo al formato elegido. Flujo similar a y2mate, con cola:
  1. /api/info        -> metadatos del video (título, miniatura, duración)
  2. /api/convert     -> agrega un trabajo a la cola de conversión
  3. /api/jobs        -> estado de todos los trabajos de la cola
  4. /api/download    -> entrega el archivo terminado
  5. DELETE /api/jobs -> cancela un trabajo en espera o lo quita de la lista
"""

import itertools
import os
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_file
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", BASE_DIR / "downloads"))
MAX_DURATION = int(os.environ.get("MAX_DURATION_SECONDS", 60 * 60))  # 1 hora
FILE_TTL = int(os.environ.get("FILE_TTL_SECONDS", 30 * 60))  # 30 minutos
WORKERS = max(1, int(os.environ.get("WORKERS", 2)))  # conversiones simultáneas
ALLOWED_BITRATES = ["128", "192", "256", "320"]
# formato -> (etiqueta, tipo MIME, usa bitrate)
FORMATS = {
    "mp3": ("MP3", "audio/mpeg", True),
    "m4a": ("M4A (AAC)", "audio/mp4", True),
    "opus": ("OPUS", "audio/ogg", True),
    "wav": ("WAV (sin pérdida)", "audio/wav", False),
    "flac": ("FLAC (sin pérdida)", "audio/flac", False),
}
ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
jobs = {}
jobs_lock = threading.Lock()
job_queue = queue.Queue()
job_seq = itertools.count()


def is_youtube_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_HOSTS


def safe_filename(title, ext):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", title).strip()
    return f"{name[:120] or 'audio'}.{ext}"


def base_ydl_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }


def extract_info(url):
    with YoutubeDL(base_ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def update_job(job_id, **fields):
    with jobs_lock:
        jobs[job_id].update(fields)


def run_conversion(job_id, url, fmt, bitrate):
    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = (done / total * 90) if total else 0  # 0-90% descarga
            update_job(job_id, status="downloading", progress=round(pct, 1))
        elif d["status"] == "finished":
            update_job(job_id, status="converting", progress=92)

    extract = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
    if FORMATS[fmt][2]:
        extract["preferredquality"] = bitrate
    opts = base_ydl_opts() | {
        "format": "bestaudio/best",
        "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "postprocessors": [extract, {"key": "FFmpegMetadata"}],
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        out = next(job_dir.glob(f"*.{fmt}"), None)
        if out is None:
            raise RuntimeError("No se generó el archivo de audio")
        update_job(
            job_id,
            status="done",
            progress=100,
            path=str(out),
            filename=safe_filename(info.get("title", "audio"), fmt),
            size=out.stat().st_size,
            finished=time.time(),
        )
    except Exception as exc:  # noqa: BLE001 - se reporta al usuario
        shutil.rmtree(job_dir, ignore_errors=True)
        update_job(
            job_id,
            status="error",
            error=str(exc).splitlines()[0][:300],
            finished=time.time(),
        )


def worker_loop():
    """Toma trabajos de la cola en orden de llegada."""
    while True:
        job_id = job_queue.get()
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None or job["status"] != "queued":
                job = None  # cancelado mientras esperaba
            else:
                job["status"] = "downloading"
        if job:
            run_conversion(job_id, job["url"], job["format"], job["bitrate"])
        job_queue.task_done()


def cleanup_loop():
    """Borra trabajos terminados hace más de FILE_TTL."""
    while True:
        time.sleep(60)
        cutoff = time.time() - FILE_TTL
        with jobs_lock:
            expired = [
                jid for jid, j in jobs.items() if j.get("finished", time.time()) < cutoff
            ]
            for jid in expired:
                jobs.pop(jid, None)
        for jid in expired:
            shutil.rmtree(DOWNLOAD_DIR / jid, ignore_errors=True)


def public_job(job_id, job, position):
    keys = ("status", "progress", "error", "filename", "size", "title",
            "thumbnail", "duration", "format", "bitrate")
    data = {k: job[k] for k in keys if k in job}
    data["id"] = job_id
    data["format_label"] = FORMATS[job["format"]][0]
    if position is not None:
        data["position"] = position
    return data


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def api_info():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not is_youtube_url(url):
        return jsonify(error="Ingresa un enlace válido de YouTube"), 400
    try:
        info = extract_info(url)
    except DownloadError as exc:
        return jsonify(error=str(exc).splitlines()[0][:300]), 422

    duration = info.get("duration") or 0
    return jsonify(
        id=info.get("id"),
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        duration=duration,
        thumbnail=info.get("thumbnail"),
        too_long=duration > MAX_DURATION,
        max_duration=MAX_DURATION,
        bitrates=ALLOWED_BITRATES,
        formats=[
            {"id": k, "label": v[0], "uses_bitrate": v[2]} for k, v in FORMATS.items()
        ],
    )


@app.post("/api/convert")
def api_convert():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    fmt = str(data.get("format", "mp3"))
    bitrate = str(data.get("bitrate", "192"))
    if not is_youtube_url(url):
        return jsonify(error="Ingresa un enlace válido de YouTube"), 400
    if fmt not in FORMATS:
        return jsonify(error="Formato no permitido"), 400
    if bitrate not in ALLOWED_BITRATES:
        return jsonify(error="Calidad no permitida"), 400

    try:
        info = extract_info(url)
    except DownloadError as exc:
        return jsonify(error=str(exc).splitlines()[0][:300]), 422
    if (info.get("duration") or 0) > MAX_DURATION:
        return jsonify(error="El video supera la duración máxima permitida"), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "seq": next(job_seq),
            "url": info["webpage_url"],
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration") or 0,
            "format": fmt,
            "bitrate": bitrate if FORMATS[fmt][2] else None,
        }
    job_queue.put(job_id)
    return jsonify(job_id=job_id), 202


@app.get("/api/jobs")
def api_jobs():
    with jobs_lock:
        ordered = sorted(jobs.items(), key=lambda kv: kv[1]["seq"])
        waiting = [jid for jid, j in ordered if j["status"] == "queued"]
        result = [
            public_job(jid, j, waiting.index(jid) + 1 if jid in waiting else None)
            for jid, j in ordered
        ]
    return jsonify(jobs=result)


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify(error="Trabajo no encontrado o expirado"), 404
        return jsonify(public_job(job_id, job, None))


@app.delete("/api/jobs/<job_id>")
def api_delete_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify(error="Trabajo no encontrado o expirado"), 404
        if job["status"] in ("downloading", "converting"):
            return jsonify(error="No se puede quitar un trabajo en proceso"), 409
        jobs.pop(job_id)
    shutil.rmtree(DOWNLOAD_DIR / job_id, ignore_errors=True)
    return "", 204


@app.get("/api/download/<job_id>")
def api_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "done" or not Path(job["path"]).exists():
        abort(404)
    return send_file(
        job["path"],
        mimetype=FORMATS[job["format"]][1],
        as_attachment=True,
        download_name=job["filename"],
    )


for _ in range(WORKERS):
    threading.Thread(target=worker_loop, daemon=True).start()
threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
