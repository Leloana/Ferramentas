from __future__ import annotations
import requests
import yaml
from pathlib import Path

# Carrega a configuração global
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

def unload_ollama_models(except_model: str | None = None):
    """
    Descarrega todos os modelos da memória do Ollama, exceto o especificado em except_model.
    Se except_model for None, descarrega todos.
    """
    base_url = CONFIG.get("ollama", {}).get("base_url", "http://localhost:11434")
    try:
        # Consulta os modelos atualmente carregados no Ollama
        ps_resp = requests.get(f"{base_url}/api/ps", timeout=5)
        if ps_resp.status_code != 200:
            return
        
        models_data = ps_resp.json().get("models", [])
        if not models_data:
            return
            
        # Normaliza o nome do modelo que deve permanecer na memória
        target_model = except_model
        if target_model and target_model.startswith("ollama:"):
            target_model = target_model[len("ollama:"):]
            
        for m in models_data:
            m_name = m.get("name", "")
            m_model = m.get("model", "")
            
            # Se bater com o target_model, ignoramos (mantemos carregado)
            is_target = False
            if target_model:
                clean_target = target_model.replace(":latest", "")
                clean_name = m_name.replace(":latest", "")
                clean_model = m_model.replace(":latest", "")
                if clean_name == clean_target or clean_model == clean_target:
                    is_target = True
                    
            if is_target:
                continue
                
            print(f"  [ollama] Descarregando modelo inativo para liberar GPU: {m_name}...")
            # Envia requisição com keep_alive: 0 para descarregar o modelo
            requests.post(f"{base_url}/api/chat", json={"model": m_name, "keep_alive": 0}, timeout=5)
            
    except Exception as e:
        print(f"  [ollama] Aviso: erro ao descarregar modelos: {e}")
