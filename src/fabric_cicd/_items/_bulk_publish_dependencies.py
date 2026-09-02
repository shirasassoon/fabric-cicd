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

if TYPE_CHECKING:
    from fabric_cicd.fabric_workspace import FabricWorkspace

logger = logging.getLogger(__name__)

# Asynchronously provisioned attributes that require waits between dependent publish tiers
# (mirrors constants.PROPERTY_PATH_ATTR_MAPPING, excluding the immediately available "id").
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

    parsed = parse_dynamic_variable(env_value)

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

    Parsing is delegated to the canonical dynamic-variable parser. Every variable is
    validated when the parameter file is loaded (at workspace initialization), so by the
    time bulk publish runs `parse_dynamic_variable` resolves without raising here.
    """
    parsed = _parse_current_workspace_item(env_value)
    if parsed is None:
        return None
    return parsed.item_type, parsed.item_name


def _iter_dynamic_replace_values(
    workspace_obj: "FabricWorkspace",
) -> Iterator[tuple[dict, str, Optional["ParsedDynamicVariable"]]]:
    """
    Yields (param_dict, env_value, parsed) for every find_replace / key_value_replace entry
    whose replace_value resolves to a string for the active environment.

    Each value is parsed exactly once here (single pass), so consumers can reuse `parsed`
    instead of re-parsing. `parsed` is the current-workspace item variable, or None when the
    value is not a current-workspace $items.* reference (plain string or $workspace.* variable).
    """
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
    """
    Returns True if any find_replace or key_value_replace entry uses a current-workspace
    $items.* variable in replace_value without any item_type, item_name, or file_path filter.

    When this is the case, dependency scope cannot be narrowed and bulk publish would treat
    all items as dependents of the referenced item, so callers should fall back to standard
    (serial) deployment instead.
    """
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
    Builds a dependency graph from current-workspace $items.* variables in the parameter file.

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
    # Resolve the repository root once; reused for every file_path filter below.
    resolved_repo_dir = workspace_obj.repository_directory.resolve() if workspace_obj.repository_directory else None
    # Lazily memoize each item's resolved path (only touched when a file_path filter is present).
    path_cache: dict[str, Path] = {}
    # Cache referencing-item lookups by their filter signature; identical filters reuse the result.
    referencing_cache: dict[tuple, list[str]] = {}

    for param_dict, _env_value, parsed in _iter_dynamic_replace_values(workspace_obj):
        if parsed is None:
            continue

        ref_type, ref_name = parsed.item_type, parsed.item_name
        ref_key = f"{ref_type}.{ref_name}"

        # Already deployed -> resolvable immediately, no ordering constraint
        if ref_type in workspace_obj.deployed_items and ref_name in workspace_obj.deployed_items[ref_type]:
            continue

        # Only items new in this batch impose ordering
        if ref_key not in publish_item_keys:
            continue

        cache_key = (
            param_dict.get("item_type"),
            _hashable_filter(param_dict.get("item_name")),
            _hashable_filter(param_dict.get("file_path")),
        )
        referencing_keys = referencing_cache.get(cache_key)
        if referencing_keys is None:
            referencing_keys = _get_referencing_item_keys(param_dict, repository_items, resolved_repo_dir, path_cache)
            referencing_cache[cache_key] = referencing_keys

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
    Determines which items a parameter entry applies to based on item_type/item_name/file_path filters.

    `resolved_repo_dir` must already be resolved by the caller. Item paths are resolved lazily and only
    when a file_path filter is present, memoized in `path_cache` to avoid repeated filesystem syscalls.

    Returns:
        A list of item keys ("ItemType.ItemName") that this parameter applies to.
    """
    # Normalize the parameter entry's optional filters
    filter_type = param_dict.get("item_type")
    filter_name = param_dict.get("item_name")
    filter_paths = process_input_path(resolved_repo_dir, param_dict.get("file_path")) if resolved_repo_dir else None

    # Collect repository items that satisfy every specified filter
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
    """
    Returns True when file_path is contained by the repository item's directory.

    Both arguments are expected to be already-resolved absolute paths (filter paths come pre-resolved
    from process_input_path; item paths are resolved by the caller), so no resolve() is done here.
    """
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
    Computes publish batches from a dependency graph using topological sort (Kahn's algorithm).

    Items with no dependencies (or whose dependencies are already deployed) go into Batch 0;
    items depending on Batch 0 go into Batch 1, and so on. No edges -> a single batch.

    Raises:
        InputError: If a circular dependency is detected.
    """
    if not dependency_edges:
        return [items_with_context]

    # Defensively dedupe edges (order-preserving) so in-degree counts are not inflated by duplicates.
    dependency_edges = list(dict.fromkeys(dependency_edges))

    # Index publish contexts by their dependency-graph keys
    item_key_to_context: dict[str, tuple[str, object, object]] = {}
    for item_name, item, publisher in items_with_context:
        key = f"{item.type}.{item_name}"
        item_key_to_context[key] = (item_name, item, publisher)

    # Build in-degrees and reverse edges for Kahn's algorithm
    publish_item_keys = set(item_key_to_context.keys())
    in_degree: dict[str, int] = {k: 0 for k in publish_item_keys}
    dependents: dict[str, list[str]] = {k: [] for k in publish_item_keys}

    for referencing, referenced in dependency_edges:
        if referencing in publish_item_keys and referenced in publish_item_keys:
            in_degree[referencing] = in_degree.get(referencing, 0) + 1
            dependents.setdefault(referenced, []).append(referencing)

    batches: list[list[tuple[str, object, object]]] = []
    current_batch_keys = [k for k, deg in in_degree.items() if deg == 0]

    # Process each dependency-free tier as one publish batch
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

    # Unprocessed items belong to at least one dependency cycle
    if len(processed) < len(publish_item_keys):
        cycle_keys = sorted(publish_item_keys - processed)
        msg = f"Circular dynamic variable dependency detected among: {', '.join(cycle_keys)}"
        raise InputError(msg, logger)

    return batches
