"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    profile = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in profile:
        return Verdict(alert=False, pillar="checks")

    baseline = ctx.baseline
    row_count = profile["row_count"]
    customer_null_rate = profile["null_rate"]["customer_id"]
    mean_amount = profile["mean_amount"]
    staleness_min = profile["staleness_min"]

    alert = (
        row_count < baseline["row_count_min"]
        or row_count > baseline["row_count_max"]
        or customer_null_rate > baseline["null_rate_max"]
        or mean_amount < baseline["mean_amount_min"]
        or mean_amount > baseline["mean_amount_max"]
        or staleness_min > baseline["staleness_min_max"]
    )
    return Verdict(alert=alert, pillar="checks")


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in diff:
        return Verdict(alert=False, pillar="contracts")

    if diff.get("violations"):
        return Verdict(alert=True, pillar="contracts")

    delay = diff["freshness_delay_min"]
    declared_freshness = payload.get("declared_sla", {}).get("freshness_min")
    baseline_max = ctx.baseline["freshness_delay_max_min"]
    alert = delay > baseline_max or (declared_freshness is not None and delay > declared_freshness)
    return Verdict(alert=alert, pillar="contracts")


def check_lineage_run(payload, ctx):
    slice_data = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in slice_data:
        return Verdict(alert=False, pillar="lineage")

    upstream = slice_data.get("actual_upstream", [])
    required_upstream = {"raw.orders", "raw.customers"}
    alert = (
        slice_data.get("actual_downstream_count") == 0
        or not required_upstream.issubset(set(upstream))
        or slice_data.get("duration_ms", 0) > ctx.baseline["lineage_duration_ms_max"]
    )
    return Verdict(alert=alert, pillar="lineage")


def check_feature_materialization(payload, ctx):
    drift = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    # Clean streaming variation reaches 0.472, while observed skew starts at
    # 0.970; 0.65 leaves a margin from both ranges.
    alert = drift.get("mean_shift_sigma", 0) > 0.65
    return Verdict(alert=alert, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    drift = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    alert = (
        drift.get("centroid_shift", 0) > 0.039
        or drift.get("avg_doc_age_days", 0) > 41
    )
    return Verdict(alert=alert, pillar="ai_infra")
