# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Dependency graph helpers for batched bulk item publishing."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fabric_cicd._common._exceptions import InputError, ParsingError
from fabric_cicd._parameter._utils import (
    ParsedDynamicVariable,
    parse_dynamic_variable,
    process_environment_key,
    process_input_path,
)

if TYPE_CHECKING:
    from fabric_cicd.fabric_workspace import FabricWorkspace

logger = logging.getLogger(__name__)

# Item attributes that are provisioned asynchronously after item creation and therefore
# require a provisioning wait between bulk-publish tiers before a downstream item can resolve
# them (mirrors constants.PROPERTY_PATH_ATTR_MAPPING; everything except the immediately
# available "id").
ASYNC_PROVISIONED_ATTRIBUTES = frozenset({"sqlendpoint", "sqlendpointid", "queryserviceuri"})


def _parse_current_workspace_item(env_value: str) -> Optional["ParsedDynamicVariable"]:
    """
    Returns the parsed variable when env_value is a *current-workspace* $items.* variable.

    Returns None for non-variable strings, $workspace.* variables, and cross-workspace item
    variables ($workspace.<name>.$items.*), whose targets live in another workspace and never
    create an in-batch dependency here.
    """
    if not isinstance(env_value, str) or not env_value.startswith("$"):
        return None

    try:
        parsed = parse_dynamic_variable(env_value)
    except ParsingError:
        return None

    if parsed.kind == "item" and parsed.workspace_name is None:
        return parsed

    return None


def _resolve_current_workspace_item_ref(env_value: str) -> Optional[tuple[str, str]]:
    """
    Returns (item_type, item_name) when env_value is a *current-workspace* $items.* variable.

    Returns None for:
      - non-variable strings (no leading '$')
      - $workspace.* variables (workspace id/name/name_encoded)
      - cross-workspace item variables ($workspace.<name>.$items.*), whose target lives
        in another workspace and therefore never creates an in-batch dependency here.

    Parsing is delegated to the canonical parser from #1102. By the time bulk publish
    runs, `_validate_dynamic_replacement_variables` has already validated every variable,
    so `parse_dynamic_variable` is not expected to raise here; the guard is purely defensive.
    """
    parsed = _parse_current_workspace_item(env_value)
    if parsed is None:
        return None
    return parsed.item_type, parsed.item_name


def _iter_dynamic_replace_values(workspace_obj: "FabricWorkspace") -> Iterator[tuple[dict, str]]:
    """
    Yields (param_dict, env_value) for every find_replace / key_value_replace entry whose
    replace_value resolves to a string for the active environment.
    """
    for param_name in ("find_replace", "key_value_replace"):
        for param_dict in workspace_obj.environment_parameter.get(param_name, []):
            replace_value = param_dict.get("replace_value")
            if not isinstance(replace_value, dict):
                continue
            processed = process_environment_key(workspace_obj.environment, dict(replace_value))
            env_value = processed.get(workspace_obj.environment)
            if isinstance(env_value, str):
                yield param_dict, env_value


def has_unfiltered_items_variable(workspace_obj: "FabricWorkspace") -> bool:
    """
    Returns True if any find_replace or key_value_replace entry uses a current-workspace
    $items.* variable in replace_value without any item_type, item_name, or file_path filter.

    When this is the case, dependency scope cannot be narrowed and bulk publish would treat
    all items as dependents of the referenced item, so callers should fall back to standard
    (serial) deployment instead.
    """
    for param_dict, env_value in _iter_dynamic_replace_values(workspace_obj):
        if _resolve_current_workspace_item_ref(env_value) is None:
            continue
        if not any(param_dict.get(f) for f in ("item_type", "item_name", "file_path")):
            return True

    return False


def get_async_provisioned_dependencies(
    workspace_obj: "FabricWorkspace", publish_item_keys: set[str]
) -> dict[str, set[str]]:
    """
    Maps each to-be-published source item to the asynchronously provisioned attributes referenced on it.

    Scans find_replace / key_value_replace entries for current-workspace $items.* variables whose
    attribute is asynchronously provisioned (SQL endpoint / Eventhouse query URI). Only source items
    that are part of the current publish set are included, since already-deployed items are already
    provisioned and impose no tiering.

    Returns:
        A dict of "ItemType.ItemName" -> set of async attribute names (e.g. {"sqlendpoint"}). Empty
        when no such references exist, in which case no between-tier provisioning wait is needed.
    """
    result: dict[str, set[str]] = {}

    for _param_dict, env_value in _iter_dynamic_replace_values(workspace_obj):
        parsed = _parse_current_workspace_item(env_value)
        if parsed is None or parsed.attribute not in ASYNC_PROVISIONED_ATTRIBUTES:
            continue

        key = f"{parsed.item_type}.{parsed.item_name}"
        if key in publish_item_keys:
            result.setdefault(key, set()).add(parsed.attribute)

    return result


