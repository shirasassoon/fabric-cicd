# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for deployment plan lookup."""

from unittest.mock import MagicMock

import pytest

from fabric_cicd import FabricWorkspace, ItemType
from fabric_cicd._common._exceptions import ParsingError
from fabric_cicd._common._item import Item
from fabric_cicd._items._deploymentplans import apply_deployment_plan


def test_apply_deployment_plan_returns_deployed_guid():
    workspace = MagicMock(spec=FabricWorkspace)
    plan = Item(ItemType.DEPLOYMENT_PLAN.value, "Plan", "", "deployed-guid", logical_id="logical-id")
    workspace.repository_items = {ItemType.DEPLOYMENT_PLAN.value: {"Plan": plan}}

    assert apply_deployment_plan(workspace, "Plan") == "deployed-guid"


@pytest.mark.parametrize(
    "repository_items",
    [
        {},
        {ItemType.DEPLOYMENT_PLAN.value: {}},
        {ItemType.NOTEBOOK.value: {"Plan": Item(ItemType.NOTEBOOK.value, "Plan", "", "notebook-guid")}},
    ],
)
def test_apply_deployment_plan_rejects_missing_plan(repository_items):
    workspace = MagicMock(spec=FabricWorkspace)
    workspace.repository_items = repository_items

    with pytest.raises(ParsingError, match="Cannot find Deployment Plan 'Plan' in the repository"):
        apply_deployment_plan(workspace, "Plan")


def test_apply_deployment_plan_rejects_undeployed_plan():
    workspace = MagicMock(spec=FabricWorkspace)
    plan = Item(ItemType.DEPLOYMENT_PLAN.value, "Plan", "", "", logical_id="logical-id")
    workspace.repository_items = {ItemType.DEPLOYMENT_PLAN.value: {"Plan": plan}}

    with pytest.raises(ParsingError, match="not yet deployed"):
        apply_deployment_plan(workspace, "Plan")
