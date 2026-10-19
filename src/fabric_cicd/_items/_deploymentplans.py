# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Deployment Plan item."""

from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import ItemType


class DeploymentPlanPublisher(ItemPublisher):
    """Publisher for Deployment Plan items."""

    item_type = ItemType.DEPLOYMENT_PLAN.value
