"""Fabric compatibility rules for ADF object types.

Each rule maps an ADF type to ``(status, fabric_equivalent, note)``:

* ``supported`` - lifts across with no redesign (connections are re-pointed),
* ``rework``    - has a Fabric equivalent but needs manual changes,
* ``blocker``   - no direct equivalent; needs a redesign before cut-over.
"""
from __future__ import annotations

SUPPORTED = "supported"
REWORK = "rework"
BLOCKER = "blocker"
STATUS_ORDER = {SUPPORTED: 0, REWORK: 1, BLOCKER: 2}

ACTIVITY_RULES: dict[str, tuple[str, str, str]] = {
    "Copy": (SUPPORTED, "Copy data", "Datasets are inlined into the activity; re-point connections."),
    "Lookup": (SUPPORTED, "Lookup", "Dataset is inlined into the activity."),
    "GetMetadata": (SUPPORTED, "Get metadata", "Dataset is inlined into the activity."),
    "Delete": (SUPPORTED, "Delete data", "Dataset is inlined into the activity."),
    "ForEach": (SUPPORTED, "ForEach", "Inner activities are assessed separately."),
    "IfCondition": (SUPPORTED, "If condition", "Branches are assessed separately."),
    "Switch": (SUPPORTED, "Switch", "Cases are assessed separately."),
    "Until": (SUPPORTED, "Until", "Inner activities are assessed separately."),
    "Wait": (SUPPORTED, "Wait", ""),
    "Fail": (SUPPORTED, "Fail", ""),
    "Filter": (SUPPORTED, "Filter", ""),
    "SetVariable": (SUPPORTED, "Set variable", ""),
    "AppendVariable": (SUPPORTED, "Append variable", ""),
    "WebActivity": (SUPPORTED, "Web", "Move secrets from Key Vault references into a Fabric connection."),
    "Script": (SUPPORTED, "Script", ""),
    "SqlServerStoredProcedure": (SUPPORTED, "Stored procedure", ""),
    "DatabricksNotebook": (SUPPORTED, "Azure Databricks (notebook)", "Uses a Fabric connection to the workspace."),
    "DatabricksSparkJar": (SUPPORTED, "Azure Databricks (jar)", ""),
    "DatabricksSparkPython": (SUPPORTED, "Azure Databricks (Python)", ""),
    "AzureFunctionActivity": (SUPPORTED, "Azure Function", ""),
    "ExecutePipeline": (SUPPORTED, "Invoke pipeline", "Child pipeline must be migrated first (see waves)."),
    "WebHook": (REWORK, "Web + Until polling", "Fabric has no WebHook activity; poll a status endpoint instead."),
    "Custom": (REWORK, "Notebook or Azure Batch", "Custom (Batch) activity: re-host the code in a notebook."),
    "HDInsightHive": (REWORK, "Notebook (Spark SQL)", "Port HiveQL to Spark SQL in a Fabric notebook."),
    "HDInsightSpark": (REWORK, "Notebook / Spark job definition", ""),
    "AzureMLExecutePipeline": (REWORK, "Notebook", "Call the Azure ML pipeline from a notebook."),
    "ExecuteDataFlow": (BLOCKER, "Dataflow Gen2 or notebook", "Mapping data flows have no direct Fabric equivalent; rebuild."),
    "ExecuteWranglingDataflow": (BLOCKER, "Dataflow Gen2", "Rebuild the Power Query as a Dataflow Gen2."),
    "ExecuteSSISPackage": (BLOCKER, "Notebook / pipeline rewrite", "Fabric has no Azure-SSIS runtime; rewrite the package logic."),
}

LINKED_SERVICE_RULES: dict[str, tuple[str, str, str]] = {
    "AzureSqlDatabase": (SUPPORTED, "Azure SQL Database connection", ""),
    "AzureSqlDW": (SUPPORTED, "Azure Synapse Analytics connection", ""),
    "AzureBlobFS": (SUPPORTED, "Azure Data Lake Storage Gen2 connection", "Consider a OneLake shortcut instead of copying."),
    "AzureBlobStorage": (SUPPORTED, "Azure Blob Storage connection", ""),
    "RestService": (SUPPORTED, "REST connection", ""),
    "HttpServer": (SUPPORTED, "HTTP connection", ""),
    "AzureDatabricks": (SUPPORTED, "Azure Databricks connection", ""),
    "AzureFunction": (SUPPORTED, "Azure Function connection", ""),
    "SqlServer": (REWORK, "SQL Server connection via on-premises data gateway", "Install a gateway in place of the self-hosted IR."),
    "Oracle": (REWORK, "Oracle connection via on-premises data gateway", ""),
    "FileServer": (REWORK, "File system connection via on-premises data gateway", ""),
    "Sftp": (SUPPORTED, "SFTP connection", ""),
    "AzureKeyVault": (REWORK, "Fabric connection credentials", "Fabric connections store secrets themselves; Key Vault references must be re-entered or use the Key Vault reference preview."),
}

TRIGGER_RULES: dict[str, tuple[str, str, str]] = {
    "ScheduleTrigger": (SUPPORTED, "Pipeline schedule", "One schedule per pipeline in Fabric."),
    "BlobEventsTrigger": (REWORK, "Storage event trigger (Activator)", "Recreate as an Azure Blob Storage event trigger."),
    "TumblingWindowTrigger": (REWORK, "Schedule + window parameters", "No tumbling-window trigger: pass window start/end yourself and handle backfill."),
    "CustomEventsTrigger": (REWORK, "Activator / Event Grid", ""),
}

RUNTIME_RULES: dict[str, tuple[str, str, str]] = {
    "Managed": (SUPPORTED, "Fabric-managed compute", "Azure IR is not needed in Fabric."),
    "SelfHosted": (REWORK, "On-premises data gateway", "Install and register a gateway on the SHIR host(s)."),
    "ManagedSSIS": (BLOCKER, "None", "Azure-SSIS runtime has no Fabric equivalent."),
}

EFFORT_HOURS = {
    "activity": {SUPPORTED: 0.25, REWORK: 4.0, BLOCKER: 16.0},
    "linked_service": {SUPPORTED: 0.5, REWORK: 2.0, BLOCKER: 8.0},
    "trigger": {SUPPORTED: 0.25, REWORK: 2.0, BLOCKER: 4.0},
    "integration_runtime": {SUPPORTED: 0.0, REWORK: 4.0, BLOCKER: 24.0},
    "pipeline_base": 0.5,
}

_UNKNOWN = (REWORK, "Unknown - review manually", "Type not in the rule catalogue.")


def rule_for(kind: str, adf_type: str) -> tuple[str, str, str]:
    table = {
        "activity": ACTIVITY_RULES,
        "linked_service": LINKED_SERVICE_RULES,
        "trigger": TRIGGER_RULES,
        "integration_runtime": RUNTIME_RULES,
    }[kind]
    return table.get(adf_type, _UNKNOWN)


def runtime_type(props: dict) -> str:
    """Azure-SSIS runtimes are ``Managed`` with ``ssisProperties``; report them separately."""
    rtype = props.get("type", "Managed")
    if rtype == "Managed" and props.get("typeProperties", {}).get("ssisProperties"):
        return "ManagedSSIS"
    return rtype


def worst(statuses) -> str:
    statuses = list(statuses)
    if not statuses:
        return SUPPORTED
    return max(statuses, key=STATUS_ORDER.__getitem__)
