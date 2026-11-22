"""Specialist: relative comparisons only within an explicit reference frame.

Unlike an astronomical claim, a comparison of 6mm and 13m with frame='model'
means just two declared model lengths. Nothing physical is inferred.
"""
from decimal import Decimal, InvalidOperation, localcontext
from rafvalchecks.core.contract import outcome

UNITS = {
    "mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal("1"),
    "km": Decimal("1000"), "bytes": Decimal("1"), "count": Decimal("1"),
    "s": Decimal("1"), "ms": Decimal("0.001")
}
DIMENSIONS = {"mm": "length", "cm": "length", "m": "length", "km": "length",
              "bytes": "bytes", "count": "count", "s": "time", "ms": "time"}


def check(ctx, node):
    cfg = node.get("config", {})
    frame = cfg.get("frame")
    source = cfg.get("assumption")
    left, right = cfg.get("left"), cfg.get("right")
    if not isinstance(frame, str) or not frame or not isinstance(source, str) or not source or not isinstance(left, dict) or not isinstance(right, dict):
        return outcome(node["id"], "BLOCKED", token="PAIR_FRAME_OR_SOURCE_MISSING")
    if set(left) != {"value", "unit"} or set(right) != {"value", "unit"}:
        return outcome(node["id"], "BLOCKED", token="PAIR_FIELDS_INVALID")
    ul, ur = left["unit"], right["unit"]
    if not isinstance(ul, str) or not isinstance(ur, str) or ul not in UNITS or ur not in UNITS or DIMENSIONS[ul] != DIMENSIONS[ur]:
        return outcome(node["id"], "BLOCKED", token="PAIR_DIMENSION_MISMATCH")
    if not isinstance(left["value"], str) or not isinstance(right["value"], str):
        return outcome(node["id"], "BLOCKED", token="PAIR_DECIMAL_STRING_REQUIRED")
    try:
        with localcontext() as context:
            context.prec = 36
            x = Decimal(left["value"]) * UNITS[ul]
            y = Decimal(right["value"]) * UNITS[ur]
            if not x.is_finite() or not y.is_finite() or x < 0 or y <= 0:
                raise InvalidOperation
            ratio = x / y
            relation = "smaller" if x < y else "larger" if x > y else "equal"
    except (InvalidOperation, ValueError, OverflowError):
        return outcome(node["id"], "BLOCKED", token="PAIR_VALUE_INVALID")
    return outcome(node["id"], "PASS_SCOPED", evidence="EXECUTED_LOCAL", details={
        "scope": "relative_model_comparison_only", "frame": frame, "assumption": source,
        "dimension": DIMENSIONS[ul], "relation": relation,
        "left_in_base_unit": str(x), "right_in_base_unit": str(y), "ratio": str(ratio)})
