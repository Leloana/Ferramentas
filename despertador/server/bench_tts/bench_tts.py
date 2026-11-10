"""Compara motores de TTS locais (sem GPU) para a voz de reserva do despertador.

Gera o mesmo roteiro com cada motor, um de cada vez, em prioridade baixa, e mede:
tempo de carga do modelo, tempo de síntese, duração do áudio, fator de tempo real
(síntese ÷ duração; < 1 = mais rápido que tempo real) e pico de memória do processo.

Cuidado com o resto do servidor (ver docs/TESTE_TTS_SERVIDOR.md):
- roda com nice 19 e um número limitado de threads (--threads);
- antes de cada motor, espera a carga do sistema baixar (--carga-max) e pula se não baixar;
- um motor por vez, cada um num subprocesso que é encerrado ao terminar (libera a RAM).

Uso (Linux):
  nice -n 19 ionice -c3 .venv-tts/bin/python bench_tts/bench_tts.py \
      --roteiro conteudo/2026-11-10/roteiro.json --motores piper,kokoro,xtts --threads 4
"""
from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MOTORES = ("piper", "kokoro", "xtts", "chatterbox", "qwen", "teste")


# --------------------------------------------------------------------------- worker
def _limitar_threads(n: int) -> None:
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = str(n)
    try:
        os.nice(19)
    except (AttributeError, OSError):
        pass


def _salvar_wav(caminho: Path, amostras, taxa: int) -> None:
    import numpy as np
    a = np.clip(np.asarray(amostras, dtype="float32"), -1, 1)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa)
        w.writeframes((a * 32767).astype("<i2").tobytes())


