import sys
import os
from docx2pdf import convert
import argparse

def main():
    parser = argparse.ArgumentParser(description="Converte arquivos DOCX para PDF.")
    parser.add_argument("input", help="Caminho para o arquivo .docx ou diretório contendo arquivos .docx")
    parser.add_argument("-o", "--output", help="Caminho para o arquivo de saída ou diretório de saída", default=None)

    args = parser.parse_args()

    input_path = args.input
    output_path = args.output

    if not os.path.exists(input_path):
        print(f"Erro: O caminho '{input_path}' não existe.")
        sys.exit(1)

    try:
        print(f"Iniciando conversão de: {input_path}")
        if os.path.isdir(input_path):
            # Converte todos os arquivos docx na pasta
            convert(input_path, output_path)
            print(f"Sucesso! Todos os arquivos em '{input_path}' foram convertidos.")
        else:
            # Converte um único arquivo
            if not input_path.lower().endswith(".docx"):
                print("Erro: O arquivo de entrada deve ser um .docx")
                sys.exit(1)
            
            convert(input_path, output_path)
            print(f"Sucesso! Arquivo convertido.")
            
    except Exception as e:
        print(f"Ocorreu um erro durante a conversão: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
