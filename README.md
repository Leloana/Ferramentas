# Ferramentas Utilitárias

Este repositório agrupa scripts, automações e ferramentas diversas criadas para facilitar o dia a dia, organizar fluxos de trabalho e resolver problemas específicos de forma automatizada.

## 🛠️ Ferramentas Disponíveis

| Ferramenta | Descrição |
| --- | --- |
| [**YouTube Music Playlist Organizer**](./youtube_music_playlist_organizer) | Um script de linha de comando em Python que lê uma playlist do YouTube Music, classifica as músicas por gênero utilizando Inteligência Artificial (Ollama local, sem custo de API) e organiza automaticamente as faixas em playlists separadas por gênero na sua conta do YouTube. |
| [**DOCX to PDF Converter**](./docx_to_pdf_converter) | Utilitário em Python para conversão em lote (ou individual) de documentos do Microsoft Word (`.docx`) para o formato PDF, ideal para fluxos de exportação de documentos. |

## 🚀 Como Usar

Cada projeto dentro deste repositório é independente. Para utilizar qualquer um deles:
1. Navegue até a pasta da ferramenta desejada.
2. Leia o arquivo `README.md` presente dentro da respectiva pasta.
3. Siga as instruções específicas de instalação de dependências e configuração.

## ⚠️ Atenção com Credenciais
Atenção especial para scripts que utilizam APIs de terceiros (como o YouTube Data API). Arquivos de credenciais (`.env`, `oauth.json`, `token.json`) **nunca devem ser commitados**. Eles já estão cobertos no `.gitignore` da raiz deste repositório para evitar vazamentos acidentais de chaves.
