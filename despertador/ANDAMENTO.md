# Andamento do projeto e próximos passos

## Sessão de 10/11/2026 (noite) — MVP de teste construído

Decisões do proprietário: ElevenLabs em vez de XTTS (10.000 créditos separados, modelo `eleven_v4_turbo`, chave própria em `server/.env`); instalação manual do APK (via Google Drive); conteúdo da primeira rodada escolhido pelo Claude, automação depois.

Feito e verificado no PC:
- Servidor FastAPI em `server/` (venv próprio, Python 3.11): `/healthz`, `/v1/editions/latest` (ETag/304), `/v1/editions/{id}`, `/v1/assets/{id}`, token Bearer. Testado: 401 sem token, 304 com ETag, sha256 do download confere, caminho arbitrário dá 404.
- Firewall: regra existente já libera `Python311\python.exe` no perfil Público; nenhuma regra foi criada.
- Edição `2026-11-10-r1`: 5 matérias da Agência Brasil (ata do Copom, desoneração da gasolina/etanol, Lula na COP31, marco de financiamento da saúde), roteiro em `server/conteudo/2026-11-10/roteiro.json` com fontes. Narração 75 s + música 151 s (So Nice, Marcos Valle, vocal + instrumental do karaokê misturados; originais intactos; pico -1,3 dB). Vale até 12/11 06:29.
- Gasto ElevenLabs: 1.148 de 10.000 caracteres (73 do aviso embarcado + 1.075 da narração).
- App Android em `android/` (Kotlin, AGP 8.7.3, Gradle 8.11.1, minSdk 29, target 35, sem dependências). `assembleDebug` compila; permissões conferidas com aapt: INTERNET, USE_EXACT_ALARM (SCHEDULE_EXACT_ALARM só até API 32), FOREGROUND_SERVICE(+MEDIA_PLAYBACK), POST_NOTIFICATIONS, WAKE_LOCK, RECEIVE_BOOT_COMPLETED.

Correção 0.1.1 (mesma noite): o 0.1.0 fechava ao abrir no S24. Causa confirmada no emulador (Android 16): `SecurityException: ACCESS_NETWORK_STATE required for jobs with a connectivity constraint` ao agendar o job de sync. Adicionada a permissão (normal, sem prompt) e o agendamento do job passou a não derrubar o app se falhar.

Teste no emulador (Android 16, API 36.1) com o 0.1.1: app abre; sync pelo servidor do PC baixou a edição (2 arquivos, hash ok, promoção atômica); "Testar em 1 minuto" com tela bloqueada disparou na hora (alarme RTC_WAKEUP exato, serviço em primeiro plano mediaPlayback, foco de áudio USAGE_ALARM, MediaPlayer tocando); ao acender a tela o app aparece sobre o bloqueio; Parar encerra serviço e som; Soneca na notificação encerra e reagenda +9 min. Ainda falta o mesmo no S24 FE.

Teste no S24 FE (10/11/2026, noite, 0.1.1): app abre; sincronizou pela rede de casa (S24 em 192.168.15.54 baixou manifesto, narração e música); "Testar em 1 minuto" com tela bloqueada tocou certinho. Tropeço na configuração: o endereço digitado como `https://` gerou "unable to parse TLS packet header" (servidor de teste é HTTP); com `http://` funcionou. Pendentes no aparelho: modo avião, alarme recorrente real (manhã seguinte), reinício, Bluetooth/Não Perturbe.

Ainda NÃO testado (depende do aparelho): instalação, sincronização pela rede, disparo com tela bloqueada, modo avião, reinício, soneca, fallback sem jornal.

Limitações conhecidas do MVP: sem tela cheia sobre o bloqueio (o alarme aparece como notificação com Parar/Soneca; tocar nela abre o app sobre a tela de bloqueio); sem Direct Boot (depois de reiniciar, só toca após o primeiro desbloqueio); HTTP na LAN.

