"""
Standardized response envelope.

All NEW MCP tools, and any tool migrated as part of the standardization
effort, MUST return responses through this helper. The shape is:

    {
        "ok":       bool,
        "data":     <tool-specific payload, present iff ok=True>,
        "error":    <str, present iff ok=False>,
        "status":   <int|None, HTTP status from JADX plugin if applicable>,
        "warnings": <list[str], optional>,
        "raw":      <str|None, raw response preview when relevant>
    }

Goals:
  * Distinguish success from failure on a single boolean key.
  * Stop returning error text inside ``"response"`` (the historic footgun
    that masked plugin 404s as if they were valid data).
  * Give the LLM a single shape to parse across tools.
"""

from typing import Any, Dict, List, Optional


def ok(data: Any, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "data": data}
    if isinstance(data, dict):
        for key, value in data.items():
            out.setdefault(key, value)
    if warnings:
        out["warnings"] = list(warnings)
    return out


def err(
    error: str,
    *,
    status: Optional[int] = None,
    raw: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "error": error}
    if status is not None:
        out["status"] = status
    if raw is not None:
        out["raw"] = raw
    if warnings:
        out["warnings"] = list(warnings)
    return out


def from_jadx(result: Any, *, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Wrap the result of a ``get_from_jadx`` / paginated call into the
    standardized envelope.

    Recognises the structured-error dict produced by ``config.get_from_jadx``
    (``{"ok": False, "error": ..., "status": ..., "raw": ...}``) and the
    legacy ``{"error": ...}`` shape, propagating status/raw when present.
    Anything else is treated as a successful payload.
    """
    if isinstance(result, dict):
        if result.get("ok") is True:
            if warnings:
                out = dict(result)
                existing = out.get("warnings", [])
                out["warnings"] = [*existing, *warnings] if isinstance(existing, list) else list(warnings)
                return out
            return result
        if result.get("ok") is False:
            out = dict(result)
            if warnings:
                existing = out.get("warnings", [])
                out["warnings"] = [*existing, *warnings] if isinstance(existing, list) else list(warnings)
            return out
        if "error" in result and result.get("ok") is not True:
            return err(
                str(result["error"]),
                status=result.get("status"),
                raw=result.get("raw"),
                warnings=warnings,
            )
    return ok(result, warnings=warnings)
