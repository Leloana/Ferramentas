"""Letra oficial alinhada à voz, reaproveitando o karaokê (mesmo repositório).

1. `palavras_alinhadas`: o alinhador forçado do karaokê (`karaoke/server/utils/lrc_pro.py`,
   torchaudio MMS_FA) põe cada palavra da letra oficial no tempo em que ela é cantada no
   stem de voz. Com as palavras do Whisper ele também acha a estrutura da gravação
   (versos repetidos/pulados ao vivo) e com o LRC do LRCLIB alinha verso a verso.
   Verso que o alinhador não acha ("fallback": tempo por sílabas) não é confiável:
   nesses trechos ficam as palavras do Whisper.
2. `musica_do_karaoke`: música já instalada no karaokê vira entrada da partitura: voz e
   acompanhamento já separados e a letra já alinhada (e talvez revisada) em segments.json.

Sem LLM: alinhamento acústico (CTC) e regras. Sem o karaokê ao lado, tudo devolve None e a
partitura segue com o Whisper.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KARAOKE_SERVER = AQUI.parent / "karaoke" / "server"
KARAOKE_SONGS = KARAOKE_SERVER / "songs"

# alinhamento aceito quando ao menos esta fração dos versos foi achada no áudio
MIN_VERSOS_ALINHADOS = 0.5
# palavra do Whisper entra no buraco de um verso não alinhado se cair dentro dele (± margem)
MARGEM_S = 0.3


def _importar_karaoke():
    if not KARAOKE_SERVER.is_dir():
        return None
    if str(KARAOKE_SERVER) not in sys.path:
        sys.path.append(str(KARAOKE_SERVER))  # no fim: módulos da partitura têm prioridade
    try:
        import utils.audio  # noqa: F401  (o lrc_pro carrega o áudio por ele)
    except ImportError:
        # utils.audio importa o pydub (que no Python 3.13 pede audioop-lts) só pra uma
        # função de outro caminho; aqui basta carregar o wav em 16 kHz mono
        import types

        def load_audio_full(path):
            import librosa
            return librosa.load(str(path), sr=16000, mono=True)[0]

        stub = types.ModuleType("utils.audio")
        stub.load_audio_full = load_audio_full
        sys.modules["utils.audio"] = stub
        import utils
        utils.audio = stub
    try:
        from utils import lrc_pro  # noqa: WPS433
    except Exception as e:  # dependência faltando (unidecode, rapidfuzz, pydub, av...)
        print(f"[alinhamento] alinhador do karaokê indisponível ({e}); segue com o Whisper")
        return None
    return lrc_pro


def palavras_de_segmentos(segmentos):
    """segments.json do karaokê -> (palavras [(ini, fim, texto)], janelas de versos não alinhados)."""
    palavras, ruins = [], []
    for seg in segmentos:
        base = float(seg.get("sing_start", 0.0))
        timed = seg.get("lyrics_timed") or []
        if seg.get("align") == "fallback" or not timed:
            ruins.append((float(seg.get("sing_start", 0.0)), float(seg.get("sing_end", 0.0))))
            continue
        for w in timed:
            txt = (w.get("word") or "").strip()
            if not txt:
                continue
            ini = base + float(w["expected_start"])
            fim = base + float(w.get("expected_end", w["expected_start"]))
            palavras.append((round(ini, 3), round(max(fim, ini + 0.05), 3), txt))
    palavras.sort()
    return palavras, ruins


def combinar(alinhadas, ruins, whisper):
    """Palavras alinhadas + as do Whisper só onde o verso não foi alinhado."""
    extra = [p for p in whisper
             if any(a - MARGEM_S <= p[0] and p[1] <= b + MARGEM_S for a, b in ruins)
             and not any(q[0] < p[1] and p[0] < q[1] for q in alinhadas)]
    return sorted(alinhadas + extra), len(extra)


def palavras_alinhadas(voz_wav: Path, letra_oficial: str, idioma: str, whisper=None,
                       sincronizada: str | None = None, align_fn=None):
    """Devolve (palavras, relatório) ou (None, motivo) quando não dá pra confiar."""
    lrc_pro = _importar_karaoke()
    if lrc_pro is None:
        return None, "karaoke indisponivel"
    transcrever = None
    if whisper:
        ditas = [{"word": t, "start": a, "end": b} for a, b, t in whisper]
        transcrever = lambda _audio: ditas  # noqa: E731  (o Whisper já rodou; não transcreve de novo)
    print("[alinhamento] alinhando a letra oficial na voz (MMS_FA do karaokê)...")
    try:
        segmentos, _ = lrc_pro.align_lyrics_forced(
            str(voz_wav), letra_oficial, language=idioma, synced_lrc=sincronizada,
            transcribe_fn=transcrever, align_fn=align_fn)
    except Exception as e:
        print(f"[alinhamento] falhou ({e}); segue com o Whisper")
        return None, f"falhou: {e}"
    alinhadas, ruins = palavras_de_segmentos(segmentos)
    total = len(segmentos)
    ok = total - len(ruins)
    rel = dict(versos=total, alinhados=ok, palavras_alinhadas=len(alinhadas))
    if not total or ok / total < MIN_VERSOS_ALINHADOS:
        print(f"[alinhamento] só {ok}/{total} versos alinhados; segue com o Whisper")
        return None, rel
    palavras, extra = combinar(alinhadas, ruins, whisper or [])
    rel["palavras_whisper_nos_buracos"] = extra
    print(f"[alinhamento] {ok}/{total} versos alinhados, {len(alinhadas)} palavras da letra oficial"
          f" + {extra} do Whisper nos versos não alinhados")
    return palavras, rel


# ------------------------------------------------------------------ músicas do karaokê

def pasta_do_karaoke(nome: str) -> Path:
    p = Path(nome)
    if p.is_dir():
        return p.resolve()
    p = KARAOKE_SONGS / nome
    if p.is_dir():
        return p
    raise SystemExit(f"música do karaokê não encontrada: {nome} (procurei em {KARAOKE_SONGS})")


def musica_do_karaoke(pasta: Path, trabalho: Path):
    """Prepara a entrada a partir de uma música instalada no karaokê.

    Devolve dict: audio (mix voz+acompanhamento, wav), voz (wav), acompanhamento (mp3),
    titulo, artista, idioma, palavras (ou None se a letra não estiver boa), plain_lyrics.
    """
    import numpy as np
    import soundfile as sf
    import librosa

    meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    info = meta.get("meta", {})
    voz_mp3, acomp = pasta / "vocal.mp3", pasta / "backing_track.mp3"
    if not voz_mp3.exists() or not acomp.exists():
        raise SystemExit(f"{pasta.name}: falta vocal.mp3 ou backing_track.mp3 (música não instalada nesta máquina)")
    destino = trabalho / "karaoke" / pasta.name
    destino.mkdir(parents=True, exist_ok=True)
    voz_wav, mix_wav = destino / "vocals.wav", destino / f"{pasta.name}.wav"
    # o Demucs nomeia a pasta pelo arquivo: backing_track.mp3 de músicas diferentes colidiria
    acomp_local = destino / f"{pasta.name}_acompanhamento.mp3"
    if not acomp_local.exists():
        import shutil
        shutil.copyfile(acomp, acomp_local)
    if not (voz_wav.exists() and mix_wav.exists()):
        sr = 44100
        v, _ = librosa.load(str(voz_mp3), sr=sr, mono=True)
        a, _ = librosa.load(str(acomp), sr=sr, mono=True)
        n = max(len(v), len(a))
        v, a = np.pad(v, (0, n - len(v))), np.pad(a, (0, n - len(a)))
        mix = v + a
        pico = float(np.max(np.abs(mix))) or 1.0
        sf.write(str(voz_wav), v, sr)
        sf.write(str(mix_wav), mix / max(1.0, pico), sr)
    palavras = None
    seg_path = pasta / "segments.json"
    qualidade = meta.get("alignment_quality", {}) or {}
    if seg_path.exists():
        segmentos = json.loads(seg_path.read_text(encoding="utf-8"))
        if isinstance(segmentos, dict):
            segmentos = segmentos.get("segments", [])
        palavras, ruins = palavras_de_segmentos(segmentos)
        revisar = meta.get("needs_review") and (qualidade.get("score") or 0) < 60
        if revisar or not palavras or len(ruins) > len(segmentos) * (1 - MIN_VERSOS_ALINHADOS):
            print(f"[karaoke] letra marcada pra revisão no karaokê (nota {qualidade.get('score')}); "
                  "a partitura transcreve de novo")
            palavras = None
    return dict(audio=mix_wav, voz=voz_wav, acompanhamento=acomp_local,
                titulo=info.get("title") or pasta.name, artista=info.get("artist") or "",
                idioma=info.get("language") or "pt", palavras=palavras,
                plain_lyrics=(meta.get("lyrics") or {}).get("plain_lyrics"),
                # lyrics.lrc do karaokê já está no tempo deste áudio: serve de janela por verso
                synced_lyrics=(pasta / "lyrics.lrc").read_text(encoding="utf-8")
                if (pasta / "lyrics.lrc").exists() else None)
