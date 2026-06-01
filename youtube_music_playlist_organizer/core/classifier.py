import ollama
import json
import logging
from rich.console import Console

class MusicClassifier:
    def __init__(self, model="gemma3n:e4b"):
        self.model = model
        self.logger = logging.getLogger("YTOrganizer")
        self.console = Console()

    def batch_deep_classify(self, tracks_batch, strategy="genre", retry_on_fail=True):
        """Análise em lote de músicas com foco na estratégia selecionada"""
        foco = ""
        if strategy == "genre":
            foco = "Foque primariamente no gênero musical, estilo e ritmo."
        elif strategy == "vibe":
            foco = "Ignore o gênero e foque puramente na vibração, humor e emoção que a música passa."
        elif strategy == "time":
            foco = "Foque no momento do dia ou ocasião ideal para ouvir essa música (ex: Academia, Relaxar, Trabalho, Festa)."
        elif strategy == "season":
            foco = "Foque no clima e estética (ex: Chuvoso, Praia, Verão, Frio)."
            
        lista_str = "\n".join([f"ID {t['id']}: \"{t['title']}\" - Artista: \"{t['artist']}\"" for t in tracks_batch])
        
        prompt = f"""
        Analise a seguinte lista de músicas.
        ESTRATÉGIA DE CLASSIFICAÇÃO ATIVA: {foco}
        
        Lista:
        {lista_str}
        
        Responda APENAS um JSON no formato:
        {{
            "resultados": [
                {{
                    "id": "O mesmo ID da música recebido na lista",
                    "genero_base": "Categoria principal baseada na estratégia acima",
                    "sub_genero": "Sub-categoria ou detalhe extra",
                    "vibe": "Energia ou clima da música"
                }}
            ]
        }}
        """

        try:
            response = ollama.generate(model=self.model, prompt=prompt, format="json")
            data = json.loads(response['response'])

            resultados = {}
            for res in data.get('resultados', []):
                rid = res.get('id')
                if rid is None:
                    continue
                resultados[str(rid)] = {
                    'genero_base': res.get('genero_base', 'Outros'),
                    'sub_genero': res.get('sub_genero', 'Geral'),
                    'vibe': res.get('vibe', 'Desconhecida'),
                }
            return resultados
        except json.JSONDecodeError as e:
            if retry_on_fail and len(tracks_batch) > 1:
                self.logger.warning("Falha de parse no JSON. Reduzindo lote pela metade e retentando recursivamente...")
                mid = len(tracks_batch) // 2
                res1 = self.batch_deep_classify(tracks_batch[:mid], strategy, retry_on_fail=False)
                res2 = self.batch_deep_classify(tracks_batch[mid:], strategy, retry_on_fail=False)
                res1.update(res2)
                return res1
            self.logger.error(f"Erro crítico no parse. Salvando fallback: {e}")
            return {t['id']: {"genero_base": "Outros", "sub_genero": "Geral", "vibe": "Desconhecida"} for t in tracks_batch}
        except Exception as e:
            self.logger.error(f"Erro na análise em lote: {e}")
            return {t['id']: {"genero_base": "Outros", "sub_genero": "Geral", "vibe": "Desconhecida"} for t in tracks_batch}

    def generate_global_strategy(self, track_metadata_list, existing_playlists, current_strategy="genre", max_playlists=None):
        """Analisa o panorama de todas as músicas e decide a estrutura de playlists, considerando as já existentes"""
        summary = {}
        for m in track_metadata_list:
            if m == "não-musical": continue
            key = f"{m['genero_base']} ({m['sub_genero']}) - {m['vibe']}"
            summary[key] = summary.get(key, 0) + 1
            
        self.logger.info(f"Gerando panorama global considerando {len(existing_playlists)} playlists existentes.")
        
        # Limpar nomes de playlists do usuário para a IA
        existing_names = list(existing_playlists.keys())
        
        from core.dataset_manager import DatasetManager
        examples = DatasetManager.get_top_examples(min_rating=8, max_examples=3, strategy=current_strategy)
        
        learning_context = ""
        if examples:
            learning_context = "\n[CONTEXTO DE APRENDIZADO] O usuário AVALIOU COMO EXCELENTE as seguintes playlists no passado. USE COMO INSPIRAÇÃO PARA AGRUPAMENTO E NOMENCLATURA:\n"
            for ex in examples:
                learning_context += f"- NOME: {ex['playlist_name']} | EXEMPLOS DE FAIXAS: {', '.join(ex['example_tracks'])}\n"

        # Nomenclatura: sempre nomes abstratos com emoji (em qualquer estratégia).
        naming_rule = ("3. Para playlists NOVAS (is_merge: false), o nome ('target_playlist' e 'nome_grupo') DEVE ser "
                       "altamente abstrato, refletindo emoções/sensações da música, OBRIGATORIAMENTE iniciar com um "
                       "EMOJI e ter no máximo 2 PALAVRAS (sem contar emoji/conectivos). Ex: '😔 Desolação Total'. "
                       "NUNCA use o nome literal do gênero.")
        exemplo_nome = "😔 Desolação Total"

        limit_instruction = ""
        if max_playlists:
            limit_instruction = f"5. LIMITE ESTRITO DE PLAYLISTS: O usuário exigiu um limite máximo de {max_playlists} playlists/grupos. Você DEVE fazer merges abrangentes para que o 'plano' final não exceda {max_playlists} itens, mantendo o estilo de nome definido na regra 3.\n"

        prompt = f"""
        Você é um curador de elite. Tenho a seguinte distribuição de músicas novas:
        {json.dumps(summary, indent=2)}

        Minhas playlists ATUAIS são: {existing_names}
        {learning_context}
        Sua tarefa: Criar um plano de organização coeso.
        REGRAS CRÍTICAS:
        1. NÃO invente grupos. Crie apenas o necessário para cobrir os estilos acima.
        2. Se um grupo de músicas novas combina perfeitamente com uma playlist ATUAL, sugira o MERGE (is_merge: true). ATENÇÃO: Nesses casos, o 'target_playlist' DEVE OBRIGATORIAMENTE ser o NOME EXATO da playlist atual. NUNCA invente ou altere o nome se is_merge for true.
        {naming_rule}
        {limit_instruction}

        Responda APENAS um JSON no formato:
        {{
            "plano": [
                {{
                    "nome_grupo": "Nome conforme a regra 3 (ex: {exemplo_nome})",
                    "target_playlist": "Mesmo nome do grupo, ou o nome EXATO da playlist atual se for merge",
                    "is_merge": true/false,
                    "criterios": ["sub_generos ou vibes que entram aqui"]
                }}
            ]
        }}
        """
        
        try:
            response = ollama.generate(model=self.model, prompt=prompt, format="json")
            strategy = json.loads(response['response'])
            plano = strategy.get('plano', [])
            self.logger.info(f"Plano Global gerado com {len(plano)} grupos.")
            return plano
        except Exception as e:
            self.logger.error(f"Erro ao gerar panorama global: {e}")
            return []

    def assign_to_groups(self, tracks, plano, strategy="genre", batch_size=20, progress_cb=None):
        """Pede à IA para colocar CADA faixa em um dos grupos do plano.

        Substitui o antigo match por substring: aqui o modelo vê o título real,
        os metadados e os grupos candidatos, e devolve o grupo de cada faixa.
        Retorna dict track_id -> nome_grupo (somente grupos válidos do plano).
        Faixas que o modelo não atribuir ficam de fora e o chamador decide o
        fallback (sem despejo silencioso num grupo arbitrário)."""
        valid_groups = [p['nome_grupo'] for p in plano]
        grupos_str = "\n".join(
            f"- {p['nome_grupo']}: {', '.join(p.get('criterios', []))}" for p in plano
        )

        assignments = {}
        for i in range(0, len(tracks), batch_size):
            batch = tracks[i:i + batch_size]
            linhas = []
            for t in batch:
                m = t.get('metadata', {}) or {}
                linhas.append(
                    f'ID {t["id"]}: "{t["title"]}" — {t["artist"]} '
                    f'[base={m.get("genero_base", "")}, sub={m.get("sub_genero", "")}, vibe={m.get("vibe", "")}]'
                )
            lista_str = "\n".join(linhas)

            prompt = f"""
            Você é um curador musical. Distribua cada música em UM dos grupos abaixo.
            Escolha sempre o grupo mais coerente com o estilo/vibe da faixa.
            Use SOMENTE os nomes exatos da lista; NÃO invente grupos novos.

            GRUPOS DISPONÍVEIS:
            {grupos_str}

            MÚSICAS:
            {lista_str}

            Responda APENAS um JSON no formato:
            {{
                "resultados": [
                    {{ "id": "o mesmo ID recebido", "grupo": "nome EXATO de um grupo acima" }}
                ]
            }}
            """

            try:
                response = ollama.generate(model=self.model, prompt=prompt, format="json")
                data = json.loads(response['response'])
                for res in data.get('resultados', []):
                    rid = res.get('id')
                    grupo = res.get('grupo')
                    if rid is not None and grupo in valid_groups:
                        assignments[str(rid)] = grupo
            except Exception as e:
                self.logger.error(f"Erro na atribuição faixa→grupo (lote {i}): {e}")

            if progress_cb:
                progress_cb(len(batch))

        self.logger.info(f"Atribuição via IA: {len(assignments)}/{len(tracks)} faixas mapeadas diretamente.")
        return assignments
