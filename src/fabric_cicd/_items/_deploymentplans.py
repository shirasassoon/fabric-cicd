# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Deployment Plan item."""

import logging
from collections.abc import Mapping, Sequence
from typing import Optional

from fabric_cicd._common._exceptions import InputError
from fabric_cicd._common._item import Item
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import ItemType

logger = logging.getLogger(__name__)


class DeploymentPlanPublisher(ItemPublisher):
    """Publisher for Deployment Plan items."""

    item_type = ItemType.DEPLOYMENT_PLAN.value


def set_deployment_plan(
    deployment_plan: Optional[str],
    items_with_context: Sequence[tuple[str, Item, object]],
    repository_items: Mapping[str, Mapping[str, Item]],
    deployed_items: Mapping[str, Mapping[str, Item]],
) -> dict[str, object]:
    """
    Sets the deployment plan to be used by the bulk publish operation.

    Args:
        deployment_plan: The name of the repository deployment plan to use, if provided.
        items_with_context: A sequence of tuples containing item names, Item objects, and additional context.
        repository_items: Repository items by type and name, including items outside the publish batch.
        deployed_items: Target workspace items by type and name.

    Returns:
        A dictionary containing the repository plan's logical ID, or an empty dictionary if no plan is selected.

    """
    if deployment_plan is None:
        return {}

    repository_plan = repository_items.get(ItemType.DEPLOYMENT_PLAN.value, {}).get(deployment_plan)
    if repository_plan is None:
        msg = f"Deployment Plan '{deployment_plan}' must exist in the repository to be executed in the deployment"
        raise InputError(msg, logger)
    if not repository_plan.logical_id.strip():
        msg = f"Cannot retrieve a logical ID for Deployment Plan '{deployment_plan}' from the repository"
        raise InputError(msg, logger)

    in_publish_batch = any(
        item.type == ItemType.DEPLOYMENT_PLAN.value and name == deployment_plan for name, item, _ in items_with_context
    )
    if not in_publish_batch:
        deployed_plan = deployed_items.get(ItemType.DEPLOYMENT_PLAN.value, {}).get(deployment_plan)
        if deployed_plan is None:
            msg = (
                f"Deployment Plan '{deployment_plan}' must be included in the bulk publish batch "
                "or already exist in the target workspace to be executed in the deployment"
            )
            raise InputError(msg, logger)

    return {
        "deploymentPlan": {"logicalId": repository_plan.logical_id, "referenceType": "ByLogicalId"},
    }
