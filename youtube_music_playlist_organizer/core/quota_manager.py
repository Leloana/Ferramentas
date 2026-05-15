import os
from datetime import datetime
from .json_utils import safe_load_json, atomic_save_json

class QuotaManager:
    QUOTA_FILE = "quota_usage.json"

    @staticmethod
    def _load_data():
        return safe_load_json(QuotaManager.QUOTA_FILE, lambda: {"total_ever": 0, "daily_usage": 0, "last_date": ""})

    @staticmethod
    def _save_data(data):
        atomic_save_json(QuotaManager.QUOTA_FILE, data)

    @staticmethod
    def add_usage(units):
        data = QuotaManager._load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Reset diário automático
        if data["last_date"] != today:
            data["daily_usage"] = 0
            data["last_date"] = today
            
        data["daily_usage"] += units
        data["total_ever"] += units
        QuotaManager._save_data(data)

    @staticmethod
    def get_current_usage():
        data = QuotaManager._load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Se mudou o dia, o uso diário para o relatório deve ser 0
        if data["last_date"] != today:
            return 0, data["total_ever"]
            
        return data["daily_usage"], data["total_ever"]