def motor_teste(texto: str, saida: Path, args) -> dict:
    """Motor falso (silêncio de 2 s) só para validar o próprio script."""
    t0 = time.perf_counter()
    with wave.open(str(saida), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\0\0" * 32000)
    return {"carga_s": 0.0, "sintese_s": time.perf_counter() - t0, "voz": "silêncio"}


def motor_piper(texto: str, saida: Path, args) -> dict:
    from piper import PiperVoice  # pip install piper-tts
    modelo = Path(args.piper_modelo)
    if not modelo.exists():
        raise RuntimeError(f"modelo Piper não encontrado: {modelo} "
                           f"(baixe com: python -m piper.download_voices {modelo.stem} --data-dir {modelo.parent})")
    t0 = time.perf_counter()
    voz = PiperVoice.load(str(modelo))
    carga = time.perf_counter() - t0
    t0 = time.perf_counter()
    with wave.open(str(saida), "wb") as w:
        if hasattr(voz, "synthesize_wav"):      # piper-tts >= 1.3
            voz.synthesize_wav(texto, w)
        else:                                    # piper-tts 1.2
            voz.synthesize(texto, w)
    return {"carga_s": carga, "sintese_s": time.perf_counter() - t0, "voz": modelo.stem}


def motor_kokoro(texto: str, saida: Path, args) -> dict:
    import numpy as np
    import torch
    torch.set_num_threads(args.threads)
    from kokoro import KPipeline  # pip install kokoro ; precisa de espeak-ng no sistema para pt
    t0 = time.perf_counter()
    pipe = KPipeline(lang_code="p")  # p = português do Brasil
    carga = time.perf_counter() - t0
    t0 = time.perf_counter()
    partes = [np.asarray(audio) for _, _, audio in pipe(texto, voice=args.kokoro_voz, speed=1.0)]
    _salvar_wav(saida, np.concatenate(partes), 24000)
    return {"carga_s": carga, "sintese_s": time.perf_counter() - t0, "voz": args.kokoro_voz}


def motor_xtts(texto: str, saida: Path, args) -> dict:
    import torch
    torch.set_num_threads(args.threads)
    os.environ.setdefault("COQUI_TOS_AGREED", "1")  # licença CPML: uso pessoal não comercial
    from TTS.api import TTS  # pip install coqui-tts
    t0 = time.perf_counter()
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
    carga = time.perf_counter() - t0
    vozes = list(getattr(tts, "speakers", None) or [])
    voz = args.xtts_voz if (not vozes or args.xtts_voz in vozes) else vozes[0]
    t0 = time.perf_counter()
    tts.tts_to_file(text=texto, speaker=voz, language="pt", file_path=str(saida), split_sentences=True)
    return {"carga_s": carga, "sintese_s": time.perf_counter() - t0, "voz": voz,
            "vozes_disponiveis": len(vozes)}


def _paragrafos(texto: str, maximo: int = 300) -> list[str]:
    """Quebra em trechos curtos (parágrafos/frases) para modelos com limite por geração."""
    import re
    trechos = []
    for par in [p.strip() for p in texto.split("\n") if p.strip()]:
        atual = ""
        for frase in re.split(r"(?<=[.!?])\s+", par):
            if atual and len(atual) + len(frase) + 1 > maximo:
                trechos.append(atual); atual = frase
            else:
                atual = f"{atual} {frase}".strip()
        if atual:
            trechos.append(atual)
    return trechos


def _juntar(partes, taxa: int, pausa_s: float = 0.35):
    import numpy as np
    silencio = np.zeros(int(taxa * pausa_s), dtype="float32")
    saida = []
    for p in partes:
        saida += [np.asarray(p, dtype="float32").reshape(-1), silencio]
    return np.concatenate(saida)


def motor_chatterbox(texto: str, saida: Path, args) -> dict:
    import torch
    torch.set_num_threads(args.threads)
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # pip install chatterbox-tts
    disp = "cuda" if (args.gpu and torch.cuda.is_available()) else "cpu"
    t0 = time.perf_counter()
    modelo = ChatterboxMultilingualTTS.from_pretrained(device=disp)
    carga = time.perf_counter() - t0
    t0 = time.perf_counter()
    partes = [modelo.generate(t, language_id="pt", cfg_weight=args.cb_cfg, exaggeration=args.cb_exag)
              .squeeze(0).cpu().numpy() for t in _paragrafos(texto)]
    _salvar_wav(saida, _juntar(partes, modelo.sr), modelo.sr)
    return {"carga_s": carga, "sintese_s": time.perf_counter() - t0,
            "voz": f"padrão ({disp}) cfg={args.cb_cfg} exag={args.cb_exag}"}


# Tags de estilo no roteiro, ex.: "[animado] Bom dia!". Cada parágrafo herda a tag que o abre;
# a tag vira a instrução (`instruct`) do Qwen3-TTS. Para os outros motores as tags são removidas.
TAGS = {
    "animado": "Speak like a cheerful, energetic Brazilian morning radio host, smiling, upbeat and warm.",
    "noticia": "Speak like a clear, confident Brazilian news anchor, natural pace, engaging but neutral.",
    "serio": "Speak in a calm, serious and steady news tone.",
    "leve": "Speak in a relaxed, friendly and light conversational tone.",
    "despedida": "Speak warmly and cheerfully, like saying goodbye to a friend in the morning.",
}
_TAG_RE = re.compile(r"^\s*\[([a-zà-ú]+)\]\s*", re.IGNORECASE)


def sem_tags(texto: str) -> str:
    return "\n".join(_TAG_RE.sub("", l) for l in texto.split("\n"))


def _trechos_com_tag(texto: str, maximo: int) -> list[tuple[str, str]]:
    trechos, tag = [], ""
    for par in [p for p in texto.split("\n") if p.strip()]:
        m = _TAG_RE.match(par)
        if m:
            tag = m.group(1).lower()
            par = par[m.end():]
        trechos += [(tag, t) for t in _paragrafos(par, maximo)]
    return trechos


def motor_qwen(texto: str, saida: Path, args) -> dict:
    import torch
    torch.set_num_threads(args.threads)
    from qwen_tts import Qwen3TTSModel  # pip install qwen-tts
    disp = "cuda:0" if (args.gpu and torch.cuda.is_available()) else "cpu"
    t0 = time.perf_counter()
    modelo = Qwen3TTSModel.from_pretrained(args.qwen_modelo, device_map=disp,
                                           dtype=torch.bfloat16 if disp != "cpu" else torch.float32)
    carga = time.perf_counter() - t0
    t0 = time.perf_counter()
    partes, taxa, instrucao_ok = [], 24000, True
    trechos = _trechos_com_tag(texto, args.qwen_max_trecho)
    for i, (tag, t) in enumerate(trechos, 1):
        instr = TAGS.get(tag) or args.qwen_instrucao
        if args.qwen_modo == "design":
            # VoiceDesign: a voz é descrita em texto; o estilo da tag vai junto.
            kw = dict(text=t, language="Portuguese", instruct=f"{args.qwen_descricao} {instr}".strip())
            wavs, taxa = modelo.generate_voice_design(**kw)
            print(f"trecho {i}/{len(trechos)} [{tag or '-'}] {len(t)} car.", flush=True)
            partes.append(wavs[0])
            continue
        kw = dict(text=t, language="Portuguese", speaker=args.qwen_voz)
        if instr and instrucao_ok:
            kw["instruct"] = instr
        try:
            wavs, taxa = modelo.generate_custom_voice(**kw)
        except (TypeError, ValueError) as e:
            if "instruct" not in kw:
                raise
            print(f"modelo não aceitou instruct ({e}); seguindo sem", flush=True)
            instrucao_ok = False
            kw.pop("instruct")
            wavs, taxa = modelo.generate_custom_voice(**kw)
        print(f"trecho {i}/{len(trechos)} [{tag or '-'}] {len(t)} car.", flush=True)
        partes.append(wavs[0])
    _salvar_wav(saida, _juntar(partes, taxa, 0.3), taxa)
    return {"carga_s": carga, "sintese_s": time.perf_counter() - t0,
            "voz": ("design" if args.qwen_modo == "design" else args.qwen_voz) + f" ({disp}){' +instrução' if instrucao_ok and (args.qwen_instrucao or any(tg for tg, _ in trechos)) else ''}",
            "trechos": len(trechos)}


def worker(args) -> None:
    _limitar_threads(args.threads)
    texto = json.loads(Path(args.roteiro).read_text(encoding="utf-8"))["texto"].strip()
    if args._motor != "qwen":
        texto = sem_tags(texto)
    saida = Path(args.saida) / f"{args._motor}.wav"
    r = globals()[f"motor_{args._motor}"](texto, saida, args)
    with wave.open(str(saida), "rb") as w:
        r["duracao_audio_s"] = w.getnframes() / w.getframerate()
    r["caracteres"] = len(texto)
    print("RESULTADO " + json.dumps(r, ensure_ascii=False), flush=True)


# --------------------------------------------------------------------------- orquestrador
def carga_1min() -> float | None:
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return None


def memoria_disponivel_mb() -> int | None:
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable:"):
                return int(linha.split()[1]) // 1024
    except OSError:
        pass
    return None


def esperar_folga(args) -> str | None:
    """Devolve None quando pode rodar, ou o motivo para pular."""
    prazo = time.time() + args.espera_max * 60
    while True:
        carga, mem = carga_1min(), memoria_disponivel_mb()
        ok_carga = carga is None or carga <= args.carga_max
        ok_mem = mem is None or mem >= args.mem_min_mb
        if ok_carga and ok_mem:
            return None
        if time.time() > prazo:
            return f"servidor ocupado (carga {carga}, memória livre {mem} MB)"
        print(f"  aguardando folga: carga={carga} (máx {args.carga_max}), "
              f"memória livre={mem} MB (mín {args.mem_min_mb})", flush=True)
        time.sleep(30)


def rodar_motor(motor: str, args) -> dict:
    motivo = esperar_folga(args)
    if motivo:
        return {"motor": motor, "status": "pulado", "erro": motivo}
    cmd = [sys.executable, __file__, "--_motor", motor] + [a for a in sys.argv[1:]]
    t0 = time.perf_counter()
    carga_antes = carga_1min()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env=env)
    saida_txt: list[str] = []
    for linha in p.stdout:  # mostra o progresso e guarda o log
        saida_txt.append(linha)
        if not linha.startswith("RESULTADO "):
            print("   |", linha.rstrip()[:200], flush=True)
    pico_mb = None
    if hasattr(os, "wait4"):
        _, status, uso = os.wait4(p.pid, 0)
        codigo = os.waitstatus_to_exitcode(status)
        pico_mb = round(uso.ru_maxrss / 1024)  # Linux: KB
    else:
        codigo = p.wait()
    r = {"motor": motor, "total_s": round(time.perf_counter() - t0, 1),
         "carga_antes": carga_antes, "pico_memoria_mb": pico_mb}
    resultado = [l for l in saida_txt if l.startswith("RESULTADO ")]
    if codigo == 0 and resultado:
        dados = json.loads(resultado[-1][len("RESULTADO "):])
        dados["rtf"] = round(dados["sintese_s"] / max(dados["duracao_audio_s"], 0.01), 2)
        r.update(status="ok", **{k: (round(v, 1) if isinstance(v, float) and k != "rtf" else v) for k, v in dados.items()})
    else:
        r.update(status="erro", erro="".join(saida_txt[-15:]).strip()[-1500:])
    return r


