"""Álbum de uma música (nome, ano, faixa), guardado em `meta.json["album"]`.

A lista agrupa as músicas de cada artista por álbum. A busca é a do iTunes (a
mesma das capas, sem chave): entre os resultados do mesmo artista e mesmo
título, fica o álbum de estúdio mais antigo — tributo, ao vivo, coletânea e
"Deluxe"/"Remaster" não contam como outro álbum. Só aparece em single? Vai para
"Singles e outras" na lista (`kind: "single"`); sem resultado, `kind: "unknown"`.

    {"name": "Is This It", "year": 2001, "track": 7, "kind": "album", "source": "itunes"}

Editar à mão no editor do meta.json vale: `fill_album` não sobrescreve um álbum
já preenchido (só com `force=True`). Só biblioteca padrão.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from collections import Counter
from pathlib import Path

from utils.cover import _BAD_ALBUM_RE, _get, _norm, _similar

logger = logging.getLogger(__name__)

KINDS = ("album", "single", "unknown")
# "(Deluxe Edition)", "[2024 Remaster]": o mesmo álbum, não outro
_EDITION_RE = re.compile(
    r"\s*[\(\[][^\)\]]*(deluxe|edition|remaster|anniversary|bonus|expanded|version|special|reissue)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(r"\s+-\s+single$", re.IGNORECASE)
_EP_RE = re.compile(r"\s+-\s+ep$", re.IGNORECASE)
_EP_NAME_RE = re.compile(r"\bep\b", re.IGNORECASE)
# outra gravação da música: só vale se o título da biblioteca também disser
_OTHER_TAKE_RE = re.compile(
    r"\blive\b|ao vivo|demo|remix|\bversion\b|vers[aã]o|acoustic|ac[uú]stic|\bedit\b|instrumental",
    re.IGNORECASE,
)
# coletânea que não é o disco original (o iTunes às vezes data com o ano da 1ª gravação)
_COMPILATION_RE = re.compile(
    r"\bbox\b|maxximum|\banos\b|perfil|millennium|collection|cole[cç][aã]o|sucessos|o melhor|\bfocus\b|"
    r"definitive|retrospect|grandes|s[eé]rie|raridades|essencia|singles|time flies|soundtrack|trilha",
    re.IGNORECASE,
)
_REMASTER_RE = re.compile(r"[\(\[]?\s*(\d{4}\s+)?remaster(ed)?(\s+\d{4})?\s*[\)\]]?", re.IGNORECASE)


def _title_key(title: str) -> str:
    """'Don’t Look Back In Anger' = "Don't Look Back in Anger (Remastered)";
    "Undone - The Sweater Song" = "Undone (The Sweater Song)" (o que vem depois de " - " cai)."""
    title = re.split(r"\s+-\s+", title or "")[0]
    return _norm(_REMASTER_RE.sub(" ", re.sub(r"['’`´]", "", title)))


def clean_album_name(name: str) -> str:
    """'Hybrid Theory (Deluxe Edition)' → 'Hybrid Theory'; 'X - EP' → 'X (EP)'."""
    name = _EDITION_RE.sub("", name or "").strip()
    if _EP_RE.search(name):
        name = _EP_RE.sub("", name).strip() + " (EP)"
    return name


def _year(release_date: str | None) -> int | None:
    match = re.match(r"(\d{4})", release_date or "")
    return int(match.group(1)) if match else None


def _tier(artist: str, collection: str, track_count: int) -> int:
    """0 = álbum de estúdio, 1 = EP, 2 = coletânea (só se não houver outro)."""
    if _COMPILATION_RE.search(collection) or (
            _norm(artist) and _norm(artist) in _norm(collection) and _norm(artist) != _norm(clean_album_name(collection))):
        return 2  # "Maxximum - Chico Buarque", "Box - Los Hermanos" (mas "Weezer" é o disco)
    if _EP_RE.search(collection) or _EP_NAME_RE.search(collection) or track_count <= 6:
        return 1
    return 0


def pick_album(artist: str, title: str, results: list[dict]) -> dict:
    """Escolhe o álbum entre resultados do iTunes (`entity=song`). Puro, testável."""
    want_title = _title_key(title)
    albums, singles = [], []
    for r in results:
        if _similar(artist, r.get("artistName")) < 0.85:
            continue
        if _title_key(r.get("trackName")) != want_title:  # o _norm tira "(...)": "Last Nite (Live)" casa
            continue
        collection = r.get("collectionName") or ""
        if _OTHER_TAKE_RE.search(r.get("trackName") or "") and not _OTHER_TAKE_RE.search(title or ""):
            continue
        if _BAD_ALBUM_RE.search(collection) and not _BAD_ALBUM_RE.search(title or ""):
            continue
        if (r.get("collectionArtistName") or "").lower() in ("various artists", "vários artistas"):
            continue
        if _SINGLE_RE.search(collection) or (r.get("trackCount") or 0) <= 2:
            singles.append(r)
        else:
            albums.append(r)
    if not albums:
        return {"name": None, "year": None, "track": None, "kind": "single" if singles else "unknown",
                "source": "itunes"}

    by_name: dict[str, list[dict]] = {}
    for r in albums:
        by_name.setdefault(clean_album_name(r["collectionName"]), []).append(r)

    def rank(name: str) -> tuple:
        rows = by_name[name]
        years = [y for y in (_year(r.get("releaseDate")) for r in rows) if y]
        tier = min(_tier(artist, r["collectionName"], r.get("trackCount") or 0) for r in rows)
        return (tier, min(years) if years else 9999, -len(rows))

    name = min(by_name, key=rank)
    rows = by_name[name]
    years = Counter(y for y in (_year(r.get("releaseDate")) for r in rows) if y)
    year = min(y for y, c in years.items() if c == max(years.values())) if years else None
    # faixa da edição normal (a deluxe às vezes renumera)
    plain = [r for r in rows if clean_album_name(r["collectionName"]) == r["collectionName"]] or rows
    return {"name": name, "year": year, "track": plain[0].get("trackNumber"), "kind": "album",
            "source": "itunes"}


def _itunes_songs(term: str, country: str, by_title: bool = False) -> list[dict]:
    params = {"term": term, "entity": "song", "limit": 50 if by_title else 25, "country": country}
    if by_title:
        params["attribute"] = "songTerm"  # só pelo título: a busca "artista título" às vezes só traz covers
    query = urllib.parse.urlencode(params)
    return json.loads(_get(f"https://itunes.apple.com/search?{query}").decode("utf-8")).get("results") or []


# catálogo do artista por (artista, loja): a biblioteca tem várias músicas do mesmo
_CATALOG_CACHE: dict[tuple[str, str], list[dict]] = {}


def _artist_catalog(artist: str, country: str) -> list[dict]:
    """Até 200 músicas do artista (busca o id do artista, depois o lookup). Acha a faixa
    que a busca por texto não traz ("EARFQUAKE" só voltava covers) e evita a banda
    homônima (o artista mais relevante da busca é o que fica)."""
    key = (_norm(artist), country)
    if key not in _CATALOG_CACHE:
        query = urllib.parse.urlencode({"term": artist, "entity": "musicArtist", "limit": 5, "country": country})
        found = json.loads(_get(f"https://itunes.apple.com/search?{query}").decode("utf-8")).get("results") or []
        match = next((a for a in found if _similar(artist, a.get("artistName")) >= 0.85), None)
        songs = []
        if match:
            query = urllib.parse.urlencode({"id": match["artistId"], "entity": "song", "limit": 200, "country": country})
            data = json.loads(_get(f"https://itunes.apple.com/lookup?{query}").decode("utf-8"))
            songs = [r for r in data.get("results") or [] if r.get("wrapperType") == "track"]
        _CATALOG_CACHE[key] = songs
    return _CATALOG_CACHE[key]


def lookup_album(artist: str, title: str) -> dict | None:
    """Álbum pelo iTunes: catálogo do artista, busca "artista título" e busca só pelo
    título, na loja dos EUA e depois na do Brasil. None = rede fora em todas."""
    if not artist or not title:
        return {"name": None, "year": None, "track": None, "kind": "unknown", "source": "itunes"}
    clean_title = _REMASTER_RE.sub(" ", title).strip()
    best = None
    for country in ("US", "BR"):
        sources = (
            lambda: _artist_catalog(artist, country),
            lambda: _itunes_songs(f"{artist} {clean_title}", country),
            lambda: _itunes_songs(clean_title, country, by_title=True),
        )
        for source in sources:
            try:
                found = pick_album(artist, title, source())
            except Exception as e:  # rede fora, limite de pedidos: tenta de novo noutra hora
                logger.info(f"[Álbum] iTunes ({country}) indisponível para {artist} - {title}: {e}")
                continue
            if found["kind"] == "album":
                return found
            if best is None or (best["kind"] == "unknown" and found["kind"] == "single"):
                best = found
    return best


def album_of(meta: dict) -> dict | None:
    album = meta.get("album")
    return album if isinstance(album, dict) and album.get("kind") in KINDS else None


def fill_album(song_dir: Path, force: bool = False) -> dict | None:
    """Busca e grava `meta.json["album"]`. Bloqueante (use em thread)."""
    meta_path = Path(song_dir) / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    current = album_of(meta)
    if current and not force:
        return current
    info = meta.get("meta") or {}
    album = lookup_album(info.get("artist") or "", info.get("title") or "")
    if album is None:
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))  # relê: outra rota pode ter salvo no meio
    meta["album"] = album
    with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)
    return album


def fill_missing_albums(songs_dir: Path, pause_sec: float = 3.0) -> int:
    """Preenche o álbum das músicas que ainda não têm (na subida do servidor). Bloqueante."""
    import time

    done = 0
    for song_dir in sorted(Path(songs_dir).iterdir()):
        meta_path = song_dir / "meta.json"
        if not song_dir.is_dir() or not meta_path.exists():
            continue
        try:
            if album_of(json.loads(meta_path.read_text(encoding="utf-8"))):
                continue
        except (OSError, ValueError):
            continue
        if fill_album(song_dir):
            done += 1
        time.sleep(pause_sec)  # a busca do iTunes limita ~20 pedidos por minuto
    return done