def build_dynamic_variable_dependency_graph(
    workspace_obj: "FabricWorkspace", publish_item_keys: set[str]
) -> list[tuple[str, str]]:
    """
    Builds a dependency graph from current-workspace $items.* variables in the parameter file.

    For each replace_value that references an item which is NOT already deployed but IS in the
    current publish set, an edge (referencing_item_key -> referenced_item_key) is added, where
    key format is "ItemType.ItemName".

    Returns:
        A list of dependency edges. An empty list means all dynamic variables are resolvable
        upfront and a single bulk call is sufficient.
    """
    edges: list[tuple[str, str]] = []

    for param_dict, env_value in _iter_dynamic_replace_values(workspace_obj):
        referenced = _resolve_current_workspace_item_ref(env_value)
        if referenced is None:
            continue

        ref_type, ref_name = referenced
        ref_key = f"{ref_type}.{ref_name}"

        # Already deployed -> resolvable immediately, no ordering constraint.
        if ref_type in workspace_obj.deployed_items and ref_name in workspace_obj.deployed_items[ref_type]:
            continue

        # Only items new in this batch impose ordering.
        if ref_key not in publish_item_keys:
            continue

        referencing_keys = _get_referencing_item_keys(
            param_dict, workspace_obj.repository_items, workspace_obj.repository_directory
        )
        for referencing_key in referencing_keys:
            if referencing_key != ref_key and referencing_key in publish_item_keys:
                edges.append((referencing_key, ref_key))

    return edges


def _get_referencing_item_keys(
    param_dict: dict, repository_items: dict, repository_directory: Optional[Path] = None
) -> list[str]:
    """
    Determines which items a parameter entry applies to based on item_type/item_name/file_path filters.

    Returns:
        A list of item keys ("ItemType.ItemName") that this parameter applies to.
    """
    filter_type = param_dict.get("item_type")
    filter_name = param_dict.get("item_name")
    if repository_directory is not None:
        repository_directory = repository_directory.resolve()
    filter_paths = (
        process_input_path(repository_directory, param_dict.get("file_path")) if repository_directory else None
    )

    keys = []
    for item_type, items in repository_items.items():
        if filter_type is not None and item_type != filter_type:
            continue
        for item_name, item in items.items():
            if filter_name is not None and item_name != filter_name:
                continue
            if filter_paths is not None and not any(
                _is_path_in_item(file_path, item.path) for file_path in filter_paths
            ):
                continue
            keys.append(f"{item_type}.{item_name}")

    return keys


def _is_path_in_item(file_path: Path, item_path: Path) -> bool:
    """Returns True when file_path is contained by the repository item's directory."""
    try:
        file_path.resolve().relative_to(item_path.resolve())
        return True
    except ValueError:
        return False


def compute_publish_batches(
    items_with_context: list[tuple[str, object, object]],
    dependency_edges: list[tuple[str, str]],
) -> list[list[tuple[str, object, object]]]:
    """
    Computes publish batches from a dependency graph using topological sort (Kahn's algorithm).

    Items with no dependencies (or whose dependencies are already deployed) go into Batch 0;
    items depending on Batch 0 go into Batch 1, and so on. No edges -> a single batch.

    Raises:
        InputError: If a circular dependency is detected.
    """
    if not dependency_edges:
        return [items_with_context]

    item_key_to_context: dict[str, tuple[str, object, object]] = {}
    for item_name, item, publisher in items_with_context:
        key = f"{item.type}.{item_name}"
        item_key_to_context[key] = (item_name, item, publisher)

    publish_item_keys = set(item_key_to_context.keys())
    in_degree: dict[str, int] = {k: 0 for k in publish_item_keys}
    dependents: dict[str, list[str]] = {k: [] for k in publish_item_keys}

    for referencing, referenced in dependency_edges:
        if referencing in publish_item_keys and referenced in publish_item_keys:
            in_degree[referencing] = in_degree.get(referencing, 0) + 1
            dependents.setdefault(referenced, []).append(referencing)

    batches: list[list[tuple[str, object, object]]] = []
    current_batch_keys = [k for k, deg in in_degree.items() if deg == 0]

    processed = set()
    while current_batch_keys:
        batch = []
        next_batch_keys = []
        for key in current_batch_keys:
            if key in item_key_to_context:
                batch.append(item_key_to_context[key])
            processed.add(key)
            for dependent in dependents.get(key, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_batch_keys.append(dependent)

        if batch:
            batches.append(batch)
        current_batch_keys = next_batch_keys

    if len(processed) < len(publish_item_keys):
        cycle_keys = sorted(publish_item_keys - processed)
        msg = f"Circular dynamic variable dependency detected among: {', '.join(cycle_keys)}"
        raise InputError(msg, logger)

    return batches
