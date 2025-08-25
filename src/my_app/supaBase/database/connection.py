
from supabase import create_client, Client
from typing import Optional
from ..config.settings import Config

class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'client'):
            self.client: Client = create_client(
                Config.SUPABASE_URL,
                Config.SUPABASE_KEY
            )
    
    def get_client(self) -> Client:
        return self.client
