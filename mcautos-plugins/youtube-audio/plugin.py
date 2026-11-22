"""MCAUTOS native YouTube music adapter, built on the existing _shared/extractor.py.

This is NOT the Spotube Hetu/NewPipe runtime: Spotube requires its own host NewPipe API.
Uses the same MCAUTOS yt-dlp extraction engine as built-in Plugins/youtube.
"""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from protocol import Failure, require_text, results, run, section
from extractor import Extractor

source = Extractor("youtube", ["music"])
SOURCE_ID = "youtubeaudio"
KIND = "music"
TOPICS = [["music_hits","Популярная музыка","top music official audio"],["live","Живые выступления","live concert music"],["electronic","Электронная музыка","electronic music mix"],["rock","Рок","rock music official audio"]]

def normalize(rows):
    for record in rows:
        record["source"] = SOURCE_ID
        record["kind"] = KIND
    return rows

def search(request):
    output = source.search({**request, "kind": KIND, "page": request.get("page", 1)})
    normalize(output.get("items", []))
    return output

def browse(request):
    key = request.get("section", "home")
    if key == "home":
        groups = []
        failures = []
        for ident, title, query in TOPICS:
            try:
                found = search({"query": query, "page": 1})["items"]
                if found:
                    groups.append(section(ident, title, found))
            except Failure as exc:
                failures.append(str(exc))
        if groups:
            return {"sections": groups}
        if failures:
            raise Failure("browse_failed", "YouTube не вернул подборки: " + failures[0])
        raise Failure("empty_catalog", "YouTube вернул пустые подборки. Проверьте yt-dlp")
    topic = next((t for t in TOPICS if t[0] == key), None)
    if topic:
        return {"sections": [section(topic[0], topic[1], search({"query": topic[2], "page": request.get("page", 1)})["items"])]}
    # Accept YouTube public playlist/channel URLs just like MCAUTOS's own YouTube source.
    data = source.browse({**request, "kind": KIND})
    for group in data.get("sections", []):
        normalize(group.get("items", []))
    return data

def resolve(request):
    return source.resolve({**request, "kind": KIND})

def download(request):
    return source.download({**request, "kind": KIND})

def match(request):
    query = (", ".join(request.get("artists") or []) + " " + str(request.get("title") or "")).strip()
    if not query:
        raise Failure("invalid_request", "Нужны title или artists")
    found = search({"query": query + " audio", "page": 1})["items"]
    if not found:
        raise Failure("no_stream", "Совпадающий трек не найден")
    return resolve({"id": found[0]["id"], "page": 1})

def formats(request):
    return source.formats({**request, "kind": KIND})

def subtitles(request):
    return {"subtitles": formats(request)["subtitles"]}

if __name__ == "__main__":
    sys.exit(run({"search": search, "browse": browse, "resolve": resolve,
                  "download": download, "match": match, "formats": formats,
                  "subtitles": subtitles}))
