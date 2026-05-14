# Conversor DOCX para PDF

Esta ferramenta permite converter arquivos do Microsoft Word (.docx) para PDF de forma simples usando Python.

## Pré-requisitos

1. **Microsoft Word instalado**: Esta ferramenta utiliza a API do Word no Windows para garantir a melhor fidelidade na conversão.
2. **Python 3.x** instalado.

## Instalação

Abra o terminal na pasta `docx_to_pdf_converter` e instale a dependência necessária:

```bash
pip install -r requirements.txt
```

## Como Usar

### Converter um único arquivo
```bash
python converter.py "caminho/para/documento.docx"
```

### Converter todos os arquivos de uma pasta
```bash
python converter.py "caminho/para/pasta_com_docx"
```

### Especificar saída personalizada
```bash
python converter.py "documento.docx" -o "saida.pdf"
```

---
*Desenvolvido com Antigravity*
