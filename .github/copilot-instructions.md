# Fabric CICD

fabric-cicd is a Python library for Microsoft Fabric CI/CD automation. It supports code-first Continuous Integration/Continuous Deployment automations to seamlessly integrate Source Controlled workspaces into a deployment framework.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

- Bootstrap and set up the development environment:
    - Ensure Python 3.9+ is installed
    - `pip install uv`
    - `uv sync --dev` -- NEVER CANCEL. Set timeout to 120+ seconds.
- Run tests:
    - `uv run pytest -v` -- NEVER CANCEL. Set timeout to 120+ seconds.
- Code formatting and linting:
    - `uv run ruff format` -- Apply formatting fixes.
    - `uv run ruff check` -- Check for linting issues.
    - `uv run ruff format --check` -- Check if formatting is needed.
- Documentation:
    - `uv run mkdocs build --clean` -- Build documentation.
    - `uv run mkdocs serve` -- starts local documentation server.

## Validation

- ALWAYS test library import functionality: `uv run python -c "from fabric_cicd import FabricWorkspace; print('Import successful')"`
- ALWAYS run through the complete test suite after making changes: `uv run pytest -v`
- ALWAYS run `uv run ruff format` and `uv run ruff check` before committing or the CI (.github/workflows/validate.yml) will fail
- The library requires Azure authentication (DefaultAzureCredential) for actual functionality - imports work without auth

## Project Structure

```
/
├── .github/workflows/    # CI/CD pipelines (test.yml, validate.yml, bump.yml)
├── docs/                # Documentation source files
├── sample/              # Example workspace structure and items
├── src/fabric_cicd/     # Main library source code
├── tests/               # Test files
├── pyproject.toml       # Project configuration and dependencies
├── ruff.toml           # Code formatting and linting configuration
├── mkdocs.yml          # Documentation configuration
├── activate.ps1        # PowerShell setup script (Windows only)
└── uv.lock            # Dependency lock file
```

## Common Tasks

Reference these validated outputs instead of running bash commands to save time:

### Import and Basic Usage

```python
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items

# Initialize workspace (requires Azure auth)
workspace = FabricWorkspace(
    workspace_id="your-workspace-id",
    repository_directory="/path/to/workspace/items",
    item_type_in_scope=["Notebook", "DataPipeline", "Environment"],
    environment="DEV"
)

# Deploy items
publish_all_items(workspace)

# Clean up orphaned items
unpublish_all_orphan_items(workspace)
```

### Config-Based Deployment

An alternative to the programmatic API, `deploy_with_config()` centralizes all deployment
settings in a YAML config file. It is a public API exported from the package.

- Entry point: `deploy_with_config()` in `src/fabric_cicd/publish.py`
- Config utilities: `src/fabric_cicd/_common/_config_utils.py` (loading, extraction)
- Config validation: `src/fabric_cicd/_common/_config_validator.py`
- Documentation: `docs/how_to/config_deployment.md`
- Tests: `tests/test_deploy_with_config.py`, `tests/test_config_validator.py`

Basic usage:

```python
from fabric_cicd import deploy_with_config
result = deploy_with_config(config_file_path="config.yml", environment="dev")
```

### Onboarding New Item Types

Follow these instructions when the task is to add support for a new Microsoft Fabric item type in fabric-cicd.
Onboarding a new Microsoft Fabric item type requires changes across multiple files in a specific order.

**Pre-requisites:**

- Confirm Microsoft Fabric API support for the new item type, search API documentation: https://learn.microsoft.com/en-us/rest/api/fabric/
- New item type definition must be supported in source control/Git integration and the Fabric API must support deploying its definition. See supported items: https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/item-definition-overview. Note that if an item type has a definition, but the API does not support definition deployment, it cannot be supported by fabric-cicd.
- Determine if the new item type has unique deployment or parameterization requirements
- Check for dependency on other item types

**Steps:**

1. Register the new item type in `src/fabric_cicd/constants.py`:
    - Add to the `ItemType` enum (e.g. `ITEM_TYPE_NEWTYPE = "NewType"`)
    - Add to `SERIAL_ITEM_PUBLISH_ORDER` - choose the correct position based on the item's dependencies. Items that other items depend on must come earlier in the order. The unpublish order is automatically the reverse.
    - Optionally add to `SHELL_ONLY_PUBLISH` — If the API does not support item definition, only supports metadata (shell) deployment (like Lakehouse, Warehouse, SQL Database, ML Experiment).
    - Optionally add to `EXCLUDE_PATH_REGEX_MAPPING` — If certain file paths within the item should be excluded during publish (e.g., .pbi/ folders for Report/Semantic Model, .children/ for Eventhouse).
    - Optionally add to `API_FORMAT_MAPPING` — If the Fabric API requires a specific format string for the item's definition (e.g., "ipynb" for Notebooks, "SparkJobDefinitionV2" for Spark Job Definitions).
    - Optionally add to `UNPUBLISH_FLAG_MAPPING` — If unpublishing the item is destructive and should be gated behind a feature flag (like Lakehouse, Warehouse, Eventhouse). If so, also add a new `FeatureFlag` enum member.
    - Optionally add to `NO_ASSIGNED_CAPACITY_REQUIRED` — If the item doesn't require assigned capacity.
