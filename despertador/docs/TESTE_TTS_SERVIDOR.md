# Teste de TTS local no servidor Linux (voz de reserva do despertador)

**Para o agente do servidor.** Leia tudo antes de executar qualquer coisa.

## Contexto

O despertador usa a ElevenLabs (`eleven_v4_turbo`) como voz principal, mas o projeto só tem 10 mil créditos (~34 edições de 1 minuto). Precisamos de uma **voz local de reserva**: quando o crédito acabar ou a API falhar, o servidor gera a narração com um motor local.

O servidor tem Xeon E5-2630 v4 (10 núcleos / 20 threads), cerca de 12 GB de RAM e **nenhuma GPU**. A geração roda de madrugada e tem horas até o alarme, então velocidade não é crítica. O que importa é:

1. a qualidade da voz em português;
2. o tempo de síntese;
3. o uso de memória;
4. **não atrapalhar os outros serviços do servidor.**

Objetivo deste teste: gerar o mesmo roteiro (~1 minuto, 1.075 caracteres) com três motores, medir cada um e entregar os áudios para o proprietário escutar e escolher.

| Motor | Por que testar |
|---|---|
| **Piper** (`pt_BR-faber-medium`) | Muito leve. No PC de teste (i5-13400F) gerou 59 s de áudio em 3,3 s (RTF 0,06). Qualidade mais robótica. |
| **Kokoro** (voz `pm_alex`) | Intermediário. Português ainda não avaliado. |
| **XTTS-v2** (voz embutida `Damien Black`) | Melhor qualidade das grátis. Pesado no CPU (estimativa: alguns minutos por edição, 4–6 GB de RAM). |

## Regras de convivência com o servidor (obrigatórias)

Este servidor roda outros processos do proprietário, e eles têm prioridade sobre este teste.

- **Inventário primeiro.** Antes de instalar qualquer coisa, veja o que está rodando e quanto sobra:
  - `uptime`, `nproc`, `free -h`, `df -h`;
  - `top -bn1 | head -25`;
  - `systemctl list-units --type=service --state=running`;
  - `systemctl list-timers`, `crontab -l` (horários de picos e backups);
  - `docker ps`, se existir.

  Anote os serviços importantes e os horários de pico.
- **Escolha uma janela calma.** Se houver tarefas agendadas (backup, cron pesado), rode fora desses horários.
- **Prioridade baixa sempre.** Use `nice -n 19 ionice -c3` e no máximo **4 threads** por motor (`--threads 4`, de 20 disponíveis). O script já espera a carga baixar antes de cada motor:
  - load average de 1 min ≤ metade dos núcleos;
  - ≥ 7 GB de RAM disponível.

  Se não baixar em 30 min, ele pula o motor. Não afrouxe esses limites para forçar o teste.
- **Opcional, se funcionar sem sudo:** limitar com `systemd-run --user --scope -p MemoryMax=7G -p CPUQuota=400% <comando>`. Se pedir senha ou não existir, siga só com nice/ionice.
- **Um motor por vez.** O script já faz isso. Cada motor roda num subprocesso que termina e libera a RAM. Não rode duas cópias do script.
- **Fique de olho durante a execução.** Se algum serviço do proprietário ficar lento, der erro, ou se a memória começar a ir para swap (`free -h`, `vmstat 5`), interrompa com Ctrl+C e registre o que aconteceu.
- **Nunca** pare, reinicie, mate ou reconfigure processos e serviços que não sejam deste teste. Não altere firewall, proxy ou systemd.
- **Sem sudo/apt sem autorização do proprietário.** O Kokoro precisa de `espeak-ng` no sistema para o português. Se não estiver instalado (`which espeak-ng`), **pule o Kokoro** e anote que ele depende dessa instalação. O ffmpeg é opcional (só converte para MP3).
- **Disco:** os modelos ocupam ~3 GB (XTTS ~1,9 GB, Kokoro ~0,4 GB, Piper ~60 MB) e o PyTorch para CPU ~1 GB. Confirme espaço com `df -h` antes. Tudo fica dentro de `despertador/server`, sem cache espalhado pelo home.
- **Ao terminar** (ou se abortar), confirme que não sobrou nenhum processo do teste (`pgrep -af bench_tts`).

## Passos

Na raiz do repositório, depois do `git pull`:

```bash
cd despertador/server

# 1. Ambiente isolado só para o teste (não usar o .venv da API).
#    PyTorch CPU-only para não baixar ~2 GB de bibliotecas CUDA.
python3 -m venv .venv-tts
.venv-tts/bin/pip install --upgrade pip
.venv-tts/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-tts/bin/pip install piper-tts coqui-tts kokoro soundfile numpy
.venv-tts/bin/pip freeze > bench_tts/saida-pip-freeze.txt   # registrar versões reais

# 2. Caches de modelos dentro do projeto (gitignored).
export TTS_HOME="$PWD/bench_tts/modelos/coqui"
export HF_HOME="$PWD/bench_tts/modelos/hf"
export COQUI_TOS_AGREED=1   # XTTS: licença CPML, uso pessoal não comercial (é o caso)

# 3. Voz do Piper
.venv-tts/bin/python -m piper.download_voices pt_BR-faber-medium --data-dir bench_tts/modelos

# 4. Teste do próprio script (motor falso, 1 segundo)
.venv-tts/bin/python bench_tts/bench_tts.py --motores teste

# 5. Teste real, do mais leve para o mais pesado
nice -n 19 ionice -c3 .venv-tts/bin/python bench_tts/bench_tts.py \
    --motores piper,kokoro,xtts --threads 4 2>&1 | tee bench_tts/saida/log.txt
```

Se `coqui-tts` ou `kokoro` não instalarem na versão de Python do servidor, ou se a API instalada for diferente da usada no script, ajuste o mínimo necessário em `bench_tts/bench_tts.py` e registre o que mudou. Não invente parâmetros: confira com `--help` ou com a documentação da versão instalada.

**Opcional:** só se o servidor estiver claramente ocioso (carga perto de 0) e o XTTS tiver passado com 4 threads, rode `--motores xtts --threads 8 --saida bench_tts/saida-8t`. Isso mostra quanto ele acelera com mais núcleos.

## Entrega

1. Crie `despertador/docs/RESULTADO_TTS_SERVIDOR.md` com:
   - a tabela de `bench_tts/saida/resultados.md`;
   - o estado do servidor antes e durante o teste (carga, RAM livre, serviços importantes, se algo foi afetado);
   - versões instaladas;
   - o que foi pulado e por quê;
   - sua recomendação.
2. Copie os MP3 para `despertador/docs/amostras_tts/` (piper.mp3, kokoro.mp3, xtts.mp3; ~0,5–1 MB cada) para o proprietário escutar.
3. **Não** commite WAVs, modelos nem o `.venv-tts` (já estão no `.gitignore`).
4. Faça commit e push dessas entregas, seguindo a regra do repositório (CLAUDE.md).
5. Deixe o `.venv-tts` e os modelos no servidor. Se um motor for escolhido, eles serão reaproveitados na implementação da reserva.

A decisão de qual motor usar é do proprietário, depois de escutar. Não implemente a troca de voz no `gerar_edicao.py` nesta etapa.
