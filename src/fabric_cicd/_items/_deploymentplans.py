# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Deployment Plan item."""

import logging
from collections.abc import Sequence
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
) -> dict[str, object]:
    """Return the logical-ID plan option, or no options when no plan is selected."""
    if deployment_plan is None:
        return {}

    plan = next(
        (
            item
            for name, item, _ in items_with_context
            if item.type == ItemType.DEPLOYMENT_PLAN.value and name == deployment_plan
        ),
        None,
    )
    if plan is None:
        msg = f"Deployment Plan '{deployment_plan}' must be included in the bulk publish batch."
        raise InputError(msg, logger)
    if not plan.logical_id:
        msg = f"Error with Deployment Plan '{plan.name}'."
        raise InputError(msg, logger)
    return {
        "deploymentPlan": {"logicalId": plan.logical_id, "referenceType": "ByLogicalId"},
    }
