# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Dependency graph helpers for batched bulk item publishing."""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import fabric_cicd.constants as constants
from fabric_cicd._common._exceptions import InputError
from fabric_cicd._parameter._utils import process_environment_key, process_input_path

if TYPE_CHECKING:
    from fabric_cicd.fabric_workspace import FabricWorkspace

logger = logging.getLogger(__name__)


def has_unfiltered_items_variable(workspace_obj: "FabricWorkspace") -> bool:
    """
    Returns True if any find_replace or key_value_replace entry uses an $items.* variable
    in replace_value without any item_type, item_name, or file_path filter.

    When this is the case, dependency scope cannot be narrowed and bulk publish would
    treat all items as dependents of the referenced item, so callers should fall back
    to standard (serial) deployment instead.

    Args:
        workspace_obj: The FabricWorkspace object.

    Returns:
        True if at least one unfiltered $items.* entry exists, False otherwise.
    """
    items_pattern = re.compile(constants.DYNAMIC_VARIABLES_ITEMS_REGEX, re.IGNORECASE)

    for param_name in ("find_replace", "key_value_replace"):
        for param_dict in workspace_obj.environment_parameter.get(param_name, []):
            replace_value = param_dict.get("replace_value")
            if not isinstance(replace_value, dict):
                continue
            processed = process_environment_key(workspace_obj.environment, dict(replace_value))
            env_value = processed.get(workspace_obj.environment)
            if not isinstance(env_value, str) or not items_pattern.search(env_value):
                continue
            if not any(param_dict.get(f) for f in ("item_type", "item_name", "file_path")):
                return True

    return False


def build_dynamic_variable_dependency_graph(
    workspace_obj: "FabricWorkspace", publish_item_keys: set[str]
) -> list[tuple[str, str]]:
    """
    Builds a dependency graph from dynamic $items.* variables in the parameter file.

    Scans find_replace and key_value_replace entries for $items.* patterns in replace_value.
    For each reference to an item that is NOT already deployed but IS in the current publish set,
    creates a dependency edge.

    Args:
        workspace_obj: The FabricWorkspace object.
        publish_item_keys: Set of item keys included in the current bulk publish operation.

    Returns:
        A list of dependency edges as (referencing_item_key, referenced_item_key) tuples,
        where item_key format is "ItemType.ItemName". An empty list means all dynamic
        variables are resolvable upfront and a single bulk call is sufficient.
    """
    items_pattern = re.compile(constants.DYNAMIC_VARIABLES_ITEMS_REGEX, re.IGNORECASE)
    edges: list[tuple[str, str]] = []

    for param_name in ("find_replace", "key_value_replace"):
        param_values = workspace_obj.environment_parameter.get(param_name, [])

        for param_dict in param_values:
            replace_value = param_dict["replace_value"]
            processed = process_environment_key(workspace_obj.environment, dict(replace_value))
            env_value = processed.get(workspace_obj.environment)
            if not isinstance(env_value, str) or not items_pattern.search(env_value):
                continue

            referenced = _parse_items_variable_reference(env_value)
            if referenced is None:
                continue

            ref_type, ref_name = referenced
            ref_key = f"{ref_type}.{ref_name}"

            if ref_type in workspace_obj.deployed_items and ref_name in workspace_obj.deployed_items[ref_type]:
                continue

            if ref_key in publish_item_keys:
                referencing_keys = _get_referencing_item_keys(
                    param_dict, workspace_obj.repository_items, workspace_obj.repository_directory
                )
                for referencing_key in referencing_keys:
                    if referencing_key != ref_key and referencing_key in publish_item_keys:
                        edges.append((referencing_key, ref_key))

    return edges


def _parse_items_variable_reference(variable: str) -> tuple[str, str] | None:
    """
    Parses a $items.* variable string to extract the referenced item type and name.

    Args:
        variable: The $items variable string (e.g., "$items.Lakehouse.my_lh.$id").

    Returns:
        A tuple of (item_type, item_name) or None if parsing fails.
    """
    var_string = variable.removeprefix("$items.")

    if ".$" in var_string:
        name_part, _attr = var_string.rsplit(".$", 1)
    elif "." in var_string:
        last_dot = var_string.rfind(".")
        name_part = var_string[:last_dot]
    else:
        return None

    type_dot = name_part.find(".")
    if type_dot == -1:
        return None

    item_type = name_part[:type_dot].strip()
    item_name = name_part[type_dot + 1 :].strip()

    if not item_type or not item_name:
        return None

    return item_type, item_name


def _get_referencing_item_keys(
    param_dict: dict, repository_items: dict, repository_directory: Optional[Path] = None
) -> list[str]:
    """
    Determines which items a parameter entry applies to based on item_type/item_name filters.

    Args:
        param_dict: The parameter dictionary entry with optional item_type and item_name filters.
        repository_items: Dictionary of items in the repository.
        repository_directory: Root path of the repository. Used to resolve file_path filters.

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
    Computes publish batches from a dependency graph using topological sort.

    Items with no dependencies or whose dependencies are already deployed go into Batch 0.
    Items depending on Batch 0 items go into Batch 1, and so on.
    If no dependency edges exist, all items are placed in a single batch (Batch 0).

    Args:
        items_with_context: List of (item_name, Item, ItemPublisher) tuples to publish.
        dependency_edges: List of (referencing_key, referenced_key) dependency edges
            where key format is "ItemType.ItemName".

    Returns:
        A list of batches, where each batch is a list of (item_name, Item, ItemPublisher) tuples.

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
