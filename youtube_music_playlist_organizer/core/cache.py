import os
from .json_utils import safe_load_json, atomic_save_json

class CacheManager:
    CACHE_FILE = ".tracks_cache.json"

    @staticmethod
    def load_cache():
        return safe_load_json(CacheManager.CACHE_FILE, dict)

    @staticmethod
    def save_cache(data):
        atomic_save_json(CacheManager.CACHE_FILE, data)

    @staticmethod
    def get_key(track_id, strategy, model):
        return f"{track_id}_{strategy}_{model}"

    @staticmethod
    def add_to_cache(cache_data, track_id, strategy, model, metadata):
        key = CacheManager.get_key(track_id, strategy, model)
        cache_data[key] = {
            "model": model,
            "metadata": metadata
        }
        
    @staticmethod
    def get_from_cache(cache_data, track_id, strategy, model):
        key = CacheManager.get_key(track_id, strategy, model)
        entry = cache_data.get(key)
        if entry and entry.get("model") == model:
            return entry.get("metadata")
        return None
