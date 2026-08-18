# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy OrgAppAudience item."""

from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import ItemType


class OrgAppAudiencePublisher(ItemPublisher):
    """Publisher for OrgAppAudience items."""

    item_type = ItemType.ORG_APP_AUDIENCE.value
