import json

from adf2fabric.convert import apply_connection_map, convert_factory, convert_pipeline, substitute


def _foreach_copy(factory):
    doc = convert_pipeline(factory, "pl_metadata_driven_load")
    return doc["properties"]["activities"][1]["typeProperties"]["activities"][0]


def test_copy_datasets_are_inlined_with_parameters(factory):
    copy = _foreach_copy(factory)
    assert "inputs" not in copy and "outputs" not in copy
    src = copy["typeProperties"]["source"]["datasetSettings"]
    assert src["typeProperties"]["table"] == {"value": "@item().table_name", "type": "Expression"}
    sink = copy["typeProperties"]["sink"]["datasetSettings"]
    assert sink["typeProperties"]["location"]["folderPath"]["value"] == "erp/@{item().table_name}"
    assert sink["externalReferences"]["connection"] == "{{CONNECTION:ls_adls_lake}}"


def test_substitution_rules():
    params = {"a": "lit", "b": {"value": "@item().x", "type": "Expression"}}
    assert substitute({"value": "@dataset().a", "type": "Expression"}, params) == "lit"
    assert substitute("raw/@{dataset().a}/x", params) == "raw/lit/x"
    assert substitute("raw/@{dataset().b}", params) == {"value": "raw/@{item().x}", "type": "Expression"}
    out = substitute({"value": "@concat(dataset().a, dataset().b)", "type": "Expression"}, params)
    assert out == {"value": "@concat('lit', item().x)", "type": "Expression"}


def test_dataset_defaults_and_literals(factory):
    doc = convert_pipeline(factory, "pl_archive_landing_files")
    branch = doc["properties"]["activities"][1]["typeProperties"]["ifTrueActivities"]
    src_loc = branch[0]["typeProperties"]["source"]["datasetSettings"]["typeProperties"]["location"]
    sink_loc = branch[0]["typeProperties"]["sink"]["datasetSettings"]["typeProperties"]["location"]
    assert src_loc["fileSystem"] == "landing"      # dataset default
    assert sink_loc["fileSystem"] == "archive"     # literal passed by the activity
    assert "datasetSettings" in branch[1]["typeProperties"]  # Delete activity


def test_execute_pipeline_becomes_invoke_pipeline(factory):
    act = convert_pipeline(factory, "pl_master_daily")["properties"]["activities"][0]
    assert act["type"] == "InvokePipeline"
    assert act["typeProperties"]["pipelineId"] == "{{PIPELINE:pl_metadata_driven_load}}"
    assert act["typeProperties"]["parameters"] == {"source_system": "ERP"}


def test_blockers_are_kept_but_deactivated(factory):
    act = convert_pipeline(factory, "pl_customer_dimension")["properties"]["activities"][0]
    assert act["state"] == "Inactive"
    assert act["description"].startswith("[MIGRATION BLOCKER]")


def test_linked_service_becomes_connection(factory):
    act = convert_pipeline(factory, "pl_databricks_transform")["properties"]["activities"][0]
    assert "linkedServiceName" not in act
    assert act["externalReferences"]["connection"] == "{{CONNECTION:ls_databricks}}"


def test_connection_map_and_files(factory, tmp_path):
    files = convert_factory(factory, tmp_path, mapping={"ls_databricks": "conn-123", "WORKSPACE_ID": "ws-1"})
    assert len(files) == 7
    doc = json.loads((tmp_path / "pl_databricks_transform.json").read_text())
    assert doc["properties"]["activities"][0]["externalReferences"]["connection"] == "conn-123"
    master = json.loads((tmp_path / "pl_master_daily.json").read_text())
    assert master["properties"]["activities"][0]["typeProperties"]["workspaceId"] == "ws-1"
    assert apply_connection_map({"x": "{{CONNECTION:a}}"}, {"a": "b"}) == {"x": "b"}
