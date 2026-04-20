# Enterprise Fabric Deployment Demo

This directory contains the deployment script and setup for an end-to-end Microsoft Fabric workspace deployment using [fabric-cicd](https://github.com/microsoft/fabric-cicd) and GitHub Actions with a Service Principal (SPN).

## Overview

The deployment workflow (`../.github/workflows/deploy_to_fabric.yml`) uses the Python script `deploy_fabric_workspace.py` to:

1. Authenticate to Azure using a Service Principal (`ClientSecretCredential`).
2. Initialize a `FabricWorkspace` pointing at the `sample/workspace/` items in this repository.
3. **Publish** all in-scope items (Notebooks, DataPipelines, Environments) to the target Fabric workspace.
4. **Unpublish** any orphaned items that exist in the workspace but are no longer in the repository.

## Prerequisites

### 1. Azure AD App Registration (Service Principal)

- Register an application in Azure AD (Entra ID).
- Create a client secret for the application.
- Note the **Tenant ID**, **Client ID**, and **Client Secret**.

### 2. Fabric Workspace Permissions

- Grant the Service Principal **Contributor** (or Admin) access to the target Fabric workspace. This can be done from the Fabric portal under Workspace Settings → Manage Access.

### 3. GitHub Repository Secrets

Add the following secrets in **GitHub → Settings → Secrets and variables → Actions**:

| Secret Name           | Description                                     |
| --------------------- | ----------------------------------------------- |
| `AZURE_TENANT_ID`     | Azure AD tenant ID                              |
| `AZURE_CLIENT_ID`     | Service Principal application (client) ID       |
| `AZURE_CLIENT_SECRET` | Service Principal client secret                 |
| `FABRIC_WORKSPACE_ID` | Target Microsoft Fabric workspace ID (GUID)     |

### 4. (Optional) GitHub Environments

The workflow references a GitHub environment matching the selected deployment target (`PPE` or `PROD`). You can configure [GitHub environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) with environment-specific secrets and protection rules (e.g., required reviewers) for a staged deployment.

## How to Run

1. Go to the **Actions** tab of this repository.
2. Select the **Deploy to Fabric Workspace** workflow.
3. Click **Run workflow**.
4. Choose the target environment (`PPE` or `PROD`).
5. Click **Run workflow** to start the deployment.

The workflow will check out the repo, install `fabric-cicd`, and execute the deployment script against the configured Fabric workspace.

## Customization

### Deploying Different Item Types

Edit `item_type_in_scope` in `deploy_fabric_workspace.py` to include other Fabric item types available in the sample workspace (e.g., `SemanticModel`, `Report`, `Lakehouse`, `Eventhouse`, etc.).

### Using Parameter Substitution

The sample workspace includes a `parameter.yml` file that supports environment-specific value replacement (e.g., connection strings, workspace IDs). The `FabricWorkspace` class automatically applies these parameter substitutions based on the `environment` value.

### Enabling Debug Logging

Enable verbose output by enabling **debug logging** in the GitHub Actions run (Settings → Actions → Enable debug logging), or by setting the `ACTIONS_STEP_DEBUG` secret to `true`.
