"""Capa do álbum de uma música, guardada em `server/songs/<slug>/cover.jpg`.

Candidatos de três fontes, sem chave de API: busca do iTunes (vários
resultados), busca do Deezer e a miniatura do vídeo do YouTube. Cada um ganha
uma nota pela semelhança do artista/título com a música e perde pontos se o
álbum parece tributo, karaokê, ao vivo ou coletânea — antes ia o 1º resultado
do iTunes, e "A Wolf at the Door" saía com a capa de um álbum tributo.

- `find_cover`: automático, usa o melhor candidato (1ª vez; depois o arquivo).
- `cover_options` / `choose_cover`: a pessoa escolhe outra capa na TV. Só
  aceita URL que veio da própria lista (`cover.options.json`), nada arbitrário.
Sem nada, grava `cover.none` para não repetir a busca (apague para tentar de novo).
Só biblioteca padrão (mesmo esquema do lyrics_fetcher).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 6
COVER_NAME = "cover.jpg"
MISS_NAME = "cover.none"
OPTIONS_NAME = "cover.options.json"
CHOICE_NAME = "cover.choice.json"
MAX_OPTIONS = 12
# o cartão do fim estica a capa até ~1600 px num celular de tela densa: 600 ficava borrado
ITUNES_SIZE = "1200x1200bb"
_ITUNES_SIZE_RE = re.compile(r"/\d+x\d+bb\.jpg$")
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([\w-]{11})")
# álbum que quase nunca é a capa certa da música original
_BAD_ALBUM_RE = re.compile(
    r"tribute|homenagem|songbook|portrait of|karaok|instrumental|cover|lullab|ao vivo|\blive\b|greatest hits|best of|"
    r"the very best|essential|anthology|colet[aâ]nea|hits|remix|piano|acoustic|ac[uú]stic|8-bit|sped up|slowed",
    re.IGNORECASE,
)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Karaoke/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text.lower())  # "(Remastered)", "[Live]"
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def score_candidate(artist: str, title: str, cand_artist: str, cand_title: str, album: str) -> float:
    """0..1: artista pesa mais que o título; álbum de tributo/karaokê/ao vivo perde."""
    title_sim = _similar(title, cand_title)
    score = 0.55 * _similar(artist, cand_artist) + 0.45 * title_sim
    if title_sim < 0.5:  # outra música do mesmo artista: capa de outro álbum
        score -= 0.3
    if album and _BAD_ALBUM_RE.search(album) and not _BAD_ALBUM_RE.search(title or ""):
        score -= 0.35
    return round(max(0.0, score), 3)


def _itunes(artist: str, title: str) -> list[dict]:
    term = f"{artist} {title}".strip()
    if not term:
        return []
    query = urllib.parse.urlencode({"term": term, "entity": "song", "limit": 12})
    data = json.loads(_get(f"https://itunes.apple.com/search?{query}").decode("utf-8"))
    out = []
    for r in data.get("results") or []:
        art = r.get("artworkUrl100")
        if not art:
            continue
        out.append({
            "url": art.replace("100x100bb", ITUNES_SIZE),  # a URL aceita qualquer tamanho
            "thumb": art.replace("100x100bb", "200x200bb"),
            "source": "iTunes",
            "album": r.get("collectionName") or "",
            "score": score_candidate(artist, title, r.get("artistName"), r.get("trackName"), r.get("collectionName")),
        })
    return out


def _deezer(artist: str, title: str) -> list[dict]:
    if not (artist or title):
        return []
    # a busca simples acha mais que a avançada (artist:"x" track:"y" vinha vazia)
    q = f"{artist} {title}".strip()
    data = json.loads(_get("https://api.deezer.com/search?" + urllib.parse.urlencode({"q": q, "limit": 10})).decode("utf-8"))
    out = []
    for r in data.get("data") or []:
        album = r.get("album") or {}
        if not album.get("cover_xl"):
            continue
        out.append({
            "url": album["cover_xl"],
            "thumb": album.get("cover_medium") or album["cover_xl"],
            "source": "Deezer",
            "album": album.get("title") or "",
            "score": score_candidate(artist, title, (r.get("artist") or {}).get("name"), r.get("title"), album.get("title")),
        })
    return out


def youtube_id(url: str | None) -> str | None:
    match = _YT_ID_RE.search(url or "")
    return match.group(1) if match else None


def _read_meta(song_dir: Path) -> dict:
    try:
        return json.loads((song_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def collect_candidates(song_dir: Path) -> tuple[list[dict], bool]:
    """Todos os candidatos, do melhor para o pior. Devolve (lista, houve_erro_de_rede)."""
    meta = _read_meta(song_dir)
    info = meta.get("meta") or {}
    audio = meta.get("audio") or {}
    artist, title = info.get("artist") or "", info.get("title") or ""
    found, had_error = [], False
    for source in (_itunes, _deezer):
        try:
            found.extend(source(artist, title))
        except Exception as e:  # rede fora, API mudou... a capa é opcional
            logger.info(f"[Capa] {source.__name__} indisponível para {song_dir.name}: {e}")
            had_error = True
    vid = youtube_id(audio.get("youtube_vocal_url") or audio.get("youtube_backing_url"))
    if vid:
        # miniatura do vídeo: sempre disponível, mas raramente é a arte do álbum
        found.append({"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                      "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                      "source": "YouTube", "album": "Vídeo", "score": 0.3})

    seen, unique = set(), []
    for cand in sorted(found, key=lambda c: -c["score"]):
        key = cand["url"].split("/")[-2] if cand["source"] == "iTunes" else cand["url"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    return unique[:MAX_OPTIONS], had_error


def _save_options(song_dir: Path, options: list[dict]) -> None:
    try:
        (song_dir / OPTIONS_NAME).write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def hd_url(url: str) -> str:
    """Versão grande da mesma capa: iTunes em 1200 px, miniatura do YouTube em 1280x720
    (a hqdefault tem 480x360 com faixas pretas). Outras URLs ficam como estão."""
    if "mzstatic.com" in url:
        return _ITUNES_SIZE_RE.sub(f"/{ITUNES_SIZE}.jpg", url)
    if "i.ytimg.com" in url:
        return url.replace("/hqdefault.jpg", "/maxresdefault.jpg")
    return url


def _download_best(url: str, dest: Path) -> bool:
    """Baixa a versão grande; sem ela (vídeo sem maxres, 404), a URL original."""
    big = hd_url(url)
    return (big != url and _download(big, dest)) or _download(url, dest)


def _download(url: str, dest: Path) -> bool:
    try:
        data = _get(url)
        if len(data) < 500:  # resposta vazia/erro disfarçado
            return False
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True
    except Exception as e:
        logger.info(f"[Capa] Falha ao baixar {url}: {e}")
        return False


def find_cover(song_dir: Path) -> Path | None:
    """Devolve o caminho da capa, baixando na primeira vez. Bloqueante (use em thread)."""
    cover = song_dir / COVER_NAME
    legacy = cover.exists() and not (song_dir / OPTIONS_NAME).exists() and not (song_dir / CHOICE_NAME).exists()
    if cover.exists() and not legacy:
        return cover
    if legacy:
        # capa do algoritmo antigo (1º resultado do iTunes, às vezes um tributo):
        # escolhe de novo uma vez; sem rede, fica a que já estava
        candidates, _ = collect_candidates(song_dir)
        if candidates:
            _save_options(song_dir, candidates)
            for cand in candidates:
                if _download_best(cand["url"], cover):
                    break
        return cover
    if (song_dir / MISS_NAME).exists() or not song_dir.is_dir():
        return None

    candidates, had_error = collect_candidates(song_dir)
    _save_options(song_dir, candidates)
    for cand in candidates:
        if _download_best(cand["url"], cover):
            return cover
        had_error = True

    if had_error:
        return None  # tenta de novo na próxima vez
    try:
        (song_dir / MISS_NAME).write_text("", encoding="utf-8")
    except OSError:
        pass
    return None


def cover_options(song_dir: Path) -> dict:
    """Opções para a pessoa escolher (busca de novo se ainda não há lista salva)."""
    options = []
    try:
        options = json.loads((song_dir / OPTIONS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not options:
        options, _ = collect_candidates(song_dir)
        _save_options(song_dir, options)
    current = None
    try:
        current = json.loads((song_dir / CHOICE_NAME).read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError):
        current = options[0]["url"] if options and (song_dir / COVER_NAME).exists() else None
    return {"options": options, "current": current}


def choose_cover(song_dir: Path, url: str) -> bool:
    """Troca a capa por uma das opções listadas. False se a URL não é da lista ou falhou."""
    options = cover_options(song_dir)["options"]
    if not any(o["url"] == url for o in options):
        return False
    if not _download_best(url, song_dir / COVER_NAME):
        return False
    (song_dir / MISS_NAME).unlink(missing_ok=True)
    try:
        (song_dir / CHOICE_NAME).write_text(json.dumps({"url": url}), encoding="utf-8")
    except OSError:
        pass
    return True


def current_cover_url(song_dir: Path) -> str | None:
    """URL de onde veio a capa em disco: a escolhida na TV ou a 1ª opção da lista."""
    try:
        return json.loads((song_dir / CHOICE_NAME).read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError):
        pass
    try:
        options = json.loads((song_dir / OPTIONS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return options[0]["url"] if options else None


def upgrade_cover(song_dir: Path) -> bool:
    """Troca uma capa baixada pequena (iTunes 600, YouTube 480) pela versão grande da
    mesma imagem. True se trocou; sem rede ou sem versão grande, a capa fica."""
    cover = song_dir / COVER_NAME
    url = current_cover_url(song_dir) if cover.exists() else None
    if not url or hd_url(url) == url:
        return False
    return _download(hd_url(url), cover)
