# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""
Enterprise deployment script for Microsoft Fabric workspace items.

This script is designed to run in GitHub Actions using a Service Principal (SPN)
authenticated via OIDC Workload Identity Federation (no client secret required).
It deploys all in-scope Fabric items from the sample workspace to a target Fabric
workspace, then cleans up any orphaned items not present in the repository.

Required environment variables (set via GitHub Actions secrets):
    FABRIC_WORKSPACE_ID   - Target Fabric workspace ID
    ENVIRONMENT           - Deployment environment name (e.g., PPE, PROD)

Authentication is handled by the azure/login@v2 action using OIDC before this
script runs. AzureCliCredential reads the token from that CLI session automatically.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from azure.identity import AzureCliCredential

from fabric_cicd import FabricWorkspace, change_log_level, publish_all_items, unpublish_all_orphan_items

logger = logging.getLogger(__name__)


def get_required_env(name: str) -> str:
    """Retrieve a required environment variable or exit with an error."""
    value = os.getenv(name)
    if not value:
        logger.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return value


def main() -> None:
    """Run the end-to-end Fabric workspace deployment."""
    # Enable debug logging
    change_log_level()

    # --- Authentication via Azure CLI (OIDC Workload Identity Federation) ---
    # AzureCliCredential reads the token from the Azure CLI session established
    # by the azure/login@v2 action using OIDC. No client secret is required or stored.
    token_credential = AzureCliCredential()

    # --- Deployment configuration ---
    workspace_id = get_required_env("FABRIC_WORKSPACE_ID")
    environment = os.getenv("ENVIRONMENT", "PROD")

    # Resolve the sample workspace directory relative to the repo root
    repo_root = Path(os.getenv("GITHUB_WORKSPACE", str(Path(__file__).resolve().parent.parent)))
    repository_directory = str(repo_root / "sample" / "workspace")

    logger.info("Starting deployment to workspace '%s' (environment: %s)", workspace_id, environment)
    logger.info("Repository directory: %s", repository_directory)

    # --- Initialize workspace ---
    target_workspace = FabricWorkspace(
        workspace_id=workspace_id,
        environment=environment,
        repository_directory=repository_directory,
        token_credential=token_credential,
    )

    # --- Publish all items in scope ---
    publish_all_items(target_workspace)

    # --- Unpublish orphaned items not found in the repository ---
    unpublish_all_orphan_items(target_workspace)

    logger.info("Deployment completed successfully.")


if __name__ == "__main__":
    main()