Próximos passos:
1. Proprietário instala o APK, configura endereço/token, sincroniza e roda "Testar em 1 minuto" com tela bloqueada e depois em modo avião.
2. Corrigir o que falhar no aparelho; avaliar tela cheia (USE_FULL_SCREEN_INTENT) se a notificação não bastar.
3. Automatizar a seleção de notícias (agy no Linux) gerando o mesmo `roteiro.json`.
4. Portar o servidor para o Linux com HTTPS e systemd.

---

## Registro anterior (preparação)

Atualizado em 10/11/2026, durante a preparação do primeiro teste local.

Este arquivo é o registro de continuidade do trabalho. Atualizar após cada etapa relevante, anotando resultados reais, falhas e pendências. Não registrar senhas, tokens ou conteúdo de `.env`.

## Objetivo atual autorizado pelo proprietário

Antes de implantar no Linux, usar este PC Windows como servidor de teste e criar um cliente Android mínimo para o Samsung S24 FE:

1. Selecionar notícias reais na internet e preparar um roteiro curto.
2. Gerar a narração neste PC com modelo TTS local já existente, preferencialmente reaproveitando `tts_platform_pt`.
3. Reutilizar uma música já baixada neste PC.
4. O celular baixa os áudios antecipadamente, agenda um alarme e, ao despertar, reproduz notícias e música localmente.
5. Manter um toque local de reserva caso falte conteúdo ou a reprodução falhe.

O proprietário avisou que a GPU poderia estar ocupada e autorizou esperar antes de gerar voz. Não interromper outros processos nem descarregar modelos alheios para liberar memória.

## Pilares confirmados pelo proprietário

- Servidor computa; celular consome.
- Menor quantidade possível de permissões no celular.
- Fallbacks inteligentes.

Para a fase Linux: há `agy` disponível no terminal, já usado pelo proprietário para buscas na internet. Também há plano pago ElevenLabs, sujeito ao saldo e ao consumo. O teste atual pede TTS local, sem necessidade de gastar créditos ElevenLabs.

## Arquivos já criados

- `README.md`: proposta, escopo, experiência, stack sugerida e limitações.
- `docs/ARQUITETURA.md`: pipeline, contrato HTTP proposto, cache, permissões, fallbacks e custos.
- `docs/IMPLEMENTACAO.md`: etapas, critérios de aceite e prompt para o agente Linux.
- `ANDAMENTO.md`: este registro, solicitado pelo proprietário.

Até este registro, esses arquivos são documentação. Não foram criados servidor executável, projeto Android do despertador, APK ou narração de teste.

## Inspeções realizadas e resultados

### Workspace e acesso

- Diretório: `C:\Users\mf827\Documents\Ferramentas`.
- Lidos `.ai_instructions.md`, `CLAUDE.MD`, README da raiz e `.gitignore`.
- Há um projeto Android anterior em `ecosistema/android`, classificado como descontinuado. Pode servir de referência de ferramentas de build, mas não copiar sua arquitetura nem permissões: o histórico registra problemas com alterações de segurança/NFC.
- Acesso normal a `tts_platform_pt` foi negado. Uma leitura com execução elevada foi autorizada e permitiu inspecionar arquivos do motor e configuração. Novos acessos que esbarrem no sandbox devem seguir o fluxo de autorização da ferramenta.
- `git status` falhou com “not a git repository”; a listagem de `.git` também retornou acesso negado. Não concluir que o histórico foi perdido. Não houve commit nem push das alterações desta sessão.

### GPU

- Executado `nvidia-smi` em 10/11/2026, aproximadamente 18:11 no PC.
- GPU detectada: NVIDIA GeForce RTX 4070, 12.282 MiB de VRAM.
- Naquela leitura: 1.035 MiB ocupados e 2% de utilização, temperatura 44 °C.
- É apenas uma amostra. Reconsultar imediatamente antes de carregar o TTS; não presumir que continua livre.
- Nenhum modelo foi carregado por este trabalho e nenhum processo de GPU foi encerrado.

