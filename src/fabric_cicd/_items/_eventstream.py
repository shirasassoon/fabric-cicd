# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Eventstream item."""

import logging
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from fabric_cicd import FabricWorkspace, constants
from fabric_cicd._common._item import Item
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import FeatureFlag, ItemType

logger = logging.getLogger(__name__)


def _get_running_sources(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str) -> list[dict]:
    """Return every currently running source in the eventstream's topology."""
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/get-eventstream-topology
    response = fabric_workspace_obj.endpoint.invoke(
        method="GET",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/topology",
    )
    sources = response["body"].get("sources", []) or []
    return [source for source in sources if source.get("status", "").lower() == "running"]


def _pause_source(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str, source: dict) -> None:
    """Pause a single eventstream source."""
    source_name = source.get("name", source["id"])
    logger.info(f"{constants.INDENT}Pausing Eventstream source '{source_name}'")
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/pause-eventstream-source
    fabric_workspace_obj.endpoint.invoke(
        method="POST",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/sources/{source['id']}/pause",
    )


def _resume_source(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str, source: dict) -> None:
    """Resume a single eventstream source from where it was last stopped."""
    source_name = source.get("name", source["id"])
    logger.info(f"{constants.INDENT}Resuming Eventstream source '{source_name}'")
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/resume-eventstream-source
    fabric_workspace_obj.endpoint.invoke(
        method="POST",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/sources/{source['id']}/resume",
        body={"startType": "WhenLastStopped"},
    )


@contextmanager
def _paused_eventstream_sources(fabric_workspace_obj: FabricWorkspace, items: list[Item]) -> Iterator[None]:
    """
    Pause the running sources of the given deployed eventstreams for the duration of the publish, then resume them.

    This is the single source of truth for the pause/resume flow, shared by the single-item
    (publish_one) and bulk (publish_batch_context) publish paths. It is a no-op unless the
    enable_eventstream_source_pause feature flag is set. Eventstreams that are not yet deployed
    (no GUID) are skipped, as they have no running sources. Sources are always resumed via a
    finally block, so a failed publish can never leave them paused.

    Args:
        fabric_workspace_obj: The FabricWorkspace object.
        items: The eventstream Item objects being published.
    """
    paused_sources = []  # list of (eventstream_guid, source) tuples
    try:
        if FeatureFlag.ENABLE_EVENTSTREAM_SOURCE_PAUSE.value in constants.FEATURE_FLAG:
            for item in items:
                if not item.guid:
                    continue
                for source in _get_running_sources(fabric_workspace_obj, item.guid):
                    _pause_source(fabric_workspace_obj, item.guid, source)
                    paused_sources.append((item.guid, source))
        yield
    finally:
        for eventstream_guid, source in paused_sources:
            _resume_source(fabric_workspace_obj, eventstream_guid, source)


class EventstreamPublisher(ItemPublisher):
    """Publisher for Eventstream items."""

    item_type = ItemType.EVENTSTREAM.value

    def publish_one(self, item_name: str, item: Item) -> None:
        """Publish a single Eventstream item, pausing its running sources when the feature flag is set."""
        with _paused_eventstream_sources(self.fabric_workspace_obj, [item]):
            self.fabric_workspace_obj._publish_item(item_name=item_name, item_type=self.item_type)

    def publish_batch_context(self, items: list[Item]) -> AbstractContextManager[None]:
        """Pause/resume the batch's eventstream sources around the bulk publish (see _paused_eventstream_sources)."""
        return _paused_eventstream_sources(self.fabric_workspace_obj, items)