def para_mp3(wav: Path) -> None:
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "96k", str(wav.with_suffix(".mp3"))],
                       check=True)
    except (OSError, subprocess.CalledProcessError):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roteiro", default=str(AQUI.parent / "conteudo/2026-11-10/roteiro.json"))
    ap.add_argument("--motores", default="piper,kokoro,xtts")
    ap.add_argument("--saida", default=str(AQUI / "saida"))
    ap.add_argument("--threads", type=int, default=4, help="threads de CPU por motor (deixe folga para o resto)")
    ap.add_argument("--carga-max", type=float, default=None, help="load average de 1 min máximo para começar "
                    "(padrão: metade dos núcleos)")
    ap.add_argument("--mem-min-mb", type=int, default=7000, help="memória disponível mínima para começar")
    ap.add_argument("--espera-max", type=int, default=30, help="minutos esperando folga antes de pular o motor")
    ap.add_argument("--piper-modelo", default=str(AQUI / "modelos/pt_BR-faber-medium.onnx"))
    ap.add_argument("--kokoro-voz", default="pm_alex")
    ap.add_argument("--xtts-voz", default="Damien Black")
    ap.add_argument("--qwen-modelo", default="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
    ap.add_argument("--qwen-voz", default="Ryan")
    ap.add_argument("--qwen-instrucao", default="", help="instrução de estilo padrão (as [tags] do roteiro têm prioridade)")
    ap.add_argument("--qwen-modo", choices=("custom", "design"), default="custom",
                    help="custom = vozes prontas (CustomVoice); design = voz descrita em texto (VoiceDesign)")
    ap.add_argument("--qwen-descricao", default="A Brazilian Portuguese male radio news presenter in his 40s, "
                    "warm, deep and clear voice, native accent from São Paulo, natural and friendly.")
    ap.add_argument("--cb-cfg", type=float, default=0.5, help="Chatterbox: menor = fala mais calma (0.3 recomendado p/ quem fala rápido)")
    ap.add_argument("--cb-exag", type=float, default=0.5, help="Chatterbox: exagero de emoção (0.25 a 2)")
    ap.add_argument("--qwen-max-trecho", type=int, default=160, help="caracteres por geração (curto evita pular texto)")
    ap.add_argument("--gpu", action="store_true", help="usar CUDA se houver (só para comparar qualidade no PC)")
    ap.add_argument("--_motor", choices=MOTORES, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.carga_max is None:
        args.carga_max = (os.cpu_count() or 2) / 2
    Path(args.saida).mkdir(parents=True, exist_ok=True)

    if args._motor:
        worker(args)
        return

    motores = [m.strip() for m in args.motores.split(",") if m.strip()]
    for m in motores:
        if m not in MOTORES:
            sys.exit(f"motor desconhecido: {m} (opções: {', '.join(MOTORES)})")
    print(f"CPU lógicas: {os.cpu_count()} | threads por motor: {args.threads} | "
          f"carga máx: {args.carga_max} | memória livre: {memoria_disponivel_mb()} MB", flush=True)
    resultados = []
    for m in motores:
        print(f"\n== {m}", flush=True)
        r = rodar_motor(m, args)
        resultados.append(r)
        if r["status"] == "ok":
            para_mp3(Path(args.saida) / f"{m}.wav")
        print(f"   -> {json.dumps(r, ensure_ascii=False)[:400]}", flush=True)

    (Path(args.saida) / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    linhas = ["| motor | status | voz | carga do modelo (s) | síntese (s) | áudio (s) | RTF | pico RAM (MB) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        v = lambda k: "" if r.get(k) is None else r[k]
        linhas.append(f"| {r['motor']} | {r['status']} | {v('voz')} | {v('carga_s')} | {v('sintese_s')} | "
                      f"{v('duracao_audio_s')} | {v('rtf')} | {v('pico_memoria_mb')} |")
    tabela = "\n".join(linhas)
    (Path(args.saida) / "resultados.md").write_text(tabela + "\n", encoding="utf-8")
    print("\n" + tabela)


if __name__ == "__main__":
    main()