### TTS local

Lidos:

- `tts_platform_pt/server/engine/tts_engine.py`.
- `tts_platform_pt/server/config.py`.
- `tts_platform_pt/server/routes/synthesize.py`.

Constatações:

- O código está configurado para Coqui XTTS-v2: `tts_models/multilingual/multi-dataset/xtts_v2`.
- Idioma padrão: português (`pt`).
- Existe pasta `tts_platform_pt/venv`, mas o interpretador e suas dependências ainda não foram verificados por execução.
- O motor escolhe CUDA quando disponível e tenta CPU se o carregamento falhar.
- O motor completo também instancia alinhador forçado de palavras; para este teste, timestamps não são necessários. Avaliar um gerador isolado usando o XTTS existente para evitar carregar componentes extras.
- Há segmentação em frases e tratamento específico da pontuação em português no motor existente; considerar essas soluções na geração do jornal.
- A rota existente é `POST /api/synthesize`, com campos `texto`, `voice_id`, `language`, `normalizar` e `speed`.
- A normalização opcional usa outro modelo via Ollama; não é necessária para o roteiro curto já revisado deste teste. Evitar carga adicional na GPU.
- Configuração do serviço existente aponta para `127.0.0.1:8011`, mas não foi confirmado se está rodando.
- Foram encontrados vários WAVs de saídas anteriores. Eles não são o jornal deste teste.
- A configuração também tem ElevenLabs, mas este teste deve usar o modelo local.
- Ainda falta confirmar que o checkpoint XTTS está no cache, escolher voz embutida disponível e gerar uma amostra. Código configurado não prova que o modelo consegue executar.

### Ferramentas Android e áudio

- `java.exe` encontrado em `C:\Program Files\Eclipse Adoptium\jdk-21.0.7.6-hotspot\bin\java.exe`.
- `adb.exe` encontrado em `C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe`.
- `ffmpeg.exe` encontrado via WinGet.
- `python.exe` do PATH aponta para WindowsApps; verificar interpretador real antes de usá-lo.
- Existe SDK em `C:\Users\mf827\AppData\Local\Android\Sdk`, com pastas de plataformas, build-tools e platform-tools. Versões instaladas ainda precisam ser confirmadas.
- O projeto anterior usa Android Gradle Plugin 8.7.3, Kotlin 2.0.21 e wrapper Gradle 8.11.1. São referências locais, não versões já escolhidas/validadas para o novo cliente.
- Ainda não há confirmação de aparelho autorizado no ADB. Houve uma tentativa de consulta, mas a saída útil não ficou confirmada antes da interrupção; executar novamente.

### Música local

- A busca encontrou várias faixas já separadas em `karaoke/server/songs`, normalmente `vocal.mp3` e `backing_track.mp3`.
- Candidato identificado: `so-nice-summer-samba-marcos-valle`, com caminhos para vocal e instrumental encontrados na busca. Ainda não foi inspecionado/escutado nem preparado para o teste.
- Se não houver arquivo original completo, misturar vocal e instrumental correspondentes com FFmpeg em saída nova dentro de `despertador`, verificando duração e clipping. Não modificar a biblioteca de origem.
- O guia de onboarding do projeto karaoke foi aberto para respeitar as instruções locais. Nenhum código ou conteúdo do karaoke foi alterado.

### Rede

- Consulta por `Get-NetIPAddress` foi negada pelo ambiente.
- Falta confirmar IP local, porta livre, acesso do celular e se ambos estão na mesma rede.
- Não foi aberta porta no firewall, criado túnel ou alterado proxy.

### Notícias

