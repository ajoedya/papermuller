"""Aggregate provider-reported usage without inventing missing tokens or cost."""

import math


def reported_values(raw):
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            if key == "cost" or float(value).is_integer():
                result[key] = value
    if "total_tokens" not in result and all(k in result for k in ("prompt_tokens", "completion_tokens")):
        result["total_tokens"] = result["prompt_tokens"] + result["completion_tokens"]
    return result


def add_response(rows, key, raw, simulated=False):
    values = {} if simulated else reported_values(raw)
    row = rows.setdefault(str(key), {"calls": 0, "simulated_calls": 0,
                                   "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                                   "cost": 0, "has_cost": False, "has_tokens": False,
                                   "token_reports": 0, "cost_reports": 0,
                                   "prompt_reports": 0, "completion_reports": 0})
    row["calls"] += 1
    row["simulated_calls"] += int(bool(simulated))
    for field, counter in (("prompt_tokens", "prompt_reports"), ("completion_tokens", "completion_reports"),
                           ("total_tokens", "token_reports"), ("cost", "cost_reports")):
        if field in values:
            row[field] += values[field]
            row[counter] += 1
    row["has_tokens"] = row["token_reports"] > 0
    row["has_cost"] = row["cost_reports"] > 0
    return values


def totals(rows):
    fields = ("calls", "simulated_calls", "prompt_tokens", "completion_tokens", "total_tokens", "cost",
              "token_reports", "cost_reports", "prompt_reports", "completion_reports")
    result = {field: sum(row.get(field, 0) for row in rows.values()) for field in fields}
    result["real_responses"] = result["calls"] - result["simulated_calls"]
    result["has_tokens"] = result["token_reports"] > 0
    result["has_cost"] = result["cost_reports"] > 0
    result["partial_tokens"] = 0 < result["token_reports"] < result["real_responses"]
    result["partial_cost"] = 0 < result["cost_reports"] < result["real_responses"]
    return result
