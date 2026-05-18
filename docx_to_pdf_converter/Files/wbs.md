# WBS: Plataforma RAG Multi-domínio com LLM

[cite_start]Este documento detalha a Estrutura Analítica do Projeto (WBS) para o desenvolvimento da plataforma de Retrieval-Augmented Generation (RAG)[cite: 13]. A estrutura foi adaptada para mapear os entregáveis técnicos do projeto aos nós padronizados do sistema.

## 1.0 Definição de Parâmetros
Fase focada no levantamento de requisitos operacionais e mapeamento de domínios.

* [cite_start]**1.1 Informações Mapeadas:** Levantamento das bases documentais e de conhecimento das áreas envolvidas para indexação[cite: 25]. [cite_start]Definição dos casos de uso iniciais, que incluem atendimento via WhatsApp, livros técnicos e manuais de risco de TI[cite: 22]. [cite_start]Estabelecimento de critérios de curadoria junto às áreas de negócio para evitar a ingestão de documentos com qualidade insuficiente[cite: 35].
* [cite_start]**1.2 Interfaces Definidas:** Especificação da API REST de consulta RAG, garantindo que ela tenha suporte a múltiplos domínios isolados[cite: 22]. [cite_start]Definição da arquitetura baseada em pipeline modular e da interface de administração das bases de conhecimento[cite: 22, 54].

## 2.0 Preparação dos Ambientes
Fase destinada à aquisição, configuração e provisionamento da infraestrutura física e lógica.

* [cite_start]**2.1 Fornecedor Selecionado:** Seleção e aprovação de licenças de uso dos modelos LLM, sejam eles em nuvem ou locais (como Ollama suportando Qwen2.5-Coder, DeepSeek-R1 ou Llama 3.1)[cite: 22, 27, 51].
* [cite_start]**2.2 Hardware Recebido:** Provisionamento de servidor com GPU dedicada de no mínimo 8 GB de VRAM (recomendado NVIDIA 4070/12 GB VRAM) para rodar modelos locais[cite: 24, 58]. [cite_start]Garantia de 32 GB de RAM para processamento em batch e armazenamento SSD mínimo de 500 GB para as bases vetoriais[cite: 58].
* [cite_start]**2.3 Pagamento Efetuado:** Alocação e controle do orçamento aprovado, que está limitado a R$ 180.000,00[cite: 31].
* [cite_start]**2.4 Estações de Trabalho Instaladas:** Configuração do ambiente conteinerizado via Docker para as fases de desenvolvimento e produção[cite: 58]. [cite_start]Configuração de uma rede isolada para garantir a conformidade e a segurança no tráfego de dados sensíveis[cite: 58].

## 3.0 Conversão de Dados
*Nota: No contexto de IA/RAG, esta etapa abrange os pipelines de ingestão, chunking e indexação vetorial.*

* [cite_start]**3.1 Layout Estabelecido:** Configuração do banco vetorial (ChromaDB para desenvolvimento e Qdrant para produção)[cite: 50]. [cite_start]Configuração da arquitetura onde cada domínio possuirá sua própria *collection* isolada[cite: 55].
* [cite_start]**3.2 Arquivos Preparados:** Construção do pipeline de ingestão e *chunking* de documentos em formatos como PDF, DOCX, TXT e MD[cite: 22].
* [cite_start]**3.3 Arquivos Importados:** Execução do processo de *embedding* (utilizando all-MiniLM-L6-v2 ou modelos multilingues) e indexação vetorial configurável por domínio[cite: 22, 53, 54].
* [cite_start]**3.4 Testes Isolados:** Realização de benchmark de modelos e ajustes técnicos de quantização (4-bit/8-bit) para mitigar a latência na inferência local[cite: 37].
* [cite_start]**3.5 Testes Integrados:** Testes completos de orquestração RAG (LangChain ou LlamaIndex) unindo recuperação e geração[cite: 49, 55]. [cite_start]Validação para garantir que a arquitetura seja compatível tanto com ambientes Windows quanto Linux[cite: 33].

## 4.0 Capacitação
[cite_start]*Nota: O treinamento de usuários finais das áreas de domínio não é escopo deste projeto[cite: 22]. O foco aqui é a equipe técnica e os curadores.*

* [cite_start]**4.1 Material Didático Preparado:** Elaboração da documentação técnica e do guia de operação da plataforma[cite: 22].
* **4.2 Usuários Treinados:** Capacitação dos perfis-chave para a gestão da plataforma.
    * [cite_start]**4.2.1 Treinamento Turma 1 Realizado:** Alinhamento e treinamento dos "Curadores de Domínio" (Áreas de negócio) sobre o processo de curadoria e validação das bases de conhecimento[cite: 28, 65].
    * [cite_start]**4.2.2 Treinamento Turma 2 Realizado:** Treinamento da equipe de TI e "Usuários-chave" para validação de resultados e testes de aceitação das respostas geradas[cite: 65].

## 5.0 Go Live
Fase de implantação, ajustes finais de qualidade e entrega da primeira versão.

* [cite_start]**5.1 Manuais de Operação Desenvolvidos:** Finalização e entrega do guia operacional da API e da interface administrativa[cite: 22].
* [cite_start]**5.2 Acompanhamento do Usuário Realizado:** Monitoramento inicial focado nos usuários-chave durante os testes de aceitação e na validação dos resultados em contextos reais[cite: 65].
* [cite_start]**5.3 Ajustes Realizados:** Configuração refinada do *threshold* de relevância e mecanismos de controle de resposta para mitigar riscos de "alucinação" do LLM em contextos incompletos[cite: 35].
* [cite_start]**5.4 Sistemas Conferidos:** Verificação formal de que nenhum dado sensível está sendo enviado para APIs externas sem a devida aprovação formal da área de segurança[cite: 30].
* [cite_start]**5.5 Testes Finais Concluídos:** Homologação e entrega oficial da versão 1.0, respeitando o prazo máximo de 12 meses estipulado no TAP[cite: 32].

## 6.0 Conclusão
* [cite_start]**6.1 Suporte Pós-implementação:** Transição para o suporte da operação técnica, assegurando que a expansão para novos domínios possa ocorrer sem alteração da infraestrutura central (*core*)[cite: 56]. [cite_start]*Nota: A gestão da infraestrutura de servidores em produção não faz parte do escopo deste projeto[cite: 22].*
* [cite_start]**6.2 Avaliação Final:** Encerramento do projeto com verificação do retorno sobre investimento, redução de retrabalho e entrega dos objetivos de modernização e eficiência via inteligência artificial[cite: 10, 15, 18].