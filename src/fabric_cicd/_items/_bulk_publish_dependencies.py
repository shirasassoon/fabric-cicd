# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Dependency graph helpers for batched bulk item publishing."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fabric_cicd._common._exceptions import InputError
from fabric_cicd._parameter._utils import (
    ParsedDynamicVariable,
    parse_dynamic_variable,
    process_environment_key,
    process_input_path,
)
from fabric_cicd.constants import ASYNC_PROVISIONED_ATTRIBUTES

if TYPE_CHECKING:
    from fabric_cicd.fabric_workspace import FabricWorkspace

logger = logging.getLogger(__name__)


def _parse_current_workspace_item(env_value: str) -> Optional["ParsedDynamicVariable"]:
    """Parse a current-workspace $items.* variable, or return None."""
    if not env_value.startswith("$"):
        return None

    parsed = parse_dynamic_variable(env_value)

    if parsed.kind == "item" and parsed.workspace_name is None:
        return parsed

    return None


def _iter_dynamic_replace_values(
    workspace_obj: "FabricWorkspace",
) -> Iterator[tuple[dict, str, Optional["ParsedDynamicVariable"]]]:
    """Yield each active string replacement and its current-workspace item variable, if any."""
    for param_name in ("find_replace", "key_value_replace"):
        for param_dict in workspace_obj.environment_parameter.get(param_name, []):
            replace_value = param_dict.get("replace_value")
            if not isinstance(replace_value, dict):
                continue
            processed = process_environment_key(workspace_obj.environment, dict(replace_value))
            env_value = processed.get(workspace_obj.environment)
            if isinstance(env_value, str):
                yield param_dict, env_value, _parse_current_workspace_item(env_value)


def has_unfiltered_items_variable(workspace_obj: "FabricWorkspace") -> bool:
    """Return whether an $items.* variable is unfiltered and requires serial deployment."""
    for param_dict, _env_value, parsed in _iter_dynamic_replace_values(workspace_obj):
        if parsed is None:
            continue
        if not any(param_dict.get(f) for f in ("item_type", "item_name", "file_path")):
            return True

    return False


def get_async_provisioned_dependencies(
    workspace_obj: "FabricWorkspace", publish_item_keys: set[str]
) -> dict[str, set[str]]:
    """
    Map published source items to referenced, asynchronously provisioned attributes.

    Already-deployed items need no tiering and are excluded.
    """
    result: dict[str, set[str]] = {}

    # Find current-workspace references to asynchronously provisioned attributes
    for _param_dict, _env_value, parsed in _iter_dynamic_replace_values(workspace_obj):
        if parsed is None or parsed.attribute not in ASYNC_PROVISIONED_ATTRIBUTES:
            continue

        # Record only source items created in this publish operation
        key = f"{parsed.item_type}.{parsed.item_name}"
        if key in publish_item_keys:
            result.setdefault(key, set()).add(parsed.attribute)

    return result


def build_dynamic_variable_dependency_graph(
    workspace_obj: "FabricWorkspace", publish_item_keys: set[str]
) -> list[tuple[str, str]]:
    """
    Build dependency edges from current-workspace $items.* variables.

    For each replace_value that references an item which is NOT already deployed but IS in the
    current publish set, an edge (referencing_item_key -> referenced_item_key) is added, where
    key format is "ItemType.ItemName".

    Returns:
        A list of dependency edges. An empty list means all dynamic variables are resolvable
        upfront and a single bulk call is sufficient.
    """
    edges: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()

    repository_items = workspace_obj.repository_items
    # Reuse resolved paths and filter matches across parameter entries
    resolved_repo_dir = workspace_obj.repository_directory.resolve() if workspace_obj.repository_directory else None
    path_cache: dict[str, Path] = {}
    referencing_cache: dict[tuple, list[str]] = {}

    for param_dict, _env_value, parsed in _iter_dynamic_replace_values(workspace_obj):
        if parsed is None:
            continue

        ref_type, ref_name = parsed.item_type, parsed.item_name
        ref_key = f"{ref_type}.{ref_name}"

        # Deployed references impose no ordering constraint
        if ref_type in workspace_obj.deployed_items and ref_name in workspace_obj.deployed_items[ref_type]:
            continue

        # Only references created in this batch impose ordering
        if ref_key not in publish_item_keys:
            continue

        # Match parameter filters to referencing items once per filter set
        cache_key = (
            _hashable_filter(param_dict.get("item_type")),
            _hashable_filter(param_dict.get("item_name")),
            _hashable_filter(param_dict.get("file_path")),
        )
        referencing_keys = referencing_cache.get(cache_key)
        if referencing_keys is None:
            referencing_keys = _get_referencing_item_keys(param_dict, repository_items, resolved_repo_dir, path_cache)
            referencing_cache[cache_key] = referencing_keys

        # Add unique in-batch edges, excluding self-references
        for referencing_key in referencing_keys:
            if referencing_key != ref_key and referencing_key in publish_item_keys:
                edge = (referencing_key, ref_key)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    edges.append(edge)

    return edges


