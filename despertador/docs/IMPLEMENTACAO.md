# Plano de implementação e passagem para o Linux

## Etapa 0 — levantar o ambiente

Ler o README e a arquitetura. Inspecionar distribuição Linux, Python, Java/Android SDK, FFmpeg, systemd, portas e serviços existentes. Descobrir a interface real do `agy` com ajuda e uma busca de teste pequena; registrar formato, timeout, autenticação existente e limites. Não imprimir tokens nem copiar credenciais de outros projetos.

Verificar no celular versão de Android/One UI, método de instalação do APK e configurações de alarmes. Defaults editoriais provisórios: português, America/Sao_Paulo, 3–5 minutos, uma edição diária. Horário, temas, fontes, voz ElevenLabs e orçamento são configurações pendentes, não decisões já aprovadas.

## Etapa 1 — provar o despertador offline

Criar app Kotlin com alarme único recorrente, toque embarcado, parar, soneca, persistência e estado de prontidão. Começar com áudio de teste local; nenhuma integração com IA necessária.

Aceite no S24 FE: disparo com app fora da tela, tela bloqueada, modo avião e bateria em economia; testar reinício, revogação de permissão, troca de horário/fuso, soneca e disparos repetidos. Registrar horário esperado/real, versão do sistema, saída de áudio e resultado. Testar Bluetooth e Não Perturbe. Distinguir encerramento normal de “forçar parada”. Resolver ou declarar limites de Direct Boot.

## Etapa 2 — servir e baixar edição fixa

Criar API Python com uma edição de demonstração, token, manifesto validado e assets imutáveis. Criar `.venv` para dependências Python; fixar versões no momento da implementação. Android sincroniza para cache privado e toca sem servidor.

Aceite: autenticação, versão inválida, download interrompido, conteúdo corrompido, disco cheio, edição vencida e servidor desligado. Promoção atômica mantém última edição válida. Toque de reserva não depende de download.

## Etapa 3 — gerar jornal com agy e ElevenLabs

Implementar adaptadores separados de pesquisa/roteiro e voz. Começar com fixtures e modo simulado; depois uma chamada real pequena para medir qualidade e créditos. Não inventar flags do `agy` nem fixar voz/modelo/preço sem verificar as interfaces instaladas e documentação vigente.

Aceite: fontes rastreáveis, fatos sem suporte omitidos, timeout do agente, ausência de notícias, indisponibilidade do TTS, orçamento esgotado, execução duplicada e reinício no meio da geração. Nenhum desses casos pode substituir a edição válida por arquivos incompletos.

## Etapa 4 — operação no Linux

Entregar unidades systemd de API e geração, usuário sem privilégios, diretórios persistentes, arquivo de configuração de exemplo sem segredos e instruções de instalação/remoção. Timer com fuso explícito e recuperação de execução perdida; lock para evitar concorrência. Confirmar rede/HTTPS existente antes de escolher proxy ou exposição externa.

O agente deve implementar e testar antes de habilitar serviços persistentes, documentando os comandos e as alterações necessárias no host. Não sobrescrever proxy, firewall ou serviços existentes. Não efetuar compras, contratar provedores ou mudar plano ElevenLabs.

Aceite: reboot do Linux, geração manual, timer, logs sem chaves, saúde da API e teste completo no celular após download. Só considerar pronto para uso diário depois da validação física do alarme.

## Etapas futuras

Música própria, preferências sincronizadas, boletins adicionais e botão para abrir YouTube Music. Múltiplos usuários, streaming, painel web e automação de tela ficam fora do escopo inicial.

## Prompt para o agente no servidor

> Trabalhe na pasta `despertador` deste repositório. Leia `README.md`, `docs/ARQUITETURA.md` e este plano. Preserve os três pilares: servidor computa/celular consome, mínimo de permissões e fallbacks inteligentes. Primeiro inspecione o ambiente e o CLI `agy` existente sem revelar credenciais. Implemente em etapas verificáveis: alarme Android offline; API e cache com edição fixa; pesquisa via agy e voz ElevenLabs com teto de gasto; operação Linux. Avance no que puder testar localmente, registrando validações físicas pendentes no Samsung S24 FE. Não marque esses testes como concluídos sem o aparelho. Não altere segurança/NFC do celular, não exponha portas nem substitua serviços existentes sem necessidade e autorização. Mantenha documentação, comandos reproduzíveis e limitações reais atualizados.