- Foi feita busca web para notícias ligadas a novembro de 2026 e referências oficiais Android.
- Duas candidatas encontradas, ainda sem seleção editorial final nem roteiro:
  - Agência Brasil, publicada em 03/11/2026: “Semana de Educação Midiática terá atividades em todas as regiões”. URL: https://agenciabrasil.ebc.com.br/educacao/noticia/2026-11/semana-de-educacao-midiatica-tera-atividades-em-todas-regioes
  - Agência Espacial Brasileira: “Prazo para afiliação para a 2ª Feira Nacional de Ciências GLOBE Brasil segue até 4 de novembro”. URL: https://www.gov.br/aeb/pt-br/assuntos/noticias/prazo-para-afiliacao-para-a-2a-feira-nacional-de-ciencias-globe-brasil-segue-ate-4-de-novembro/
- O prazo de inscrição da segunda matéria já estaria encerrado na data do teste: não narrá-lo como convite ainda vigente. Verificar o conteúdo e a data do evento antes de usar.
- A tentativa seguinte de abrir as páginas completas foi interrompida pelo proprietário. Não tratar essas páginas como integralmente verificadas.
- Escolher matérias atuais com datas claras, ler as páginas completas e guardar atribuições/URLs junto do roteiro. Não apresentar um jornal de demonstração congelado como atualização diária automática.

## Próximos passos, em ordem

1. Confirmar ferramentas: Python do venv TTS, checkpoint no cache, versões do SDK, Gradle disponível e `adb devices`. Confirmar IP por método permitido. Evitar expor segredos nos resultados.
2. Reconsultar GPU. Se estiver ocupada, continuar trabalhando no cliente/servidor e voltar ao TTS depois; se necessário, usar CPU mediante viabilidade. Não interferir em outras tarefas.
3. Ler e escolher duas ou três notícias reais; produzir roteiro curto com data de referência e fontes em arquivo. Começar com aproximadamente um minuto para validar o fluxo rapidamente.
4. Gerar amostra XTTS local em português usando voz disponível; verificar áudio e duração. Gerar narração completa e encerrar o processo de inferência para liberar memória.
5. Preparar música existente em arquivo independente, preservando os originais. Registrar origem e título.
6. Implementar servidor de teste na pasta `despertador`, com dependências mínimas, manifesto e entrega dos arquivos. Servir apenas diretório de artefatos, sem expor o repositório ou credenciais. Escolher rede e autenticação compatíveis com o teste local; documentar qualquer uso temporário de HTTP na LAN.
7. Implementar cliente Android separado e mínimo: configurar endereço do PC, baixar arquivos para armazenamento privado, validar download completo, agendar horário ou teste em um minuto, reproduzir notícias seguidas de música, parar e cancelar alarme. Incluir toque embarcado independente da rede.
8. Pedir somente permissões necessárias ao alarme e serviço de reprodução. Usar AlarmManager para disparo e serviço de primeiro plano com notificação/ação de parar. Não usar acessibilidade, contatos, microfone, SMS, leitura de notificações, VPN ou alterações de NFC/segurança.
9. Compilar APK, verificar manifesto e disponibilizar arquivo e instruções. Instalar via ADB somente se houver aparelho conectado/autorizado; caso contrário, fornecer caminho/download do APK e passos de instalação manual.
10. Validar no PC: API, manifesto, hash/arquivos, reprodução/decodificação e build Android. Validar no Samsung: disparo com tela bloqueada e modo avião depois de baixar, sequência jornal/música, parar e fallback sem jornal. Não afirmar que teste físico passou sem executá-lo.
11. Atualizar este arquivo e o README com comandos reais para iniciar/parar o servidor, localização do APK, notícias/música utilizadas, resultados e limitações. Depois retomar implantação Linux conforme o plano original.

## Estado no momento da interrupção

O proprietário interrompeu a inspeção para solicitar este registro. As últimas chamadas de leitura/consulta podem não ter terminado; verificar antes de repetir qualquer operação que gere efeitos. Até aqui, não foi iniciado servidor, build Android ou geração TTS por este trabalho. A próxima ação prática é concluir o inventário do ambiente, preservando a GPU e os projetos existentes.
