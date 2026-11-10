# Despertador pessoal

Status (10/11/2026): **MVP de teste pronto**, com este PC Windows como servidor. Falta validar no S24 FE.

## Teste local (PC como servidor)

```powershell
# 1. Servidor (deixe a janela aberta). Mostra o endereço e o token para digitar no app.
cd despertador\server; .\.venv\Scripts\python.exe run.py

# 2. Nova edição a partir de um roteiro (narração ElevenLabs + música local)
.\.venv\Scripts\python.exe gerar_edicao.py conteudo\2026-11-10\roteiro.json --musica ..\..\karaoke\server\songs\so-nice-summer-samba-marcos-valle

# 3. APK (sai em android\dist\ depois de copiar; instalar manualmente no celular)
cd despertador\android; $env:JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-21.0.7.6-hotspot"; .\gradlew assembleDebug
```

- `server/`: FastAPI (`app.py`), gerador de edição (`gerar_edicao.py`), adaptador ElevenLabs com cache e teto (`voz.py`, modelo `eleven_v4_turbo`, voz David). Chave em `server/.env` (gitignored). Gerado fica em `server/data/` (gitignored): edições, token, `gastos.jsonl`.
- Orçamento: 10.000 créditos no total (custo real lido do cabeçalho `character-cost`; turbo v4 ≈ 0,25 crédito/caractere, ~290 créditos por edição de 1 min ⇒ ~33 edições) e 2.500 caracteres por edição (`config.py`). Narração repetida sai do cache sem gastar.
- `android/`: Kotlin sem bibliotecas externas (AlarmManager `setAlarmClock`, MediaPlayer com áudio de alarme, JobScheduler para sincronizar no Wi‑Fi a cada ~3 h). Sequência: toque embarcado com volume crescente → jornal (ou aviso embarcado se faltar/vencer) → música → toque em loop até Parar/Soneca (limite de 15 min).
- HTTP sem TLS só na rede de casa (`usesCleartextTraffic`, temporário). No servidor final: HTTPS.

Despertador para uso pessoal no Samsung S24 FE. O servidor Linux prepara um jornal em áudio; o celular sincroniza, guarda os arquivos e toca no horário, mesmo sem rede.

## Três pilares

1. **Servidor computa, celular consome.** Pesquisa, seleção, resumo e ElevenLabs rodam no Linux. Android só configura o alarme, sincroniza e reproduz arquivos locais.
2. **Mínimo de permissões no celular.** Armazenamento privado do app, sem acessibilidade, contatos, SMS, leitura de notificações, VPN ou alterações de segurança do aparelho. Permissões de alarme e reprodução devem ter finalidade explícita.
3. **Fallbacks inteligentes.** Falhar na geração ou no download nunca deve apagar o último conteúdo válido nem impedir o toque local.

## Recursos já disponíveis

- Servidor Linux com `agy` no terminal, já utilizado pelo proprietário para buscas na internet. Usar como primeira opção para pesquisa e roteiro, através de um adaptador; descobrir a interface real instalada antes de implementar comandos.
- ElevenLabs pago. Crédito suficiente depende da duração e frequência: medir consumo real, limitar gastos e reutilizar áudio já gerado.
- Samsung S24 FE. Versão de Android/One UI e comportamento de bateria precisam ser verificados no aparelho.

## Experiência proposta

O app mostra o próximo alarme, a edição baixada e seu horário de publicação, além de um botão para testar o toque. O usuário escolhe dias da semana, horário, duração do jornal e temas. No MVP: um usuário, um aparelho, um alarme recorrente, jornal em português e controles de parar/soneca.

Sequência sugerida: sinal local curto com aumento gradual de volume, jornal, música local opcional. Um limite de duração evita reprodução infinita. A política de volume, Bluetooth e Não Perturbe será validada no aparelho; não prometer contornar decisões do sistema.

YouTube Music fica para uma etapa posterior, como ação opcional visível para abrir uma playlist. O funcionamento do alarme não depende de reprodução automática por outro aplicativo.

## Decisões iniciais

| Tema | Proposta |
| --- | --- |
| App | Android nativo: Kotlin, Compose, Room e Media3 |
| Alarme | AlarmManager; sincronização oportunista com WorkManager |
| Servidor | Python, FastAPI, SQLite e arquivos no disco |
| Agendamento no Linux | systemd timer e serviço separados para geração e API |
| Pesquisa e roteiro | Adaptador para o `agy` existente, com timeout e saída validada |
| Voz | Adaptador ElevenLabs, voz configurável e orçamento por edição/mês |
| Rede | HTTPS; começar na rede doméstica, sem abrir porta pública automaticamente |
| Autenticação | Token de dispositivo revogável; chaves dos provedores só no servidor |
| Fuso inicial | America/Sao_Paulo; persistir instantes em UTC e datas editoriais no fuso |

São propostas para implementação, não dependências já instaladas. Não criar painel web, contas múltiplas ou streaming no MVP.

## O que precisa ser validado antes de uso diário

O alarme deve ser testado no aparelho físico com tela apagada, economia de bateria, modo avião, reinício e ausência de servidor. Forçar parada, desligar o aparelho ou revogar permissões são situações que impedem garantias de funcionamento; o app deve mostrar o estado de prontidão quando aberto.

A sincronização em segundo plano não tem horário garantido. Por isso, o celular já deve ter um toque embarcado e uma edição válida antes da madrugada. O servidor pode desligar após o download, mas precisa estar disponível durante alguma janela de sincronização.

Não existe jornal com notícias futuras: uma edição para amanhã descreve fatos disponíveis no horário de geração. Conteúdo velho deve ser identificado; por padrão, jornal vencido é substituído por aviso local e toque/música, sem leitura silenciosa de notícias antigas como se fossem atuais.

Leia [a arquitetura e os fallbacks](docs/ARQUITETURA.md) e [o plano para o agente Linux](docs/IMPLEMENTACAO.md).