def _hashable_filter(value: object) -> object:
    """Normalizes an optional filter value (None, str, or list) to a hashable cache-key component."""
    if isinstance(value, list):
        return tuple(value)
    return value


def _get_referencing_item_keys(
    param_dict: dict,
    repository_items: dict,
    resolved_repo_dir: Optional[Path] = None,
    path_cache: Optional[dict[str, Path]] = None,
) -> list[str]:
    """
    Return item keys matching a parameter entry's type, name, and path filters.

    `resolved_repo_dir` must be resolved. Item paths are resolved lazily and cached.
    """
    filter_type = param_dict.get("item_type")
    filter_name = param_dict.get("item_name")
    filter_paths = process_input_path(resolved_repo_dir, param_dict.get("file_path")) if resolved_repo_dir else None
    # Wildcard matches may be unresolved, unlike explicit paths
    if filter_paths is not None:
        filter_paths = [p.resolve() for p in filter_paths]

    keys = []
    for item_type, items in repository_items.items():
        if filter_type is not None and item_type != filter_type:
            continue
        for item_name, item in items.items():
            if filter_name is not None and item_name != filter_name:
                continue
            if filter_paths is not None:
                item_key = f"{item_type}.{item_name}"
                item_path = path_cache.get(item_key) if path_cache is not None else None
                if item_path is None:
                    item_path = item.path.resolve()
                    if path_cache is not None:
                        path_cache[item_key] = item_path
                if not any(_is_path_in_item(file_path, item_path) for file_path in filter_paths):
                    continue
            keys.append(f"{item_type}.{item_name}")

    return keys


def _is_path_in_item(file_path: Path, item_path: Path) -> bool:
    """Return whether a resolved file path is within a resolved item directory."""
    try:
        file_path.relative_to(item_path)
        return True
    except ValueError:
        return False


def compute_publish_batches(
    items_with_context: list[tuple[str, object, object]],
    dependency_edges: list[tuple[str, str]],
) -> list[list[tuple[str, object, object]]]:
    """
    Compute dependency tiers with Kahn's topological-sort algorithm.

    Dependency-free items enter the first batch. No edges produce one batch.

    Raises:
        InputError: If dependencies contain a cycle.
    """
    if not dependency_edges:
        return [items_with_context]

    # Preserve edge order while deduplicating
    dependency_edges = list(dict.fromkeys(dependency_edges))

    # Index publish contexts by graph key
    item_key_to_context: dict[str, tuple[str, object, object]] = {}
    for item_name, item, publisher in items_with_context:
        key = f"{item.type}.{item_name}"
        item_key_to_context[key] = (item_name, item, publisher)

    publish_item_keys = set(item_key_to_context.keys())
    in_degree: dict[str, int] = {k: 0 for k in publish_item_keys}
    dependents: dict[str, list[str]] = {k: [] for k in publish_item_keys}

    # Build in-degrees and reverse edges for Kahn's algorithm
    for referencing, referenced in dependency_edges:
        if referencing in publish_item_keys and referenced in publish_item_keys:
            in_degree[referencing] = in_degree.get(referencing, 0) + 1
            dependents.setdefault(referenced, []).append(referencing)

    batches: list[list[tuple[str, object, object]]] = []
    current_batch_keys = [k for k, deg in in_degree.items() if deg == 0]

    # Publish each dependency-free tier as one batch
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

    # Unprocessed items belong to a dependency cycle
    if len(processed) < len(publish_item_keys):
        cycle_keys = sorted(publish_item_keys - processed)
        msg = f"Circular dynamic variable dependency detected among: {', '.join(cycle_keys)}"
        raise InputError(msg, logger)

    return batches
