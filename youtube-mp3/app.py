"""Convertidor YouTube -> MP3 (uso interno).

Servidor Flask que usa yt-dlp para descargar el audio y ffmpeg para
convertirlo a MP3. Flujo similar a y2mate:
  1. /api/info      -> metadatos del video (título, miniatura, duración)
  2. /api/convert   -> crea un trabajo de conversión en segundo plano
  3. /api/status    -> progreso del trabajo
  4. /api/download  -> entrega el MP3 terminado
"""

import os
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
ALLOWED_BITRATES = {"128", "192", "256", "320"}
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


def is_youtube_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_HOSTS


def safe_filename(title):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", title).strip()
    return (name[:120] or "audio") + ".mp3"


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


def run_conversion(job_id, url, bitrate):
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

    opts = base_ydl_opts() | {
        "format": "bestaudio/best",
        "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            },
            {"key": "FFmpegMetadata"},
        ],
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        mp3 = next(job_dir.glob("*.mp3"), None)
        if mp3 is None:
            raise RuntimeError("No se generó el archivo MP3")
        update_job(
            job_id,
            status="done",
            progress=100,
            path=str(mp3),
            filename=safe_filename(info.get("title", "audio")),
            size=mp3.stat().st_size,
        )
    except Exception as exc:  # noqa: BLE001 - se reporta al usuario
        shutil.rmtree(job_dir, ignore_errors=True)
        update_job(job_id, status="error", error=str(exc).splitlines()[0][:300])


def cleanup_loop():
    """Borra trabajos y archivos más antiguos que FILE_TTL."""
    while True:
        time.sleep(60)
        cutoff = time.time() - FILE_TTL
        with jobs_lock:
            expired = [jid for jid, j in jobs.items() if j["created"] < cutoff]
            for jid in expired:
                jobs.pop(jid, None)
        for jid in expired:
            shutil.rmtree(DOWNLOAD_DIR / jid, ignore_errors=True)


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
        bitrates=sorted(ALLOWED_BITRATES, key=int),
    )


@app.post("/api/convert")
def api_convert():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    bitrate = str(data.get("bitrate", "192"))
    if not is_youtube_url(url):
        return jsonify(error="Ingresa un enlace válido de YouTube"), 400
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
        jobs[job_id] = {"status": "queued", "progress": 0, "created": time.time()}
    threading.Thread(
        target=run_conversion, args=(job_id, info["webpage_url"], bitrate), daemon=True
    ).start()
    return jsonify(job_id=job_id), 202


@app.get("/api/status/<job_id>")
def api_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify(error="Trabajo no encontrado o expirado"), 404
        public = {k: job[k] for k in ("status", "progress", "error", "filename", "size") if k in job}
    return jsonify(public)


@app.get("/api/download/<job_id>")
def api_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "done" or not Path(job["path"]).exists():
        abort(404)
    return send_file(
        job["path"],
        mimetype="audio/mpeg",
        as_attachment=True,
        download_name=job["filename"],
    )


threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
