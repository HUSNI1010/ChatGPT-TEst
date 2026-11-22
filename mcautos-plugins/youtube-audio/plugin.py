"""MCAUTOS YouTube source using yt-dlp (no account authentication or DRM bypass).

Requires: python3 -m pip install -U yt-dlp
Search and browsing use YouTube public results; resolve returns a short-lived direct HTTPS URL.
"""
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from protocol import Failure, require_text, results, run, item, section, stream

SOURCE = "youtubeaudio"
KIND = "music"
VIDEO_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

def library():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        raise Failure("missing_dependency", "Установите yt-dlp: python3 -m pip install -U yt-dlp")

def extract(target, flat=False):
    ytdlp = library()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "ignoreerrors": False, "noplaylist": True,
            "extract_flat": "in_playlist" if flat else False,
            "socket_timeout": 12, "retries": 1, "extractor_retries": 1,
            "cachedir": False, "http_headers": {"User-Agent": "Mozilla/5.0"}}
    try:
        with ytdlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(target, download=False)
    except Exception as exc:
        raise Failure("source_error", "YouTube недоступен или ответ изменился: " + type(exc).__name__)

def listing(query, page=1):
    # yt-dlp's search extractor has no reliable offset. Request page*N then slice.
    count = min(60, max(1, page) * 15)
    data = extract("ytsearch%d:%s" % (count, query[:100]), flat=True)
    entries = (data or {}).get("entries") or []
    rows = []
    for e in entries[(page - 1) * 15: page * 15]:
        if not isinstance(e, dict):
            continue
        ident = str(e.get("id") or "")
        if not VIDEO_RE.fullmatch(ident):
            continue
        url = "https://www.youtube.com/watch?v=" + ident
        rows.append(item(SOURCE, KIND, ident, str(e.get("title") or "Видео без названия"), url))
    return rows

def search(request):
    query = require_text(request, "query").strip()
    if not query:
        raise Failure("invalid_query", "Введите поисковый запрос")
    try:
        page = max(1, min(int(request.get("page", 1)), 4))
    except (ValueError, TypeError):
        page = 1
    rows = listing(query, page)
    return results(rows, page + 1 if len(rows) == 15 and page < 4 else None)

def browse(request):
    # Curated discovery searches, NOT YouTube's official Trending ranking.
    topics = [
        ("discover", "Найти интересное", "documentaries 2026"),
        ("tutorials", "Обучение и технологии", "programming tutorials 2026"),
    ] if KIND == "video" else [
        ("music", "Музыка", "official music video"),
        ("live", "Живые выступления", "live concert"),
    ]
    sections = []
    for key, title, query in topics:
        try:
            sections.append(section(key, title, listing(query, 1)[:12]))
        except Failure:
            continue
    return {"sections": sections}

def resolve(request):
    ident = require_text(request, "id").strip()
    if not VIDEO_RE.fullmatch(ident):
        raise Failure("invalid_id", "Неверный ID видео YouTube")
    info = extract("https://www.youtube.com/watch?v=" + ident, flat=False)
    formats = (info or {}).get("formats") or []
    candidates = []
    for f in formats:
        if not isinstance(f, dict):
            continue
        url = f.get("url") or ""
        if not url.startswith("https://"):
            continue
        if f.get("has_drm") or (f.get("protocol") or "").lower() not in ("https", "http"):
            continue
        acodec = f.get("acodec") or "none"
        vcodec = f.get("vcodec") or "none"
        ext = f.get("ext") or ""
        if KIND == "video":
            # MCAUTOS expects ONE combined playable stream. Prefer MP4 with H.264 + AAC.
            if acodec == "none" or vcodec == "none":
                continue
            if ext not in ("mp4", "webm"):
                continue
            rank = (ext == "mp4", "avc" in str(vcodec), min(int(f.get("height") or 0),1080), int(f.get("tbr") or 0))
            mime = "video/mp4" if ext == "mp4" else "video/webm"
        else:
            if acodec == "none" or vcodec != "none":
                continue
            if ext not in ("m4a", "webm", "mp3", "mp4"):
                continue
            rank = (ext in ("m4a", "mp4"), min(int(f.get("abr") or f.get("tbr") or 0), 320))
            mime = "audio/mp4" if ext in ("m4a", "mp4") else ("audio/mpeg" if ext == "mp3" else "audio/webm")
        candidates.append((rank, url, mime))
    if not candidates:
        raise Failure("not_playable", "Нет совместимого прямого потока. Попробуйте другой ролик или обновите yt-dlp")
    _, url, mime = max(candidates, key=lambda a: a[0])
    return stream(url, mime)

if __name__ == "__main__":
    sys.exit(run({"search": search, "browse": browse, "resolve": resolve}))
