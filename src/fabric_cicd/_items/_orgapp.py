# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy OrgApp item."""

from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import ItemType


class OrgAppPublisher(ItemPublisher):
    """Publisher for OrgApp items.

    OrgApp is published as a shell only (metadata, no definition). The item
    definition references packaged content by element IDs that are not remapped
    to the target workspace, which results in a blank Org App after deployment.
    Publishing only the shell avoids deploying that broken content; the Org App
    content must be configured manually in the target workspace.
    """

    item_type = ItemType.ORG_APP.value
