"""YouTube Audio for MCAUTOS.

Spotube-style separation: YouTube Music supplies track metadata/catalog and MCAUTOS's
existing yt-dlp extractor supplies actual audio URLs. Spotube's NewPipe engine is
part of its host runtime, not a portable Python module.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))

import music
from extractor import Extractor
from protocol import Failure, require_text, results, run, section

ENGINE = Extractor("youtube", ["music"])
SOURCE = "youtube_audio"
CATEGORIES = (
    ("trending", "Популярные песни", "top songs 2026"),
    ("pop", "Поп", "pop music hits"),
    ("rock", "Рок", "rock music"),
    ("electronic", "Электронная", "electronic music"),
    ("live", "Живые выступления", "live music"),
    ("relax", "Релакс", "relaxing ambient music"),
)

def map_items(items):
    out = []
    for row in items or []:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        value = dict(row)
        value["source"] = SOURCE
        value["kind"] = "music"
        out.append(value)
    return out

def search(request):
    query = require_text(request, "query")
    page = request.get("page", 1)
    category = request.get("category", "songs")
    error = None
    try:
        found = music.search(query, category, page)
        items = map_items(found.get("items", []))
        if items:
            return results(items, found.get("next_page"))
    except (Failure, OSError, ValueError, KeyError) as exc:
        error = str(exc)
    # Fallback if YouTube Music changes its internal API or returns zero songs.
    try:
        found = ENGINE.search({"query": query, "kind": "music", "page": page})
        items = map_items(found.get("items", []))
        if items:
            return results(items, found.get("next_page"))
    except Failure as exc:
        if error:
            raise Failure("source_unavailable", "YouTube Music: " + error + "; yt-dlp: " + str(exc))
        raise
    if error:
        raise Failure("music_catalog_unavailable", error)
    return results([])

def browse(request):
    key = request.get("section", "home")
    page = request.get("page", 1)
    if key == "home":
        # Real YouTube Music shelves, not synthetic metadata-only placeholders.
        try:
            home = music.home()
            shelves = [
                section("ytmusic-" + str(group.get("id", i)), group.get("title", "Музыка"),
                        map_items(group.get("items", [])))
                for i, group in enumerate(home.get("sections", []))
                if group.get("items")
            ]
            if shelves:
                return {"sections": shelves}
        except (Failure, OSError, ValueError, KeyError):
            pass
        # Fast fallback for users whose YouTube Music catalog is blocked or changed.
        shelves = []
        errors = []
        for ident, title, query in CATEGORIES[:3]:
            try:
                songs = search({"query": query, "page": 1})["items"]
                if songs:
                    shelves.append(section(ident, title, songs))
            except Failure as exc:
                errors.append(str(exc))
        if shelves:
            return {"sections": shelves}
        raise Failure("catalog_unavailable", "YouTube Music и резервный поиск не вернули контент. " +
                      (errors[0] if errors else "Проверьте сеть и актуальность yt-dlp."))
    category = next((entry for entry in CATEGORIES if entry[0] == key), None)
    if category:
        return {"sections": [section(category[0], category[1],
                                      search({"query": category[2], "page": page})["items"])]}
    if key.startswith("ytmusic-"):
        # Home shelf contents are rendered inline. Refetch fresh home on navigation.
        home = music.home()
        for i, group in enumerate(home.get("sections", [])):
            if "ytmusic-" + str(group.get("id", i)) == key:
                return {"sections": [section(key, group.get("title", "Музыка"), map_items(group.get("items", [])))]}
        raise Failure("section_unavailable", "Подборка больше не доступна — обновите главную страницу")
    if isinstance(key, str) and key.startswith("https://"):
        data = ENGINE.browse({"section": key, "page": page, "kind": "music"})
        for group in data.get("sections", []):
            group["items"] = map_items(group.get("items", []))
        return data
    raise Failure("unsupported_section", "Неизвестная подборка: " + str(key))

def resolve(request):
    identifier = require_text(request, "id")
    return ENGINE.resolve({**request, "id": identifier, "kind": "music"})

def match(request):
    title = str(request.get("title") or "").strip()
    artists = request.get("artists") or []
    artist = ", ".join((str(a.get("name") if isinstance(a, dict) else a)
                        for a in artists if a))
    query = (artist + " " + title).strip()
    if not query:
        raise Failure("invalid_request", "Укажите название и/или исполнителя")
    matches = search({"query": query, "page": 1})["items"]
    if not matches:
        raise Failure("no_match", "Музыка не найдена")
    return resolve({"id": matches[0]["id"], "page": 1})

def download(request):
    return ENGINE.download({**request, "kind": "music"})

def formats(request):
    return ENGINE.formats({**request, "kind": "music"})

if __name__ == "__main__":
    sys.exit(run({"search": search, "browse": browse, "resolve": resolve,
                  "match": match, "download": download, "formats": formats}))
