# from dagster_duckdb import DuckDBResource

# database_resource = DuckDBResource(
#     database="data/staging/data.duckdb"
# )

from dagster_duckdb import DuckDBResource
from dagster import EnvVar

database_resource = DuckDBResource(
    database=EnvVar("DUCKDB_DATABASE")      # replaced with environment variable
)
