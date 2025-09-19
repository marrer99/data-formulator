import json
import pandas as pd
import requests
from typing import Dict, Any, List
from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential
from data_formulator.data_loader.external_data_loader import ExternalDataLoader, sanitize_table_name

class PowerBIDataLoader(ExternalDataLoader):
    def list_params(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "tenant_id",
                "type": "string",
                "required": True,
                "default": "",
                "description": "Azure AD tenant ID"
            },
            {
                "name": "client_id",
                "type": "string",
                "required": True,
                "default": "",
                "description": "Azure AD client ID"
            },
            {
                "name": "client_secret",
                "type": "string",
                "required": True,
                "default": "",
                "description": "Azure AD client secret"
            },
            {
                "name": "workspace_id",
                "type": "string",
                "required": True,
                "default": "",
                "description": "Power BI workspace ID"
            }
        ]

    def __init__(self, duck_db_conn, **kwargs):
        super().__init__(duck_db_conn)
        self.tenant_id = kwargs.get('tenant_id')
        self.client_id = kwargs.get('client_id')
        self.client_secret = kwargs.get('client_secret')
        self.workspace_id = kwargs.get('workspace_id')
        
        # Initialize Azure AD credentials
        self.credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
        # Power BI API endpoints
        self.base_url = "https://api.powerbi.com/v1.0/myorg"
        self._access_token = None
        self._token_expiry = None

    def _get_access_token(self) -> str:
        """Get or refresh Power BI access token"""
        if not self._access_token or not self._token_expiry or datetime.now() >= self._token_expiry:
            token = self.credential.get_token("https://analysis.windows.net/powerbi/api/.default")
            self._access_token = token.token
            self._token_expiry = datetime.now() + timedelta(minutes=55)  # Refresh before the 1-hour expiration
        return self._access_token

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Power BI API requests"""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def list_tables(self, table_filter: str = None) -> List[Dict[str, Any]]:
        """List available tables in the Power BI dataset"""
        datasets_url = f"{self.base_url}/groups/{self.workspace_id}/datasets"
        response = requests.get(datasets_url, headers=self._get_headers())
        response.raise_for_status()
        
        results = []
        datasets = response.json()['value']
        
        for dataset in datasets:
            dataset_id = dataset['id']
            tables_url = f"{self.base_url}/groups/{self.workspace_id}/datasets/{dataset_id}/tables"
            tables_response = requests.get(tables_url, headers=self._get_headers())
            tables_response.raise_for_status()
            
            for table in tables_response.json()['value']:
                table_name = table['name']
                
                if table_filter and table_filter.lower() not in table_name.lower():
                    continue
                
                # Get table schema
                columns = [{
                    'name': col['name'],
                    'type': col['dataType']
                } for col in table.get('columns', [])]
                
                # Get sample data using EXECUTE QUERIES API
                sample_query = f"EVALUATE TOP(10, '{table_name}')"
                sample_data = self._execute_query(dataset_id, sample_query)
                
                table_metadata = {
                    "row_count": table.get('rowCount', 0),
                    "columns": columns,
                    "sample_rows": sample_data
                }
                
                results.append({
                    "name": f"{dataset['name']}.{table_name}",
                    "metadata": table_metadata
                })
        
        return results

    def _execute_query(self, dataset_id: str, query: str) -> List[Dict[str, Any]]:
        """Execute DAX query against Power BI dataset"""
        query_url = f"{self.base_url}/groups/{self.workspace_id}/datasets/{dataset_id}/executeQueries"
        payload = {
            "queries": [{"query": query}],
            "serializerSettings": {"includeNulls": True}
        }
        
        response = requests.post(query_url, headers=self._get_headers(), json=payload)
        response.raise_for_status()
        
        results = response.json()['results'][0]['tables'][0]['rows']
        return results

    def ingest_data(self, table_name: str, name_as: str = None, size: int = 1000000):
        """Import data from Power BI to DuckDB"""
        if name_as is None:
            name_as = sanitize_table_name(table_name.split('.')[-1])
        
        dataset_name, table_name = table_name.split('.')
        
        # Get dataset ID
        datasets_url = f"{self.base_url}/groups/{self.workspace_id}/datasets"
        response = requests.get(datasets_url, headers=self._get_headers())
        response.raise_for_status()
        
        dataset_id = next(
            (d['id'] for d in response.json()['value'] if d['name'] == dataset_name),
            None
        )
        
        if not dataset_id:
            raise ValueError(f"Dataset '{dataset_name}' not found")
        
        # Fetch data in chunks
        offset = 0
        chunk_size = min(size, 50000)  # Power BI has query size limits
        
        while offset < size:
            query = f"EVALUATE TOP({chunk_size}, SKIP({offset}, '{table_name}'))"
            chunk_data = self._execute_query(dataset_id, query)
            
            if not chunk_data:
                break
                
            # Convert to DataFrame
            chunk_df = pd.DataFrame(chunk_data)
            
            # For first chunk, create new table; for subsequent chunks, append
            if offset == 0:
                self.ingest_df_to_duckdb(chunk_df, name_as)
            else:
                # Append to existing table
                self.duck_db_conn.register(f'temp_df_{name_as}', chunk_df)
                self.duck_db_conn.execute(f"INSERT INTO {name_as} SELECT * FROM temp_df_{name_as}")
                self.duck_db_conn.execute(f"DROP VIEW temp_df_{name_as}")
            
            offset += chunk_size

    def view_query_sample(self, query: str) -> Dict[str, Any]:
        """Preview DAX query results"""
        dataset_id = self._get_default_dataset_id()
        results = self._execute_query(dataset_id, query)
        
        if not results:
            return {"status": "error", "error": "No results returned"}
        
        return {
            "status": "success",
            "sample": results[:10],
            "columns": list(results[0].keys()) if results else []
        }

    def ingest_data_from_query(self, query: str, name_as: str) -> None:
        """Import data from a DAX query to DuckDB"""
        dataset_id = self._get_default_dataset_id()
        results = self._execute_query(dataset_id, query)
        
        if results:
            df = pd.DataFrame(results)
            self.ingest_df_to_duckdb(df, name_as)

    def _get_default_dataset_id(self) -> str:
        """Get the first dataset ID in the workspace"""
        datasets_url = f"{self.base_url}/groups/{self.workspace_id}/datasets"
        response = requests.get(datasets_url, headers=self._get_headers())
        response.raise_for_status()
        
        datasets = response.json()['value']
        if not datasets:
            raise ValueError("No datasets found in the workspace")
        
        return datasets[0]['id']