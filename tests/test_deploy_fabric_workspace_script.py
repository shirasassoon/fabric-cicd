from importlib import util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / ".deploy" / "deploy_fabric_workspace.py"


@pytest.fixture
def deploy_module():
    spec = util.spec_from_file_location("deploy_fabric_workspace_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script_main(deploy_module, monkeypatch, mocker, actions_step_debug):
    monkeypatch.setenv("FABRIC_WORKSPACE_ID", "workspace-id")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/repo")
    monkeypatch.setenv("ENVIRONMENT", "PROD")

    if actions_step_debug is None:
        monkeypatch.delenv("ACTIONS_STEP_DEBUG", raising=False)
    else:
        monkeypatch.setenv("ACTIONS_STEP_DEBUG", actions_step_debug)

    change_log_level_mock = mocker.patch.object(deploy_module, "change_log_level")
    mocker.patch.object(deploy_module, "AzureCliCredential", return_value=object())
    mocker.patch.object(deploy_module, "FabricWorkspace", return_value=object())
    mocker.patch.object(deploy_module, "publish_all_items")
    mocker.patch.object(deploy_module, "unpublish_all_orphan_items")

    deploy_module.main()
    return change_log_level_mock


@pytest.mark.parametrize("actions_step_debug", ["true", "1"])
def test_main_enables_debug_logging_for_supported_actions_step_debug_values(
    deploy_module, monkeypatch, mocker, actions_step_debug
):
    change_log_level_mock = _run_script_main(deploy_module, monkeypatch, mocker, actions_step_debug)

    change_log_level_mock.assert_called_once_with("DEBUG")


def test_main_does_not_enable_debug_logging_when_actions_step_debug_is_unset(deploy_module, monkeypatch, mocker):
    change_log_level_mock = _run_script_main(deploy_module, monkeypatch, mocker, None)

    change_log_level_mock.assert_not_called()
