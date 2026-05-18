# Escopo do Produto: Plataforma RAG Multi-domínio com LLM

[cite_start]Este documento define as fronteiras do projeto, detalhando as entregas que fazem parte da construção da plataforma, bem como o que está explicitamente excluído do escopo atual[cite: 4, 21].

## O que está incluído (Dentro do Escopo)

* [cite_start]Pipeline de ingestão e chunking de documentos (suportando os formatos PDF, DOCX, TXT e MD)[cite: 22].
* [cite_start]Indexação vetorial com embeddings que podem ser configurados por domínio[cite: 22].
* [cite_start]API REST de consulta RAG com suporte a múltiplos domínios de forma isolada[cite: 22].
* [cite_start]Implementação dos casos de uso iniciais: WhatsApp, livros técnicos e manuais de risco de TI[cite: 22].
* [cite_start]Criação de uma interface de administração para as bases de conhecimento[cite: 22].
* [cite_start]Suporte para execução de LLMs locais (utilizando Ollama) e LLMs em nuvem (via API externa)[cite: 22].
* [cite_start]Elaboração de documentação técnica e guia de operação[cite: 22].

## O que NÃO está incluído (Fora do Escopo)

* [cite_start]Treinamento ou *fine-tuning* dos modelos LLM[cite: 22].
* [cite_start]Desenvolvimento de interfaces de usuário final (como aplicativos ou frontend)[cite: 22].
* [cite_start]Integração nativa com o WhatsApp Business API[cite: 22].
* [cite_start]Gestão e manutenção da infraestrutura de servidores no ambiente de produção[cite: 22].
* [cite_start]Suporte multilíngue para idiomas além do português[cite: 22].
* [cite_start]Treinamento direcionado aos usuários finais das respectivas áreas de domínio[cite: 22].