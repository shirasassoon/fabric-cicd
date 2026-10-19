# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for bulk deployment plan options."""

from unittest.mock import MagicMock

import pytest

from fabric_cicd import FabricWorkspace, ItemType
from fabric_cicd._common._exceptions import InputError
from fabric_cicd._common._item import Item
from fabric_cicd._items._deploymentplans import DeploymentPlanPublisher


def make_workspace():
    workspace = MagicMock(spec=FabricWorkspace)
    workspace._prepare_bulk_item_parts.return_value = []
    workspace.endpoint = MagicMock()
    workspace.endpoint.invoke.return_value = {"body": {}}
    workspace.base_api_url = "https://example.test/workspaces/workspace"
    return workspace


def make_plan(name="Plan", logical_id="00000000-0000-0000-0000-000000000000"):
    return Item(ItemType.DEPLOYMENT_PLAN.value, name, "", "", logical_id=logical_id)


def test_bulk_publish_uses_top_level_plan_logical_id():
    workspace = make_workspace()
    plan = make_plan()
    publisher = DeploymentPlanPublisher(workspace)

    FabricWorkspace._publish_items(workspace, [(plan.name, plan, publisher)])

    assert workspace.endpoint.invoke.call_args.kwargs["body"]["options"] == {
        "allowPairingByName": False,
        "deploymentPlan": {"logicalId": plan.logical_id, "referenceType": "ByLogicalId"},
    }


def test_bulk_publish_without_plan_preserves_pairing_by_name():
    workspace = make_workspace()
    FabricWorkspace._publish_items(workspace, [])

    assert workspace.endpoint.invoke.call_args.kwargs["body"]["options"] == {"allowPairingByName": True}


def test_bulk_publish_preserves_per_item_options_with_plan():
    workspace = make_workspace()
    plan = make_plan()
    model = Item(ItemType.SEMANTIC_MODEL.value, "Model", "", "", logical_id="model-id")
    model_publisher = MagicMock()
    model_publisher.get_definition_options.return_value = {"allowPurgeData": True}

    FabricWorkspace._publish_items(
        workspace,
        [(plan.name, plan, DeploymentPlanPublisher(workspace)), (model.name, model, model_publisher)],
    )

    assert workspace.endpoint.invoke.call_args.kwargs["body"]["options"] == {
        "allowPairingByName": False,
        "deploymentPlan": {"logicalId": plan.logical_id, "referenceType": "ByLogicalId"},
        "itemOptionsByLogicalId": [{"logicalId": "model-id", "options": {"allowPurgeData": True}}],
    }


@pytest.mark.parametrize(
    ("plans", "message"),
    [
        ([make_plan(), make_plan("Second")], "Only one Deployment Plan"),
        ([make_plan(logical_id="")], "must have a logical ID"),
    ],
)
def test_bulk_publish_rejects_invalid_plans_before_request(plans, message):
    workspace = make_workspace()
    batch = [(plan.name, plan, DeploymentPlanPublisher(workspace)) for plan in plans]

    with pytest.raises(InputError, match=message):
        FabricWorkspace._publish_items(workspace, batch)

    workspace.endpoint.invoke.assert_not_called()
