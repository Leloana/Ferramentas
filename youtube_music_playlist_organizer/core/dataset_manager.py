import time
from .json_utils import safe_load_json, atomic_save_json

class DatasetManager:
    DATASET_FILE = "learning_dataset.json"

    @staticmethod
    def load_dataset():
        return safe_load_json(DatasetManager.DATASET_FILE, lambda: {"playlists": {}, "drafts": {}})

    @staticmethod
    def save_dataset(data):
        atomic_save_json(DatasetManager.DATASET_FILE, data)

    @staticmethod
    def init_execution(strategy):
        data = DatasetManager.load_dataset()
        session_id = f"session_{int(time.time())}"
        data.setdefault("drafts", {})[session_id] = {
            "strategy": strategy,
            "tracks": []
        }
        DatasetManager.save_dataset(data)
        return session_id

    @staticmethod
    def update_execution(session_id, track_title, artist, target_playlist, metadata):
        data = DatasetManager.load_dataset()
        if session_id in data.get("drafts", {}):
            data["drafts"][session_id]["tracks"].append({
                "playlist": target_playlist,
                "title": track_title,
                "artist": artist,
                "genero_base": metadata.get("genero_base", ""),
                "vibe": metadata.get("vibe", "")
            })
            DatasetManager.save_dataset(data)

    @staticmethod
    def commit_execution(session_id):
        data = DatasetManager.load_dataset()
        draft = data.get("drafts", {}).pop(session_id, None)
        if not draft: return
        
        strategy = draft["strategy"]
        grouped = {}
        for t in draft["tracks"]:
            grouped.setdefault(t["playlist"], []).append(t)
            
        for pl_name, tracks in grouped.items():
            if pl_name not in data.setdefault("playlists", {}):
                data["playlists"][pl_name] = {"rating": None, "strategy_used": strategy, "tracks_summary": []}
            
            existing_titles = {tk["title"] for tk in data["playlists"][pl_name]["tracks_summary"]}
            for t in tracks:
                if t['title'] not in existing_titles:
                    data["playlists"][pl_name]["tracks_summary"].append(t)
                    
        DatasetManager.save_dataset(data)
        
    @staticmethod
    def get_top_examples(min_rating=8, max_examples=3, strategy=None):
        data = DatasetManager.load_dataset()
        good_ones = []
        for pl_name, info in data.get("playlists", {}).items():
            if info.get("rating") is not None and info["rating"] >= min_rating:
                if strategy and info.get("strategy_used") != strategy:
                    continue
                amostra = [t["title"] for t in info.get("tracks_summary", [])[:5]]
                good_ones.append({
                    "playlist_name": pl_name,
                    "strategy": info.get("strategy_used"),
                    "rating": info["rating"],
                    "example_tracks": amostra
                })
                
        good_ones = sorted(good_ones, key=lambda x: x["rating"], reverse=True)
        return good_ones[:max_examples]
