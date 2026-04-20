# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""
Enterprise deployment script for Microsoft Fabric workspace items.

This script is designed to run in GitHub Actions using a Service Principal (SPN)
with ClientSecretCredential for authentication. It deploys all in-scope Fabric
items from the sample workspace to a target Fabric workspace, then cleans up
any orphaned items not present in the repository.

Required environment variables (set via GitHub Actions secrets):
    AZURE_TENANT_ID       - Azure AD tenant ID
    AZURE_CLIENT_ID       - Service principal (SPN) client/application ID
    AZURE_CLIENT_SECRET   - Service principal client secret
    FABRIC_WORKSPACE_ID   - Target Fabric workspace ID
    ENVIRONMENT           - Deployment environment name (e.g., PPE, PROD)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from azure.identity import ClientSecretCredential

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
    # Enable debug logging when ACTIONS_STEP_DEBUG is set in GitHub Actions
    if os.getenv("ACTIONS_STEP_DEBUG", "false").lower() == "true":
        change_log_level("DEBUG")

    # --- Authentication via Service Principal ---
    tenant_id = get_required_env("AZURE_TENANT_ID")
    client_id = get_required_env("AZURE_CLIENT_ID")
    client_secret = get_required_env("AZURE_CLIENT_SECRET")

    token_credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # --- Deployment configuration ---
    workspace_id = get_required_env("FABRIC_WORKSPACE_ID")
    environment = os.getenv("ENVIRONMENT", "PROD")

    # Resolve the sample workspace directory relative to the repo root
    repo_root = Path(os.getenv("GITHUB_WORKSPACE", str(Path(__file__).resolve().parent.parent)))
    repository_directory = str(repo_root / "sample" / "workspace")

    # Item types to deploy — covers the most common Fabric item types in the sample workspace
    item_type_in_scope = [
        "Notebook",
        "DataPipeline",
        "Environment",
    ]

    logger.info("Starting deployment to workspace '%s' (environment: %s)", workspace_id, environment)
    logger.info("Repository directory: %s", repository_directory)
    logger.info("Item types in scope: %s", item_type_in_scope)

    # --- Initialize workspace ---
    target_workspace = FabricWorkspace(
        workspace_id=workspace_id,
        environment=environment,
        repository_directory=repository_directory,
        item_type_in_scope=item_type_in_scope,
        token_credential=token_credential,
    )

    # --- Publish all items in scope ---
    publish_all_items(target_workspace)

    # --- Unpublish orphaned items not found in the repository ---
    unpublish_all_orphan_items(target_workspace)

    logger.info("Deployment completed successfully.")


if __name__ == "__main__":
    main()
