import ollama
import json
import logging
from rich.console import Console

class MusicClassifier:
    def __init__(self, model="gemma4:e4b"):
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
                    "vibe": "Energia ou clima da música",
                    "is_music": true/false
                }}
            ]
        }}
        """
        
        try:
            response = ollama.generate(model=self.model, prompt=prompt, format="json")
            data = json.loads(response['response'])
            
            resultados = {}
            for res in data.get('resultados', []):
                if not res.get('is_music', True):
                    resultados[res['id']] = "não-musical"
                else:
                    resultados[res['id']] = res
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
            return {t['id']: {"genero_base": "Outros", "sub_genero": "Geral", "vibe": "Desconhecida", "is_music": True} for t in tracks_batch}
        except Exception as e:
            self.logger.error(f"Erro na análise em lote: {e}")
            return {t['id']: {"genero_base": "Outros", "sub_genero": "Geral", "vibe": "Desconhecida", "is_music": True} for t in tracks_batch}

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

        limit_instruction = ""
        if max_playlists:
            limit_instruction = f"5. LIMITE ESTRITO DE PLAYLISTS: O usuário exigiu um limite máximo de {max_playlists} playlists/grupos a serem criados. Você DEVE fazer merges abrangentes de gêneros para garantir que o 'plano' final não exceda {max_playlists} itens. Dê um nome abstrato inovador para os resultados que misturam a essência desses gêneros.\n"

        prompt = f"""
        Você é um curador de elite. Tenho a seguinte distribuição de músicas novas:
        {json.dumps(summary, indent=2)}

        Minhas playlists ATUAIS são: {existing_names}
        {learning_context}
        Sua tarefa: Criar um plano de organização coeso.
        REGRAS CRÍTICAS:
        1. NÃO invente grupos. Crie apenas o necessário para cobrir os estilos acima.
        2. Se um grupo de músicas novas combina perfeitamente com uma playlist ATUAL, sugira o MERGE (is_merge: true). ATENÇÃO: Nesses casos, o 'target_playlist' DEVE OBRIGATORIAMENTE ser o NOME EXATO da playlist atual. NUNCA invente ou altere o nome se is_merge for true.
        3. Para playlists NOVAS (is_merge: false), o nome ('target_playlist' e 'nome_grupo') DEVE ser um nome altamente abstrato, refletindo emoções ou sensações da música, e OBRIGATORIAMENTE iniciar com um EMOJI. O nome deve ser CURTO: máximo de 2 PALAVRAS (sem contar emoji/conectivos). Ex: '😔 Desolação Total'. NUNCA use o nome literal do gênero.
        {limit_instruction}
        
        Responda APENAS um JSON no formato:
        {{
            "plano": [
                {{
                    "nome_grupo": "Nome abstrato curto com emoji (ex: 🥀 Ecos Melancólicos)",
                    "target_playlist": "Nome abstrato curto com emoji (ex: 😔 Desolação Total)",
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
