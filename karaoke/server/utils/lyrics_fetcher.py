"""Busca letras de música via LRCLIB (primário) e, sem ele, sites de letra.

Ordem: LRCLIB (única com tempos) → Lyrics.ovh → letras.com.br → Genius (busca
pela API oficial com KARAOKE_GENIUS_TOKEN do .env, letra lida da página). Os sites
dão só o texto: o reinstall encaixa no áudio pela estrutura (lrc_sync). Letras.com
e Cifra Club bloqueiam robôs ("Access Denied") e ficam de fora.

Com a duração do áudio, o LRCLIB é consultado pelo `/api/search` e vence a
versão de duração mais próxima: a mesma música costuma ter dezenas de entradas
(estúdio, remaster, ao vivo, o álbum inteiro numa faixa só) e a sincronia de
uma não serve para a outra. LRC de versão longe demais não volta (só o texto).
Sem a duração (ao adicionar, antes do download) vale o `/api/get` exato e, se ele
não achar (ex.: "、" no título × ", " no LRCLIB), o `/api/search`.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Optional

from rapidfuzz import fuzz
from unidecode import unidecode

from utils.env_file import load_env_file

logger = logging.getLogger(__name__)
load_env_file()  # KARAOKE_GENIUS_TOKEN

LRCLIB_API = "https://lrclib.net/api/get"
LRCLIB_SEARCH_API = "https://lrclib.net/api/search"
OVH_API = "https://api.lyrics.ovh/v1"
REQUEST_TIMEOUT = 10
USER_AGENT = "KaraokeAI/1.0"

# Versão do LRCLIB aceita para a sincronia: até isso de diferença de duração.
# Acima disso é outra versão (ao vivo, edit, estendida): vale só o texto, e o
# alinhamento acha os tempos no áudio.
SYNC_MAX_DURATION_DIFF_SEC = 20.0
# nomes que o /api/search devolve e ainda são a mesma música
TRACK_MIN_SIMILARITY = 85
ARTIST_MIN_SIMILARITY = 70


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _name_key(text: str) -> str:
    """Nome para comparar: sem acento, sem "(Remastered 2009)", "- Live" etc."""
    text = unidecode(text or "").lower()
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    text = re.sub(r"\s+-\s+.*$", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def pick_lrclib_candidate(candidates: list, artist: str, track: str, duration: Optional[float]) -> Optional[dict]:
    """Entrada do /api/search que serve para um áudio de `duration` segundos.

    Só a mesma música (nome parecido, não instrumental). Entre as sincronizadas,
    a de duração mais próxima. Nenhuma sincronizada perto: a de duração mais
    próxima com letra, sem o LRC (a sincronia seria de outra versão).
    Sem `duration`: a 1ª sincronizada (o reinstall acerta a versão depois).
    """
    want_track, want_artist = _name_key(track), _name_key(artist)
    same = []
    for c in candidates or []:
        if not isinstance(c, dict) or c.get("instrumental"):
            continue
        if not (c.get("plainLyrics") or "").strip():
            continue
        if fuzz.token_set_ratio(_name_key(c.get("trackName")), want_track) < TRACK_MIN_SIMILARITY:
            continue
        if fuzz.token_set_ratio(_name_key(c.get("artistName")), want_artist) < ARTIST_MIN_SIMILARITY:
            continue
        diff = abs(float(c["duration"]) - duration) if c.get("duration") and duration else float("inf")
        same.append((diff, c))
    if not same:
        return None
    if not duration:
        best = next((c for _, c in same if (c.get("syncedLyrics") or "").strip()), same[0][1])
        return {**best, "durationDiff": None}
    synced = sorted((x for x in same if (x[1].get("syncedLyrics") or "").strip()), key=lambda x: x[0])
    if synced and synced[0][0] <= SYNC_MAX_DURATION_DIFF_SEC:
        diff, best = synced[0]
        return {**best, "durationDiff": diff}
    diff, best = min(same, key=lambda x: x[0])
    return {**best, "syncedLyrics": None, "durationDiff": diff}


def search_lyrics_lrclib(artist: str, track: str, duration: Optional[float]) -> Optional[dict]:
    """LRCLIB /api/search + `pick_lrclib_candidate`. Mesmo formato de `fetch_lyrics_lrclib`."""
    params = urllib.parse.urlencode({"artist_name": artist, "track_name": track})
    url = f"{LRCLIB_SEARCH_API}?{params}"
    logger.info(f"[LyricsFetcher] LRCLIB search: GET {url} (áudio de {f'{duration:.1f}s' if duration else '? s'})")
    try:
        candidates = _get_json(url)
    except Exception as e:
        logger.warning(f"[LyricsFetcher] LRCLIB search falhou: {e}")
        return None
    best = pick_lrclib_candidate(candidates, artist, track, duration)
    if not best:
        logger.info("[LyricsFetcher] LRCLIB search: nenhuma versão da mesma música.")
        return None
    synced = (best.get("syncedLyrics") or "").strip() or None
    logger.info(
        "[LyricsFetcher] LRCLIB search: %d candidatos, escolhida id=%s (%ss, diferença %ss), syncedLyrics=%s",
        len(candidates or []), best.get("id"), best.get("duration"), None if best["durationDiff"] is None else round(best["durationDiff"], 1),
        "presente" if synced else "ausente (versão longe demais)",
    )
    return {
        "plainLyrics": best["plainLyrics"].strip(),
        "syncedLyrics": synced,
        "source": "lrclib",
        "duration": best.get("duration"),
    }


def fetch_lyrics_lrclib(artist: str, track: str) -> Optional[dict]:
    """Busca letra no LRCLIB. Retorna dict com plainLyrics e syncedLyrics (pode ser None)."""
    params = urllib.parse.urlencode({
        "artist_name": artist,
        "track_name": track,
    })
    url = f"{LRCLIB_API}?{params}"
    logger.info(f"[LyricsFetcher] LRCLIB: GET {url}")

    try:
        data = _get_json(url)
    except Exception as e:
        logger.warning(f"[LyricsFetcher] LRCLIB falhou: {e}")
        return None

    plain = (data.get("plainLyrics") or "").strip()
    synced = (data.get("syncedLyrics") or "").strip() or None

    if not plain:
        logger.info("[LyricsFetcher] LRCLIB retornou mas sem plainLyrics.")
        return None

    logger.info(
        "[LyricsFetcher] LRCLIB sucesso: plainLyrics=%d chars, syncedLyrics=%s",
        len(plain), "presente" if synced else "ausente",
    )
    return {
        "plainLyrics": plain,
        "syncedLyrics": synced,
        "source": "lrclib",
        "duration": data.get("duration"),
    }


def fetch_lyrics_ovh(artist: str, track: str) -> Optional[dict]:
    """Busca letra no Lyrics.ovh (fallback). Retorna apenas plainLyrics, sem syncedLyrics."""
    safe_artist = urllib.parse.quote(artist, safe="")
    safe_track = urllib.parse.quote(track, safe="")
    url = f"{OVH_API}/{safe_artist}/{safe_track}"
    logger.info(f"[LyricsFetcher] Lyrics.ovh: GET {url}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KaraokeAI/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[LyricsFetcher] Lyrics.ovh falhou: {e}")
        return None

    plain = (data.get("lyrics") or "").strip()
    if not plain:
        logger.info("[LyricsFetcher] Lyrics.ovh retornou mas sem lyrics.")
        return None

    logger.info("[LyricsFetcher] Lyrics.ovh sucesso: plainLyrics=%d chars", len(plain))
    return {
        "plainLyrics": plain,
        "syncedLyrics": None,
        "source": "ovh",
    }


def fetch_lyrics(artist: str, track: str, duration: float | None = None) -> Optional[dict]:
    """Orquestra a busca: LRCLIB primeiro, depois Lyrics.ovh como fallback.

    `duration` (segundos do áudio que vai tocar): escolhe a versão pelo
    `/api/search`; sem resultado lá, cai no `/api/get` de sempre. Sem `duration`:
    `/api/get` exato e, sem resultado, o `/api/search`.
    """
    result = search_lyrics_lrclib(artist, track, duration) if duration else None
    if not result:
        result = fetch_lyrics_lrclib(artist, track)
        if result and duration and result.get("duration") and result.get("syncedLyrics") \
                and abs(float(result["duration"]) - duration) > SYNC_MAX_DURATION_DIFF_SEC:
            logger.info("[LyricsFetcher] LRC do /api/get é de outra versão (%ss × %.1fs): só o texto",
                        result["duration"], duration)
            result = {**result, "syncedLyrics": None}
    if not result and not duration:
        result = search_lyrics_lrclib(artist, track, None)
    if result:
        return _normalized(result)
    logger.info("[LyricsFetcher] LRCLIB sem resultado, tentando Lyrics.ovh e sites de letra...")
    # sites de letra: só o texto; o reinstall encaixa no áudio pela estrutura
    for source in (fetch_lyrics_ovh, fetch_lyrics_letras_br, fetch_lyrics_genius):
        try:
            result = source(artist, track)
        except Exception as e:
            logger.warning(f"[LyricsFetcher] {source.__name__} falhou: {e}")
            result = None
        if result:
            return _normalized(result)
    return None


def _normalized(result: dict) -> Optional[dict]:
    """Saída igual para toda fonte: letra normalizada (quebras de linha, linhas vazias)
    e LRC sem espaço nas pontas. Antes só a rota de upload normalizava; a da fila
    gravava no meta.json a letra como a fonte mandou."""
    from utils.text import normalize_lyrics_text

    plain = normalize_lyrics_text(result.get("plainLyrics")) or None
    synced = "\n".join((result.get("syncedLyrics") or "").splitlines()).strip() or None
    if not plain and not synced:
        return None
    return {**result, "plainLyrics": plain, "syncedLyrics": synced}


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130 Safari/537.36")
LETRAS_BR = "https://www.letras.com.br"
GENIUS_SEARCH_API = "https://api.genius.com/search"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """letras.com.br manda música inexistente para outra página: isso é "não achei"."""

    def redirect_request(self, *args, **kwargs):
        return None


def _get_page(url: str) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.info(f"[LyricsFetcher] {url}: {e}")
        return None


def clean_web_lyrics(text: str) -> Optional[str]:
    """Texto de site: sem marcação de seção ([Refrão], [Verso 1]) e sem linhas vazias repetidas."""
    lines = [ln.strip() for ln in html.unescape(text or "").splitlines()]
    lines = [ln for ln in lines if not re.fullmatch(r"\[[^\]]*\]", ln)]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out if len(out) >= 40 else None


def title_variants(track: str) -> list[str]:
    """"Rap do Obito (Naruto)" também como "Rap do Obito"; "X - Remastered 2009" como "X"."""
    base = re.sub(r"\s*[\(\[].*?[\)\]]", "", track or "").strip()
    base = re.sub(r"\s+-\s+.*$", "", base).strip()
    return [v for v in dict.fromkeys([(track or "").strip(), base]) if v]


def fetch_lyrics_letras_br(artist: str, track: str) -> Optional[dict]:
    """letras.com.br/<artista>/<música>: o endereço é o slug dos dois (o site não tem busca aberta)."""
    from utils.text import slugify

    for title in title_variants(track):
        url = f"{LETRAS_BR}/{slugify(artist)}/{slugify(title)}"
        page = _get_page(url)
        m = re.search(r':lyrics="`(.*?)`"', page or "", re.S)
        plain = clean_web_lyrics(m.group(1)) if m else None
        if plain:
            logger.info("[LyricsFetcher] letras.com.br sucesso: %s (%d chars)", url, len(plain))
            return {"plainLyrics": plain, "syncedLyrics": None, "source": "letras.com.br"}
    return None


class _GeniusLyrics(HTMLParser):
    """Texto dos <div data-lyrics-container="true"> (a página quebra a letra em vários)."""

    def __init__(self):
        super().__init__()
        self.depth = 0   # profundidade de <div> dentro de um container de letra
        self.skip = 0    # dentro de trecho excluído da seleção (cabeçalho, anúncio)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.depth:
            if tag == "div" and a.get("data-lyrics-container") == "true":
                self.depth = 1
                self.out.append("\n")
            return
        if tag == "br":
            if not self.skip:
                self.out.append("\n")
            return
        if self.skip or "data-exclude-from-selection" in a:
            self.skip += 1
        if tag == "div":
            self.depth += 1

    def handle_endtag(self, tag):
        if not self.depth or tag == "br":
            return
        if self.skip:
            self.skip -= 1
        if tag == "div":
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.out.append(data)


def genius_lyrics_from_html(page: str) -> str:
    parser = _GeniusLyrics()
    parser.feed(page)
    return "".join(parser.out)


def fetch_lyrics_genius(artist: str, track: str) -> Optional[dict]:
    """Genius: acha a música pela API oficial (token do .env) e lê a letra da página."""
    token = os.environ.get("KARAOKE_GENIUS_TOKEN", "").strip()
    if not token:
        return None
    title = title_variants(track)[-1]
    url = f"{GENIUS_SEARCH_API}?{urllib.parse.urlencode({'q': f'{artist} {title}'})}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            hits = (json.loads(resp.read().decode("utf-8")).get("response") or {}).get("hits") or []
    except Exception as e:
        logger.warning(f"[LyricsFetcher] Genius busca falhou: {e}")
        return None
    want_title, want_artist = _name_key(title), _name_key(artist)

    def _close(name: str, want: str, minimum: int) -> bool:
        # "ネクライトーキー (NECRY TALKIE)": o nome entre parênteses também vale
        keys = [_name_key(name)] + [_name_key(p) for p in re.findall(r"[\(\[](.*?)[\)\]]", name or "")]
        return any(fuzz.token_set_ratio(k, want) >= minimum for k in keys if k)

    # título mais parecido primeiro: "bloom" casa também com "bloom -Anime size-"
    candidates = [h.get("result") or {} for h in hits[:5]]
    candidates.sort(key=lambda s: -fuzz.ratio(_name_key(s.get("title", "")), want_title))
    for song in candidates:
        if not _close(song.get("title", ""), want_title, TRACK_MIN_SIMILARITY):
            continue
        if not _close((song.get("primary_artist") or {}).get("name", ""), want_artist, ARTIST_MIN_SIMILARITY):
            continue
        page = _get_page(song.get("url", ""))
        plain = clean_web_lyrics(genius_lyrics_from_html(page)) if page else None
        if plain:
            logger.info("[LyricsFetcher] Genius sucesso: %s (%d chars)", song.get("url"), len(plain))
            return {"plainLyrics": plain, "syncedLyrics": None, "source": "genius"}
    logger.info("[LyricsFetcher] Genius: nenhum resultado da mesma música.")
    return None
