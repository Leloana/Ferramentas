# 🧠 Base de Conhecimento — Karaoke AI Premium (`.claude/karaoke/`)

Esta pasta é a **base de conhecimento da IA assistente** para o subprojeto
`karaoke/`. Ela concentra, em um único lugar, tudo que um agente (ou desenvolvedor
novo) precisa ler antes de responder perguntas ou alterar código do karaokê:
arquitetura, contratos de dados, fluxos de rede, decisões de design e o histórico
de problemas já resolvidos.

> [!IMPORTANT]
> **Antes de qualquer modificação na pasta `karaoke/`**, leia primeiro
> [onboarding/PROJECT_GUIDE.md](onboarding/PROJECT_GUIDE.md) — é a fonte da verdade
> dos contratos de dados (`segments.json`, `meta.json`), invariantes e regras de
> código. Os demais documentos aprofundam tópicos específicos.

---

## 🗂️ Como navegar

### `onboarding/` — Entenda o sistema (leia primeiro)
Documentos vivos que descrevem **como o sistema funciona hoje**.

| Arquivo | Quando consultar |
| :--- | :--- |
| [PROJECT_GUIDE.md](onboarding/PROJECT_GUIDE.md) | **Sempre primeiro.** Estrutura de pastas, contratos de `segments.json`/`meta.json`, invariantes de dados e convenções de código (frontend e backend). |
| [ARCHITECTURE.md](onboarding/ARCHITECTURE.md) | Visão de componentes, especificações de módulos (STT, Score, Rooms), dependências externas e variáveis de ambiente. |
| [FLOW.md](onboarding/FLOW.md) | Fluxos de upload, reinstalação e edição manual de letras, com diagramas de sequência e caminhos de erro. |
| [MULTIPLAYER_FLOW.md](onboarding/MULTIPLAYER_FLOW.md) | Handshake multi-dispositivo, fila de registro de microfones, loop de jogo WebSocket, seeking e persistência de perfis. |

### `resolucoes/` — Histórico e decisões (consulta pontual)
Notas **históricas e de depuração**. Útil para entender _por que_ algo foi feito de
determinada forma e evitar reintroduzir bugs já resolvidos. Não descreve
necessariamente o estado atual do código.

| Arquivo | Conteúdo |
| :--- | :--- |
| [resolucoes/BACKEND_REFACTOR_NOTES.md](resolucoes/BACKEND_REFACTOR_NOTES.md) | Histórico da refatoração do backend (modularização de `server/`). |
| [resolucoes/LRC_ALIGNMENT_FIX.md](resolucoes/LRC_ALIGNMENT_FIX.md) | Transição do alinhamento por linha para word-level. |
| [resolucoes/LRC_ALIGNMENT_TUNING.md](resolucoes/LRC_ALIGNMENT_TUNING.md) | Playbook de ajuste de timestamps e "knobs" de alinhamento. |
| [resolucoes/PLANO.md](resolucoes/PLANO.md) | Planejamento original do MVP (deprecado). |
| [resolucoes/notes.md](resolucoes/notes.md) | Rascunho inicial: VAD, API Vagalume, casos da música _Holiday_. |
| `resolucoes/holiday-green-day/` | Áudios e JSONs de depuração usados como caso de teste de alinhamento. |

### `Executar.md` — Comandos operacionais
[Executar.md](Executar.md) reúne como ativar a `venv`, subir o servidor (HTTPS /
HTTP / túnel), descobrir o IP de rede, rodar os testes e diagnosticar erros comuns.

---

## ↔️ Relação com `docs/`

O conteúdo de `onboarding/` e `resolucoes/` espelha a documentação técnica oficial
em [`karaoke/docs/`](../../docs/) (`docs/architecture/`, `docs/guides/`,
`docs/archive/`). A cópia aqui em `.claude/` existe para que a IA assistente tenha a
documentação imediatamente disponível como contexto. **Ao atualizar um documento,
mantenha as duas cópias sincronizadas.**
