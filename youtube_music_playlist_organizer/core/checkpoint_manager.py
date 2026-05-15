import os
from .json_utils import safe_load_json, atomic_save_json

class CheckpointManager:
    CHECKPOINT_FILE = ".sync_checkpoint.json"

    @staticmethod
    def load():
        return safe_load_json(CheckpointManager.CHECKPOINT_FILE, dict)

    @staticmethod
    def save(data):
        atomic_save_json(CheckpointManager.CHECKPOINT_FILE, data)

    @staticmethod
    def add_synced_track(playlist_id, track_id):
        data = CheckpointManager.load()
        data.setdefault(playlist_id, []).append(track_id)
        CheckpointManager.save(data)

    @staticmethod
    def is_synced(playlist_id, track_id):
        data = CheckpointManager.load()
        return track_id in data.get(playlist_id, [])

    @staticmethod
    def clear():
        if os.path.exists(CheckpointManager.CHECKPOINT_FILE):
            os.remove(CheckpointManager.CHECKPOINT_FILE)
