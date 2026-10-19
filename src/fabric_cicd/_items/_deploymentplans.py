# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Deployment Plan item."""

import logging

from fabric_cicd import FabricWorkspace
from fabric_cicd._common._exceptions import ParsingError
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import ItemType

logger = logging.getLogger(__name__)


class DeploymentPlanPublisher(ItemPublisher):
    """Publisher for Deployment Plan items."""

    item_type = ItemType.DEPLOYMENT_PLAN.value


def apply_deployment_plan(fabric_workspace_obj: FabricWorkspace, plan_name: str) -> str:
    """Return the specified repository deployment plan's GUID, requiring it to be deployed."""
    plan = fabric_workspace_obj.repository_items.get(ItemType.DEPLOYMENT_PLAN.value, {}).get(plan_name)
    if plan is None:
        msg = f"Cannot find Deployment Plan '{plan_name}' in the repository."
        raise ParsingError(msg, logger)
    if not plan.guid:
        msg = f"Cannot use Deployment Plan '{plan_name}' as it is not yet deployed."
        raise ParsingError(msg, logger)
    return plan.guid
