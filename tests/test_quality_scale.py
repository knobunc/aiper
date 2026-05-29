"""Tests that verify quality scale claims are structurally true.

These tests parse quality_scale.yaml and confirm the codebase actually
satisfies the rules marked as 'done'. If a rule regresses (e.g.
PARALLEL_UPDATES is removed), the corresponding test fails.
"""

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "aiper"
QUALITY_SCALE = INTEGRATION / "quality_scale.yaml"

PLATFORM_FILES = ["sensor.py", "binary_sensor.py", "switch.py"]


def _load_rules() -> dict:
    with open(QUALITY_SCALE) as f:
        return yaml.safe_load(f)["rules"]


def _rule_status(rules: dict, name: str) -> str:
    val = rules.get(name)
    if isinstance(val, dict):
        return val["status"]
    return val or "todo"


def _parse_module(filename: str) -> ast.Module:
    return ast.parse((INTEGRATION / filename).read_text())


def _has_top_level_assign(tree: ast.Module, name: str) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
    return False


def _has_class_method(tree: ast.Module, cls: str, method: str) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == method:
                        return True
    return False


def _has_function(tree: ast.Module, name: str) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return True
    return False


class TestBronzeRules:
    def test_config_flow_exists(self):
        rules = _load_rules()
        assert _rule_status(rules, "config-flow") == "done"
        tree = _parse_module("config_flow.py")
        assert _has_class_method(tree, "AiperConfigFlow", "async_step_user")
        assert _has_class_method(
            tree, "AiperConfigFlow", "async_step_bluetooth"
        )

    def test_unique_config_entry(self):
        rules = _load_rules()
        assert _rule_status(rules, "unique-config-entry") == "done"
        source = (INTEGRATION / "config_flow.py").read_text()
        assert "_abort_if_unique_id_configured" in source

    def test_has_entity_name(self):
        rules = _load_rules()
        assert _rule_status(rules, "has-entity-name") == "done"
        source = (INTEGRATION / "entity.py").read_text()
        assert "_attr_has_entity_name = True" in source

    def test_entity_unique_id(self):
        rules = _load_rules()
        assert _rule_status(rules, "entity-unique-id") == "done"
        for pf in PLATFORM_FILES:
            source = (INTEGRATION / pf).read_text()
            assert "_attr_unique_id" in source, f"{pf} missing unique_id"

    def test_runtime_data(self):
        rules = _load_rules()
        assert _rule_status(rules, "runtime-data") == "done"
        source = (INTEGRATION / "__init__.py").read_text()
        assert "runtime_data" in source

    def test_test_before_configure(self):
        rules = _load_rules()
        assert _rule_status(rules, "test-before-configure") == "done"
        source = (INTEGRATION / "config_flow.py").read_text()
        assert "BleakClient" in source
        assert "cannot_connect" in source

    def test_test_before_setup(self):
        rules = _load_rules()
        assert _rule_status(rules, "test-before-setup") == "done"
        source = (INTEGRATION / "__init__.py").read_text()
        assert "async_config_entry_first_refresh" in source

    def test_common_modules(self):
        rules = _load_rules()
        assert _rule_status(rules, "common-modules") == "done"
        source = (INTEGRATION / "coordinator.py").read_text()
        assert "DataUpdateCoordinator" in source

    def test_appropriate_polling(self):
        rules = _load_rules()
        assert _rule_status(rules, "appropriate-polling") == "done"
        source = (INTEGRATION / "coordinator.py").read_text()
        assert "update_interval" in source


class TestSilverRules:
    def test_parallel_updates(self):
        rules = _load_rules()
        assert _rule_status(rules, "parallel-updates") == "done"
        for pf in PLATFORM_FILES:
            tree = _parse_module(pf)
            assert _has_top_level_assign(
                tree, "PARALLEL_UPDATES"
            ), f"{pf} missing PARALLEL_UPDATES"

    def test_config_entry_unloading(self):
        rules = _load_rules()
        assert _rule_status(rules, "config-entry-unloading") == "done"
        tree = _parse_module("__init__.py")
        assert _has_function(tree, "async_unload_entry")

    def test_reauthentication_flow(self):
        rules = _load_rules()
        assert _rule_status(rules, "reauthentication-flow") == "done"
        tree = _parse_module("config_flow.py")
        assert _has_class_method(
            tree, "AiperConfigFlow", "async_step_reauth"
        )
        assert _has_class_method(
            tree, "AiperConfigFlow", "async_step_reauth_confirm"
        )

    def test_action_exceptions(self):
        rules = _load_rules()
        assert _rule_status(rules, "action-exceptions") == "done"
        source = (INTEGRATION / "__init__.py").read_text()
        assert "ServiceValidationError" in source
        source = (INTEGRATION / "coordinator.py").read_text()
        assert "HomeAssistantError" in source

    def test_log_when_unavailable(self):
        rules = _load_rules()
        assert _rule_status(rules, "log-when-unavailable") == "done"
        source = (INTEGRATION / "coordinator.py").read_text()
        assert "is unavailable" in source
        assert "is available" in source

    def test_entity_unavailable(self):
        rules = _load_rules()
        assert _rule_status(rules, "entity-unavailable") == "done"
        source = (INTEGRATION / "coordinator.py").read_text()
        assert "self._state.available = False" in source
        assert "self._state.available = True" in source

    def test_integration_owner(self):
        rules = _load_rules()
        assert _rule_status(rules, "integration-owner") == "done"
        manifest = yaml.safe_load(
            (INTEGRATION / "manifest.json").read_text()
                .replace("true", "True").replace("false", "False")
        )
        assert manifest.get("codeowners")

    def test_test_coverage(self):
        rules = _load_rules()
        assert _rule_status(rules, "test-coverage") == "done"
        test_dir = ROOT / "tests"
        test_files = list(test_dir.glob("test_*.py"))
        assert len(test_files) >= 4


