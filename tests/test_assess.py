from adf2fabric import assess
from adf2fabric.assess import trigger_targets
from adf2fabric.rules import BLOCKER, REWORK, SUPPORTED, runtime_type


def test_nested_activities_are_counted(factory):
    a = assess(factory)
    archive = next(p for p in a.pipelines if p.name == "pl_archive_landing_files")
    # GetMetadata, IfCondition, Copy + Delete (true branch), Wait (false branch)
    assert archive.activities == 5


def test_blockers_are_dataflow_ssis_and_ssis_runtime(factory):
    a = assess(factory)
    assert sorted(f.adf_type for f in a.blockers) == [
        "ExecuteDataFlow", "ExecuteSSISPackage", "ManagedSSIS"]
    assert a.activity_status_counts[BLOCKER] == 2


def test_readiness_and_effort(factory):
    a = assess(factory)
    total = sum(a.activity_status_counts.values())
    assert total == 22
    assert a.readiness_pct == round(100 * 20 / 22, 1)
    assert a.total_effort_hours > 0


def test_pipeline_status_is_worst_activity(factory):
    a = assess(factory)
    by_name = {p.name: p for p in a.pipelines}
    assert by_name["pl_customer_dimension"].status == BLOCKER
    assert by_name["pl_master_daily"].status == SUPPORTED


def test_tumbling_window_trigger_uses_singular_pipeline_key(factory):
    targets = trigger_targets(factory.triggers["tr_crm_hourly_window"])
    assert targets == ["pl_rest_api_ingest"]
    a = assess(factory)
    rest = next(p for p in a.pipelines if p.name == "pl_rest_api_ingest")
    assert rest.triggers == ["tr_crm_hourly_window"]


def test_gateway_items_need_rework(factory):
    a = assess(factory)
    status = {f.name: f.status for f in a.findings}
    assert status["ls_onprem_erp"] == REWORK
    assert status["ir_selfhosted"] == REWORK
    assert status["tr_crm_hourly_window"] == REWORK


def test_ssis_runtime_detection():
    assert runtime_type({"type": "Managed", "typeProperties": {"ssisProperties": {}}}) == "Managed"
    assert runtime_type({"type": "Managed", "typeProperties": {"ssisProperties": {"edition": "Standard"}}}) == "ManagedSSIS"
    assert runtime_type({"type": "SelfHosted"}) == "SelfHosted"