2. Create a Publisher Class in `src/fabric_cicd/_items/`:
    - Create a new file (e.g., `_mynewtype.py`) with a publisher class that extends `ItemPublisher`. The simplest case looks like this:

    ```python
    # src/fabric_cicd/_items/_mynewtype.py
    from fabric_cicd._items._base_publisher import ItemPublisher
    from fabric_cicd.constants import ItemType

    class MyNewTypePublisher(ItemPublisher):
        item_type = ItemType.MY_NEW_TYPE.value
    ```

    - For more complex items, you can override these methods from `ItemPublisher`:
        - `publish_one(item_name, _item)`: Custom publish logic (e.g., creation payloads, exclude paths, custom file processing)
        - `get_items_to_publish()`: Custom filtering of items before publishing
        - `get_unpublish_order(items)`: Custom ordering of items during unpublish (e.g., dependency-based). **Must also set `has_dependency_tracking = True`** class attribute or the override won't be called.
        - `pre_publish_all()`: Pre-publish checks (e.g., Environment publish state check)
        - `post_publish_all()`: Post-publish actions (e.g., Semantic Model connection binding)
        - `post_publish_all_check()`: Async publish state checking (set `has_async_publish_check = True`)
    - See existing examples for reference:
        - Simple: `_graphqlapi.py`, `_copyjob.py` (no overrides needed)
        - With exclude paths: `_dataagent.py`, `_eventhouse.py`
        - With custom file processing: `_report.py`, `_notebook.py`, `_datapipeline.py`
        - With creation payload: `_warehouse.py`, `_lakehouse.py`
        - With post-publish actions: `_semanticmodel.py` (connection binding), `_environment.py` (metadata + async check)

3. Register the Publisher in the Factory Method:
    - In `src/fabric_cicd/_items/_base_publisher.py`, update the `ItemPublisher.create()` factory method:
        - Add the import for your new publisher class
        - Add the mapping entry in the `publisher_mapping` dictionary:
        ```python
        from fabric_cicd._items._mynewtype import MyNewTypePublisher
        publisher_mapping = {
            ...
            ItemType.MY_NEW_TYPE: MyNewTypePublisher,
        }
        ```
4. Add Tests:
    - Create or update test files in tests/:
        - Add unit tests for any custom publish logic
        - Verify the item type is accepted in `item_type_in_scope` validation
        - Test publish and unpublish flows with mocked API responses

5. Documentation Updates:
    - The supported item types list auto-generates from the `ItemType` enum via
      `docs/config/pre-build/update_item_types.py` — no manual update needed for the list.
    - Add a new section to `docs/how_to/item_types.md` for the new item type, following
      the existing pattern: parameterization behavior, deployment caveats, and links to
      Microsoft's CI/CD documentation for that item type.
6. Sample Files (Optional)
    - If helpful, add sample workspace item files under `sample/workspace/` showing the expected directory structure for the new item type.

### Test Categories

- **Unit Tests**: `tests/test_*.py` - Test individual components
- **Integration Tests**: Validate API interactions (mocked)
- **Parameter Tests**: Test parameterization and variable replacement
- **File Handling Tests**: Test various item type processing
- **Workspace Tests**: Test folder hierarchy and item management

### Key Dependencies

- `azure-identity` - Azure authentication
- `dpath` - JSON path manipulation
- `pyyaml` - YAML parameter file processing
- `requests` - HTTP API calls
- `packaging` - Version handling

### Development Dependencies

- `uv` - Package manager and virtual environment
- `ruff` - Code formatting and linting
- `pytest` - Testing framework
- `mkdocs-material` - Documentation generation

### GitHub Actions Workflows

- **test.yml**: Runs `uv run pytest -v` on PR
- **validate.yml**: Runs `ruff format` and `ruff check` validation
- **bump.yml**: Handles version bumps (requires PR title format vX.X.X)

### Authentication Requirements

- Uses Azure DefaultAzureCredential by default
- Requires Azure CLI (`az login`) or Az.Accounts PowerShell module for local development
- Service principal authentication supported for CI/CD pipelines
- No authentication needed for basic library imports or testing

### Microsoft Fabric APIs

- The library primarily integrates with Microsoft Fabric Core APIs
- API documentation: https://learn.microsoft.com/en-us/rest/api/fabric/
- Common API operations include workspace management, item publishing, and artifact deployment

### Timing Expectations and Timeouts

- **CRITICAL**: NEVER CANCEL any build or test commands. Always use adequate timeouts:
    - uv sync: 120+ seconds
    - pytest: 120+ seconds
    - All other commands: 60+ seconds

### Pull Request Requirements

- **PR Title MUST follow this exact format**: "Fixes #123 - Short Description" where #123 is the issue number
    - Use "Fixes" for bug fixes, "Closes" for features, "Resolves" for other changes
    - Example: "Fixes #520 - Add Python version requirements to documentation"
    - Version bump PRs are an exception: title must be "vX.X.X" format only
- PR description should be a copilot generated summary
- MUST pass ruff formatting and linting checks
- MUST pass all tests
- All PRs must be linked to a valid GitHub issue - no PRs without associated issues

### Common Troubleshooting

- **Import errors**: Use `uv run python` instead of direct `python` to ensure virtual environment
- **Test failures**: Check if Azure credentials are interfering with mocked tests
- **Formatting issues**: Run `uv run ruff format` to auto-fix most issues
- **CI failures**: Usually due to missing `ruff format` or failing tests

### Repository Examples

See `sample/workspace/` for example Microsoft Fabric item structures and `docs/example/` for usage patterns in different CI/CD scenarios (Azure DevOps, GitHub Actions, local development).

### Key Files to Monitor

- `src/fabric_cicd/constants.py` - Version and configuration constants
- `src/fabric_cicd/fabric_workspace.py` - Main workspace management class
- `pyproject.toml` - Project dependencies and configuration
- `parameter.yml` - Environment-specific parameter template (in sample/)