class TestGoldRules:
    def test_entity_category(self):
        rules = _load_rules()
        assert _rule_status(rules, "entity-category") == "done"
        source = (INTEGRATION / "sensor.py").read_text()
        assert "EntityCategory.DIAGNOSTIC" in source

    def test_entity_device_class(self):
        rules = _load_rules()
        assert _rule_status(rules, "entity-device-class") == "done"
        sensor_src = (INTEGRATION / "sensor.py").read_text()
        assert "SensorDeviceClass" in sensor_src
        binary_src = (INTEGRATION / "binary_sensor.py").read_text()
        assert "BinarySensorDeviceClass" in binary_src

    def test_entity_translations(self):
        rules = _load_rules()
        assert _rule_status(rules, "entity-translations") == "done"
        source = (INTEGRATION / "sensor.py").read_text()
        assert "translation_key" in source

    def test_discovery(self):
        rules = _load_rules()
        assert _rule_status(rules, "discovery") == "done"
        import json
        manifest = json.loads(
            (INTEGRATION / "manifest.json").read_text()
        )
        assert "bluetooth" in manifest


class TestPlatinumRules:
    def test_async_dependency(self):
        rules = _load_rules()
        assert _rule_status(rules, "async-dependency") == "done"
        import json
        manifest = json.loads(
            (INTEGRATION / "manifest.json").read_text()
        )
        assert manifest.get("requirements") == []

    def test_inject_websession_exempt(self):
        rules = _load_rules()
        assert _rule_status(rules, "inject-websession") == "exempt"


class TestQualityScaleIntegrity:
    """Verify the quality_scale.yaml file itself is complete."""

    BRONZE_RULES = {
        "action-setup", "appropriate-polling", "brands",
        "common-modules", "config-flow-test-coverage", "config-flow",
        "dependency-transparency", "docs-actions",
        "docs-high-level-description", "docs-installation-instructions",
        "docs-removal-instructions", "entity-event-setup",
        "entity-unique-id", "has-entity-name", "runtime-data",
        "test-before-configure", "test-before-setup",
        "unique-config-entry",
    }

    SILVER_RULES = {
        "action-exceptions", "config-entry-unloading",
        "docs-configuration-parameters", "docs-installation-parameters",
        "entity-unavailable", "integration-owner",
        "log-when-unavailable", "parallel-updates",
        "reauthentication-flow", "test-coverage",
    }

    GOLD_RULES = {
        "devices", "diagnostics", "discovery-update-info", "discovery",
        "docs-data-update", "docs-examples", "docs-known-limitations",
        "docs-supported-devices", "docs-supported-functions",
        "docs-troubleshooting", "docs-use-cases", "dynamic-devices",
        "entity-category", "entity-device-class",
        "entity-disabled-by-default", "entity-translations",
        "exception-translations", "icon-translations",
        "reconfiguration-flow", "repair-issues", "stale-devices",
    }

    PLATINUM_RULES = {
        "async-dependency", "inject-websession", "strict-typing",
    }

    ALL_RULES = BRONZE_RULES | SILVER_RULES | GOLD_RULES | PLATINUM_RULES

    def test_all_rules_present(self):
        rules = _load_rules()
        missing = self.ALL_RULES - set(rules.keys())
        assert not missing, f"Missing rules: {missing}"

    def test_no_unknown_rules(self):
        rules = _load_rules()
        unknown = set(rules.keys()) - self.ALL_RULES
        assert not unknown, f"Unknown rules: {unknown}"

    def test_all_statuses_valid(self):
        rules = _load_rules()
        for name, val in rules.items():
            status = val["status"] if isinstance(val, dict) else val
            assert status in (
                "done", "todo", "exempt"
            ), f"{name}: invalid status '{status}'"

    def test_exempt_rules_have_comments(self):
        rules = _load_rules()
        for name, val in rules.items():
            if isinstance(val, dict) and val["status"] == "exempt":
                assert val.get(
                    "comment"
                ), f"{name}: exempt without comment"
