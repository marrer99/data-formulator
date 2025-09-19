from functools import wraps
from flask import request, jsonify
from azure.identity import ClientSecretCredential
from data_formulator.powerbi_config import PowerBIConfig

class PowerBIAuth:
    def __init__(self, config: PowerBIConfig):
        self.config = config
        self.credential = ClientSecretCredential(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            client_secret=config.client_secret
        )

    def require_auth(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                token = self.credential.get_token("https://analysis.windows.net/powerbi/api/.default")
                if not token:
                    return jsonify({"error": "Failed to authenticate with Power BI"}), 401
                request.powerbi_token = token.token
                return f(*args, **kwargs)
            except Exception as e:
                return jsonify({"error": f"Authentication failed: {str(e)}"}), 401
        return decorated
