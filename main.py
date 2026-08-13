"""
Wavelin backend — risoluzione audio self-hosted con yt-dlp.

Espone due endpoint:
  GET /api/search?q=...      -> {"results": [{id,title,author,thumbnail,duration}, ...]}
  GET /api/stream/{video_id} -> {"url","title","author","thumbnail","duration"}

Nessun servizio di terzi: yt-dlp parla direttamente con YouTube.
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

COOKIES_FILE = os.environ.get("YT_COOKIES_FILE", "cookies.txt")

app = FastAPI(title="Wavelin backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def pick_thumbnail(entry):
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return entry.get("thumbnail")


@app.get("/")
def root():
    return {"ok": True, "message": "Wavelin backend attivo."}


@app.get("/api/debug")
def debug():
    return {
        "cwd": os.getcwd(),
        "cookies_file_path": COOKIES_FILE,
        "cookies_exists": os.path.exists(COOKIES_FILE),
        "cookies_size": os.path.getsize(COOKIES_FILE) if os.path.exists(COOKIES_FILE) else None,
        "etc_secrets_exists": os.path.exists("/etc/secrets/cookies.txt"),
    }


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": True,
        "default_search": "ytsearch20",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(q, download=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"search failed: {e}")

    entries = (info or {}).get("entries") or []
    results = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        results.append({
            "id": e.get("id"),
            "title": e.get("title"),
            "author": e.get("uploader") or e.get("channel"),
            "thumbnail": pick_thumbnail(e),
            "duration": e.get("duration") or 0,
        })
    return {"results": results}


@app.get("/api/stream/{video_id}")
def stream(video_id: str):
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "extractor_args": {"youtube": {"player_client": ["web"]}},
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"resolve failed: {e}")

    if not info:
        raise HTTPException(status_code=502, detail="no info returned")

    stream_url = info.get("url")
    if not stream_url and info.get("requested_formats"):
        stream_url = info["requested_formats"][0].get("url")
    if not stream_url:
        raise HTTPException(status_code=502, detail="no audio stream found")

    return {
        "url": stream_url,
        "title": info.get("title"),
        "author": info.get("uploader"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration") or 0,
    }
