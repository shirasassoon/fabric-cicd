from __future__ import annotations

import os

from azure.identity import WorkloadIdentityCredential


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"Missing required environment variable: {name}"
        raise RuntimeError(msg)
    return value


def main() -> None:
    client_id = require_env("AZURE_CLIENT_ID")
    tenant_id = require_env("AZURE_TENANT_ID")
    federated_token_file = require_env("AZURE_FEDERATED_TOKEN_FILE")

    print(f"AZURE_CLIENT_ID: {client_id}")
    print(f"AZURE_TENANT_ID: {tenant_id}")
    print(f"AZURE_FEDERATED_TOKEN_FILE exists: {os.path.exists(federated_token_file)}")

    credential = WorkloadIdentityCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        token_file_path=federated_token_file,
    )

    token = credential.get_token("https://api.fabric.microsoft.com/.default")

    print("Successfully acquired Fabric token using federated credentials.")
    print(f"Token expires_on: {token.expires_on}")


if __name__ == "__main__":
    main()
