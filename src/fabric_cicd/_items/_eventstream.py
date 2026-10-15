# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Eventstream item."""

import logging

from fabric_cicd import FabricWorkspace, constants
from fabric_cicd._common._item import Item
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import FeatureFlag, ItemType

logger = logging.getLogger(__name__)


def _get_running_sources(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str) -> list[dict]:
    """
    Return every currently running source in the eventstream's topology.

    Args:
        fabric_workspace_obj: The FabricWorkspace object.
        eventstream_guid: The GUID of the deployed eventstream.
    """
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/get-eventstream-topology
    response = fabric_workspace_obj.endpoint.invoke(
        method="GET",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/topology",
    )
    sources = response["body"].get("sources", []) or []
    return [source for source in sources if source.get("status", "").lower() == "running"]


def _pause_source(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str, source: dict) -> None:
    """
    Pause a single eventstream source.

    Args:
        fabric_workspace_obj: The FabricWorkspace object.
        eventstream_guid: The GUID of the deployed eventstream.
        source: The source definition (requires an ``id``, optional ``name``).
    """
    source_name = source.get("name", source["id"])
    logger.info(f"{constants.INDENT}Pausing Eventstream source '{source_name}'")
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/pause-eventstream-source
    fabric_workspace_obj.endpoint.invoke(
        method="POST",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/sources/{source['id']}/pause",
    )


def _resume_source(fabric_workspace_obj: FabricWorkspace, eventstream_guid: str, source: dict) -> None:
    """
    Resume a single eventstream source from where it was last stopped.

    Args:
        fabric_workspace_obj: The FabricWorkspace object.
        eventstream_guid: The GUID of the deployed eventstream.
        source: The source definition (requires an ``id``, optional ``name``).
    """
    source_name = source.get("name", source["id"])
    logger.info(f"{constants.INDENT}Resuming Eventstream source '{source_name}'")
    # https://learn.microsoft.com/en-us/rest/api/fabric/eventstream/topology/resume-eventstream-source
    fabric_workspace_obj.endpoint.invoke(
        method="POST",
        url=f"{fabric_workspace_obj.base_api_url}/eventstreams/{eventstream_guid}/sources/{source['id']}/resume",
        body={"startType": "WhenLastStopped"},
    )


class EventstreamPublisher(ItemPublisher):
    """Publisher for Eventstream items."""

    item_type = ItemType.EVENTSTREAM.value

    def publish_one(self, item_name: str, item: Item) -> None:
        """
        Publish a single Eventstream item.

        By default this behaves exactly like the base publisher. When the
        ``enable_eventstream_source_pause`` feature flag is set and the eventstream is
        already deployed, its running sources are paused before the definition update and
        resumed afterward. This is required when a source is bound to a datasource behind a
        private endpoint, which Fabric otherwise rejects with a DataSourcesValidationError.
        Sources are always resumed via a ``finally`` block so a failed update cannot leave
        them paused.

        Args:
            item_name: The name of the item to publish.
            item: The Item object to publish.
        """
        # A missing GUID means the eventstream has no deployed topology yet (create path),
        # so there are no running sources to pause.
        if FeatureFlag.ENABLE_EVENTSTREAM_SOURCE_PAUSE.value not in constants.FEATURE_FLAG or not item.guid:
            self.fabric_workspace_obj._publish_item(item_name=item_name, item_type=self.item_type)
            return

        paused_sources = []
        try:
            for source in _get_running_sources(self.fabric_workspace_obj, item.guid):
                _pause_source(self.fabric_workspace_obj, item.guid, source)
                paused_sources.append(source)

            self.fabric_workspace_obj._publish_item(item_name=item_name, item_type=self.item_type)
        finally:
            for source in paused_sources:
                _resume_source(self.fabric_workspace_obj, item.guid, source)
