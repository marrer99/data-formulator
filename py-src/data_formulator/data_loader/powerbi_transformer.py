from typing import Dict, Any, List
import pandas as pd

class PowerBITransformer:
    DUCKDB_TO_POWERBI_TYPES = {
        'INTEGER': 'Int64',
        'BIGINT': 'Int64',
        'SMALLINT': 'Int64',
        'DOUBLE': 'Double',
        'REAL': 'Double',
        'DECIMAL': 'Double',
        'VARCHAR': 'String',
        'TEXT': 'String',
        'BOOLEAN': 'Boolean',
        'TIMESTAMP': 'DateTime',
        'DATE': 'DateTime',
        'TIME': 'DateTime'
    }

    POWERBI_TO_DUCKDB_TYPES = {
        'Int64': 'BIGINT',
        'Double': 'DOUBLE',
        'String': 'VARCHAR',
        'Boolean': 'BOOLEAN',
        'DateTime': 'TIMESTAMP',
        'Decimal': 'DECIMAL(18,6)',
        'Currency': 'DECIMAL(18,6)'
    }

    @staticmethod
    def transform_for_powerbi(df: pd.DataFrame) -> pd.DataFrame:
        transformed_df = df.copy()
        for column in transformed_df.columns:
            if pd.api.types.is_datetime64_any_dtype(transformed_df[column]):
                transformed_df[column] = transformed_df[column].dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            if pd.api.types.is_numeric_dtype(transformed_df[column]):
                transformed_df[column] = transformed_df[column].fillna(0)
            else:
                transformed_df[column] = transformed_df[column].fillna('')
            if pd.api.types.is_bool_dtype(transformed_df[column]):
                transformed_df[column] = transformed_df[column].map({True: 'true', False: 'false'})
        return transformed_df

    @staticmethod
    def transform_from_powerbi(data: List[Dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(data)
        for column in df.columns:
            if df[column].dtype == 'object':
                try:
                    df[column] = pd.to_datetime(df[column])
                except (ValueError, TypeError):
                    pass
            if df[column].dtype == 'object':
                if df[column].str.lower().isin(['true', 'false']).all():
                    df[column] = df[column].str.lower().map({'true': True, 'false': False})
        return df

    @staticmethod
    def get_powerbi_schema(df: pd.DataFrame) -> List[Dict[str, str]]:
        schema = []
        for column in df.columns:
            if pd.api.types.is_integer_dtype(df[column]):
                pbi_type = 'Int64'
            elif pd.api.types.is_float_dtype(df[column]):
                pbi_type = 'Double'
            elif pd.api.types.is_bool_dtype(df[column]):
                pbi_type = 'Boolean'
            elif pd.api.types.is_datetime64_any_dtype(df[column]):
                pbi_type = 'DateTime'
            else:
                pbi_type = 'String'
            schema.append({'name': column, 'dataType': pbi_type})
        return schema
