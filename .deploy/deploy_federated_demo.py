from __future__ import annotations

import os
from pathlib import Path

from azure.identity import WorkloadIdentityCredential

from fabric_cicd import change_log_level, FabricWorkspace, publish_all_items


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"Missing required environment variable: {name}"
        raise RuntimeError(msg)
    return value


def main() -> None:
    workspace_id = require_env("FABRIC_WORKSPACE_ID")
    target_environment = os.getenv("FABRIC_TARGET_ENVIRONMENT", "demo")

    repo_root = Path(os.getenv("GITHUB_WORKSPACE", str(Path(__file__).resolve().parent.parent.parent)))
    repository_directory = str(repo_root / "sample" / "workspace")

    client_id = require_env("AZURE_CLIENT_ID")
    tenant_id = require_env("AZURE_TENANT_ID")
    federated_token_file = require_env("AZURE_FEDERATED_TOKEN_FILE")

    print(f"AZURE_CLIENT_ID: {client_id}")
    print(f"AZURE_TENANT_ID: {tenant_id}")
    print(f"AZURE_FEDERATED_TOKEN_FILE exists: {os.path.exists(federated_token_file)}")
    print(f"Repository directory: {repository_directory}")
    print(f"Target environment: {target_environment}")

    credential = WorkloadIdentityCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        token_file_path=federated_token_file,
    )
    
    change_log_level("DEBUG")

    workspace = FabricWorkspace(
        workspace_id=workspace_id,
        repository_directory=repository_directory,
        environment=target_environment,
        item_type_in_scope=["Environment", "Notebook", "DataPipeline"],
        token_credential=credential,
    )

    publish_all_items(workspace)


if __name__ == "__main__":
    main()
