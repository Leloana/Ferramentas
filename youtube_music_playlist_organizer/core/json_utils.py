import os
import json
import tempfile
import shutil
from datetime import datetime

def safe_load_json(filepath, default_factory=dict):
    if not os.path.exists(filepath):
        return default_factory()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        backup = f"{filepath}.corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(filepath, backup)
        print(f"⚠️ Aviso: {filepath} corrompido. Backup salvo em {backup}.")
        return default_factory()
    except PermissionError as e:
        raise PermissionError(f"Acesso negado ao arquivo {filepath}. Verifique as permissões.") from e
    except Exception:
        raise

def atomic_save_json(filepath, data):
    dir_name = os.path.dirname(os.path.abspath(filepath)) or '.'
    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
