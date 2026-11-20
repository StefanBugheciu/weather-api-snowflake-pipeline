import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def connect():
    from dotenv import load_dotenv
    import snowflake.connector

    load_dotenv(ROOT / ".env")
    settings = {}
    for key in ("account", "user"):
        value = os.getenv(f"SNOWFLAKE_{key.upper()}")
        if not value:
            raise ValueError(f"Set SNOWFLAKE_{key.upper()} in .env")
        settings[key] = value

    for key in ("oauth_client_id", "oauth_client_secret", "oauth_authorization_url",
                "oauth_token_request_url", "oauth_redirect_uri", "oauth_scope"):
        value = os.getenv(f"SNOWFLAKE_{key.upper()}")
        if value:
            settings[key] = value

    return snowflake.connector.connect(
        **settings,
        role=os.getenv("SNOWFLAKE_ROLE", "SYSADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", "OAUTH_AUTHORIZATION_CODE"),
        login_timeout=30,
        client_store_temporary_credential=False,
    )


def run_sql(connection, filename: str, *, show_results: bool = False) -> None:
    with (ROOT / "sql" / filename).open(encoding="utf-8") as script:
        for cursor in connection.execute_stream(script, remove_comments=True):
            try:
                if show_results and cursor.description:
                    print([column[0] for column in cursor.description])
                    for row in cursor:
                        print(row)
            finally:
                cursor.close()
