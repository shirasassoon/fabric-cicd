# Enterprise Fabric Deployment Demo

This directory contains the deployment script and setup for an end-to-end Microsoft Fabric workspace deployment using [fabric-cicd](https://github.com/microsoft/fabric-cicd) and GitHub Actions with a Service Principal (SPN) authenticated via OIDC Workload Identity Federation.

## Overview

The deployment workflow (`../.github/workflows/deploy_to_fabric.yml`) uses the Python script `deploy_fabric_workspace.py` to:

1. Authenticate to Azure using OIDC Workload Identity Federation (no client secret required).
2. Initialize a `FabricWorkspace` pointing at the `sample/workspace/` items in this repository.
3. **Publish** all in-scope items (Notebooks, DataPipelines, Environments) to the target Fabric workspace.
4. **Unpublish** any orphaned items that exist in the workspace but are no longer in the repository.

## Prerequisites

### 1. Azure AD App Registration (Service Principal)

- Register an application in Azure AD (Entra ID).
- **Do not create a client secret.** Instead, configure a **Federated Credential**:
  - In Azure Portal → App registrations → your app → **Certificates & secrets → Federated credentials → Add credential**
  - Scenario: **GitHub Actions deploying Azure resources**
  - Organization: your GitHub org or username
  - Repository: `fabric-cicd`
  - Entity type: **Environment**
  - Environment name: `PPE` (repeat for `PROD`)
- Note the **Tenant ID** and **Client ID**.

### 2. Fabric Workspace Permissions

- Grant the Service Principal **Contributor** (or Admin) access to the target Fabric workspace. This can be done from the Fabric portal under Workspace Settings → Manage Access.

### 3. GitHub Environments and Secrets

Create a GitHub Environment for each target (`PPE`, `PROD`) at **GitHub → Settings → Environments**, then add the following secrets to each environment:

| Secret Name           | Description                                     |
| --------------------- | ----------------------------------------------- |
| `AZURE_TENANT_ID`     | Azure AD tenant ID                              |
| `AZURE_CLIENT_ID`     | Service Principal application (client) ID       |
| `FABRIC_WORKSPACE_ID` | Target Microsoft Fabric workspace ID (GUID)     |

> No `AZURE_CLIENT_SECRET` needed — OIDC Workload Identity Federation eliminates the need for long-lived secrets.

## How to Run

1. Go to the **Actions** tab of this repository.
2. Select the **Deploy to Fabric Workspace** workflow.
3. Click **Run workflow**.
4. Choose the target environment (`PPE` or `PROD`).
5. Click **Run workflow** to start the deployment.

The workflow will check out the repo, log in to Azure via OIDC, install `fabric-cicd`, and execute the deployment script against the configured Fabric workspace.

## Customization

### Deploying Different Item Types

Edit `item_type_in_scope` in `deploy_fabric_workspace.py` to include other Fabric item types available in the sample workspace (e.g., `SemanticModel`, `Report`, `Lakehouse`, `Eventhouse`, etc.).

### Using Parameter Substitution

The sample workspace includes a `parameter.yml` file that supports environment-specific value replacement (e.g., connection strings, workspace IDs). The `FabricWorkspace` class automatically applies these parameter substitutions based on the `environment` value.

### Enabling Debug Logging

Enable verbose output by enabling **debug logging** in the GitHub Actions run (Settings → Actions → Enable debug logging), or by setting the `ACTIONS_STEP_DEBUG` secret to `true.