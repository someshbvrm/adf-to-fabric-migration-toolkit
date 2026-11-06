import json

import pytest

from adf2fabric.loader import load_factory, resource_name


def test_resource_name_parses_arm_expression():
    assert resource_name("[concat(parameters('factoryName'), '/pl_load')]") == "pl_load"
    assert resource_name("factory/pl_plain") == "pl_plain"


def test_arm_template_loads_every_object_type(factory):
    assert factory.name == "adf-contoso-retail-prod"
    assert factory.counts() == {
        "pipelines": 7,
        "datasets": 6,
        "linked_services": 6,
        "triggers": 3,
        "integration_runtimes": 2,
        "dataflows": 1,
    }


def test_git_folder_layout(tmp_path):
    (tmp_path / "pipeline").mkdir()
    (tmp_path / "linkedService").mkdir()
    (tmp_path / "pipeline" / "pl_a.json").write_text(
        json.dumps({"name": "pl_a", "properties": {"activities": [{"name": "w", "type": "Wait"}]}})
    )
    (tmp_path / "linkedService" / "ls.json").write_text(
        json.dumps({"name": "ls_sql", "properties": {"type": "AzureSqlDatabase"}})
    )
    f = load_factory(tmp_path)
    assert list(f.pipelines) == ["pl_a"]
    assert f.linked_services["ls_sql"]["type"] == "AzureSqlDatabase"


def test_unknown_input_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_factory(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_factory(tmp_path / "missing.json")
