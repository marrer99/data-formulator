import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class PowerBIConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    
    @staticmethod
    def from_env() -> Optional['PowerBIConfig']:
        required_vars = ['POWERBI_TENANT_ID', 'POWERBI_CLIENT_ID', 'POWERBI_CLIENT_SECRET']
        if not all(var in os.environ for var in required_vars):
            return None
        return PowerBIConfig(
            tenant_id=os.environ['POWERBI_TENANT_ID'],
            client_id=os.environ['POWERBI_CLIENT_ID'],
            client_secret=os.environ['POWERBI_CLIENT_SECRET']
        )
