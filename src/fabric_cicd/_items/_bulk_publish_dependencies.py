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
from fabric_cicd.constants import ASYNC_PROVISIONED_ATTRIBUTES, DEFAULT_GUID

if TYPE_CHECKING:
    from fabric_cicd.fabric_workspace import FabricWorkspace

logger = logging.getLogger(__name__)


def has_unfiltered_items_variable(workspace_obj: "FabricWorkspace") -> bool:
    """Return whether an $items.* variable is unfiltered and requires serial deployment."""
    for param_dict, _env_value, parsed in _iter_dynamic_replace_values(workspace_obj):
        if parsed is None:
            continue
        if not any(param_dict.get(f) for f in ("item_type", "item_name", "file_path")):
            return True

    return False


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


def _parse_current_workspace_item(env_value: str) -> Optional["ParsedDynamicVariable"]:
    """Parse a current-workspace $items.* variable, or return None."""
    if not env_value.startswith("$"):
        return None

    parsed = parse_dynamic_variable(env_value)

    if parsed.kind == "item" and parsed.workspace_name is None:
        return parsed

    return None


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


def build_logical_reference_edges(
    items_with_context: list[tuple[str, object, object]],
) -> list[tuple[str, str]]:
    """
    Find logical-ID references that require items to publish in the same bulk request.

    Returns:
        Ordered, unique co-location edges between published items.
    """
    # Map each publishable item's logical ID to its graph key
    logical_id_to_key: dict[str, str] = {}
    for item_name, item, _publisher in items_with_context:
        logical_id = getattr(item, "logical_id", "") or ""
        if logical_id and logical_id != DEFAULT_GUID:
            logical_id_to_key[logical_id] = f"{item.type}.{item_name}"

    # A reference requires at least two distinct logical IDs to relate
    if len(logical_id_to_key) < 2:
        return []

    edges: dict[tuple[str, str], None] = {}
    for item_name, item, _publisher in items_with_context:
        key = f"{item.type}.{item_name}"
        # Scan the item's text definition content for other items' logical IDs
        content = "\n".join(
            file.contents
            for file in getattr(item, "item_files", [])
            if getattr(file, "type", None) == "text" and isinstance(getattr(file, "contents", None), str)
        )
        if not content:
            continue

        for logical_id, referenced_key in logical_id_to_key.items():
            if referenced_key != key and logical_id in content:
                edge = (key, referenced_key) if key < referenced_key else (referenced_key, key)
                edges.setdefault(edge, None)

    return list(edges)


def compute_publish_batches(
    items_with_context: list[tuple[str, object, object]],
    dependency_edges: list[tuple[str, str]],
    colocation_edges: list[tuple[str, str]] = (),
) -> list[list[tuple[str, object, object]]]:
    """
    Compute dependency tiers with Kahn's topological-sort algorithm.

    Items connected by `colocation_edges` (logical-ID references) are contracted into a single
    co-publish group that ships in one batch. Dependency (dynamic-variable) ordering is then
    applied between groups: dependency-free groups enter the first batch. With no edges of either
    kind the result is a single batch.

    Raises:
        InputError: If dependencies contain a cycle, or a dynamic-variable dependency exists
            between two items forced into the same batch by a logical-ID reference.
    """
    # Return a single batch if there are no dependency or colocation edges to consider
    if not dependency_edges and not colocation_edges:
        return [items_with_context]

    item_key_to_context: dict[str, tuple[str, object, object]] = {}
    ordered_keys: list[str] = []

    for item_name, item, publisher in items_with_context:
        key = f"{item.type}.{item_name}"
        # Keep the publish data accessible after the graph is reduced to string keys
        item_key_to_context[key] = (item_name, item, publisher)
        # Preserve input order so items and batches are returned deterministically
        ordered_keys.append(key)
    # Store each key's input position so groups and batches can be sorted in the same order
    key_index = {key: index for index, key in enumerate(ordered_keys)}
    # Use a set to quickly skip edges that include an item not being published
    publish_item_keys = set(item_key_to_context)

    # Union-Find to contract co-located items into groups that must publish together
    parent = {key: key for key in ordered_keys}

    def find(node: str) -> str:
        # Resolve the co-location group and compress its path to speed up later lookups
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    def union(node_a: str, node_b: str) -> None:
        # Merge co-location groups under the earliest item to keep batch order deterministic
        root_a, root_b = find(node_a), find(node_b)
        if root_a == root_b:
            return
        if key_index[root_a] <= key_index[root_b]:
            parent[root_b] = root_a
        else:
            parent[root_a] = root_b

    for node_a, node_b in colocation_edges:
        # Merge the groups only when both items are being published
        if node_a in publish_item_keys and node_b in publish_item_keys:
            union(node_a, node_b)

    # Collect items with the same root key into one publish group, preserving input order
    groups: dict[str, list[str]] = {}
    for key in ordered_keys:
        groups.setdefault(find(key), []).append(key)

    # Lift dependency edges to the group level for Kahn's algorithm
    in_degree: dict[str, int] = {rep: 0 for rep in groups}
    dependents: dict[str, list[str]] = {rep: [] for rep in groups}
    seen_group_edges: set[tuple[str, str]] = set()
    for referencing, referenced in dependency_edges:
        if referencing not in publish_item_keys or referenced not in publish_item_keys:
            continue
        group_referencing, group_referenced = find(referencing), find(referenced)
        # Raise an error if a dependency exists within the same group, as it conflicts with co-location
        if group_referencing == group_referenced:
            conflict = ", ".join(sorted(groups[group_referencing]))
            msg = (
                f"Cannot bulk publish {conflict}: a logical-ID reference requires the items in one batch, "
                f"but a dynamic variable requires separate batches. Use serial publishing instead."
            )
            raise InputError(msg, logger)
        # Otherwise, record the edge between groups for topological sorting
        edge = (group_referencing, group_referenced)
        if edge not in seen_group_edges:
            seen_group_edges.add(edge)
            in_degree[group_referencing] += 1
            dependents[group_referenced].append(group_referencing)

    batches: list[list[tuple[str, object, object]]] = []
    current_reps = sorted((rep for rep, deg in in_degree.items() if deg == 0), key=lambda rep: key_index[rep])

    # Publish each dependency-free tier of groups as one batch
    processed: set[str] = set()
    while current_reps:
        batch = []
        next_reps = []
        for rep in current_reps:
            processed.add(rep)
            for member in groups[rep]:
                batch.append(item_key_to_context[member])
            for dependent in dependents[rep]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_reps.append(dependent)

        batches.append(batch)
        current_reps = sorted(next_reps, key=lambda rep: key_index[rep])

    # Unprocessed groups belong to a dependency cycle
    if len(processed) < len(groups):
        cycle_keys = sorted(member for rep in (set(groups) - processed) for member in groups[rep])
        msg = f"Circular dynamic variable dependency detected among: {', '.join(cycle_keys)}"
        raise InputError(msg, logger)

    return batches
