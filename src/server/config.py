"""
JADX MCP Server - Configuration Module

This module manages server configuration, HTTP client setup, and communication
with the JADX Java plugin. Handles connection management, error handling,
and request/response processing.

Author: Jafar Pathan (zinja-coder@github)
License: See LICENSE file
"""

import logging
import httpx
import json
import sys
import uuid
from typing import Union, Dict, Any

# Default Configuration
JADX_HOST = "127.0.0.1"
JADX_PORT = 8650
JADX_HTTP_BASE = f"http://{JADX_HOST}:{JADX_PORT}"

# Logging Setup
logger = logging.getLogger("jadx-mcp-server")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.ERROR)
logger.propagate = False


def _rebuild_jadx_http_base():
    """Rebuild the base URL used for all requests to the JADX plugin."""
    global JADX_HTTP_BASE
    JADX_HTTP_BASE = f"http://{JADX_HOST}:{JADX_PORT}"


def set_jadx_host(host: str):
    """
    Updates the JADX plugin host.

    Args:
        host: Hostname or IP where JADX AI MCP plugin is reachable

    Side Effects:
        Updates global JADX_HOST and JADX_HTTP_BASE configuration
    """
    global JADX_HOST
    JADX_HOST = host
    _rebuild_jadx_http_base()


def set_jadx_port(port: int):
    """
    Updates the JADX plugin port.

    Args:
        port: TCP port number where JADX AI MCP plugin is listening

    Side Effects:
        Updates global JADX_PORT and JADX_HTTP_BASE configuration
    """
    global JADX_PORT
    JADX_PORT = port
    _rebuild_jadx_http_base()


def health_ping() -> Union[str, Dict[str, Any]]:
    """
    Checks if the JADX Java plugin is reachable.

    Returns:
        Union[str, Dict[str, Any]]: Success message or error dictionary

    Note:
        Performs synchronous HTTP health check with 60-second timeout
    """
    try:
        with httpx.Client(trust_env=False) as client:
            resp = client.get(f"{JADX_HTTP_BASE}/health", timeout=60)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"error": str(e)}


def _ensure_request_id(params: Dict[str, Any]) -> str:
    request_id = params.get("request_id") or uuid.uuid4().hex
    params["request_id"] = request_id
    return request_id


def _success_response(
    payload: Any,
    *,
    request_id: str,
    status: int = None,
    raw_text: bool = False,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": True, "data": payload, "request_id": request_id}
    if status is not None:
        result["status"] = status

    if isinstance(payload, dict):
        for key, value in payload.items():
            result.setdefault(key, value)
    elif raw_text:
        result["content"] = payload
        result["response"] = payload
    else:
        result["value"] = payload

    if raw_text:
        result["format"] = "raw"
    return result


def _error_response(
    error: str,
    *,
    request_id: str,
    status: int = None,
    raw: str = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "error": error, "request_id": request_id}
    if status is not None:
        result["status"] = status
    if raw is not None:
        result["raw"] = raw
    return result


async def get_from_jadx(
    endpoint: str,
    params: Dict[str, Any] = None,
    response_format: str = "auto",
) -> Union[str, Dict[str, Any]]:
    """
    Generic async helper to request data from the JADX plugin.

    Args:
        endpoint: API endpoint path (e.g., "class-source", "manifest")
        params: Query parameters dictionary for the request

    Returns:
        Union[str, Dict[str, Any]]: Parsed JSON response, legacy text wrapped as
        ``{"response": text}``, or a structured error dict
        ``{"ok": False, "error": str, "status": int|None, "raw": str|None}``.

    Note:
        response_format accepts "raw", "json", or "auto". "json" requires a
        JSON body. "auto" asks the Java plugin to choose JSON for bounded text
        responses and raw text for very large responses. Raw text is returned
        with both ``content`` and legacy ``response`` fields.
    """
    params = dict(params or {})
    normalized_format = (response_format or "auto").lower()
    request_id = _ensure_request_id(params)
    if normalized_format not in {"raw", "json", "auto"}:
        return _error_response(
            "Invalid response_format. Expected one of: raw, json, auto.",
            request_id=request_id,
        )
    if "format" not in params and normalized_format in {"raw", "json", "auto"}:
        params["format"] = normalized_format
    url = f"{JADX_HTTP_BASE}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(url, params=params, headers={"X-Request-Id": request_id}, timeout=3600)
            resp.raise_for_status()

            try:
                parsed = resp.json()
                if isinstance(parsed, dict) and "request_id" not in parsed:
                    parsed["request_id"] = request_id
                if isinstance(parsed, dict) and parsed.get("error") and parsed.get("ok") is not True:
                    return _error_response(
                        str(parsed.get("error", "Unknown JADX error")),
                        request_id=request_id,
                        status=resp.status_code,
                        raw=parsed.get("raw"),
                    )
                return _success_response(parsed, request_id=request_id, status=resp.status_code)
            except json.JSONDecodeError:
                raw = resp.text
                if normalized_format == "json":
                    preview = raw[:1000] if raw else ""
                    error_msg = (
                        f"Non-JSON response from JADX endpoint '{endpoint}' "
                        f"(status={resp.status_code}) while JSON was explicitly requested."
                    )
                    logger.error("%s Body preview: %r", error_msg, preview)
                    return _error_response(error_msg, request_id=request_id, status=resp.status_code, raw=preview)
                return _success_response(raw, request_id=request_id, status=resp.status_code, raw_text=True)

    except httpx.HTTPStatusError as e:
        body = ""
        server_error = None
        server_request_id = request_id
        try:
            body = e.response.text[:1000]
            parsed_body = e.response.json()
            if isinstance(parsed_body, dict):
                server_error = parsed_body.get("error")
                server_request_id = parsed_body.get("request_id") or request_id
        except Exception:
            pass
        error_msg = server_error or f"HTTP error {e.response.status_code} from '{endpoint}'"
        logger.error("%s. Body preview: %r", error_msg, body)
        return _error_response(error_msg, request_id=server_request_id, status=e.response.status_code, raw=body)

    except httpx.TimeoutException:
        error_msg = (
            f"Request to JADX plugin timed out after 3600s for endpoint '{endpoint}'. "
            "The operation may still be running in JADX-GUI. "
            "For large APKs, code-level searches can take several minutes."
        )
        logger.error(error_msg)
        return _error_response(error_msg, request_id=request_id, status=None, raw=None)

    except httpx.ConnectError:
        error_msg = (
            f"Cannot connect to JADX plugin at {JADX_HTTP_BASE}. "
            "Ensure JADX-GUI is running and the AI MCP plugin is active."
        )
        logger.error(error_msg)
        return _error_response(error_msg, request_id=request_id, status=None, raw=None)

    except Exception as e:
        error_msg = f"Unexpected error communicating with JADX plugin: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        return _error_response(error_msg, request_id=request_id, status=None, raw=None)


async def post_to_jadx(endpoint: str, params: Dict[str, Any] = None) -> Union[str, Dict[str, Any]]:
    """
    Generic async helper to POST to the JADX plugin (for mutating operations like cache-clear).
    """
    params = dict(params or {})
    request_id = _ensure_request_id(params)
    url = f"{JADX_HTTP_BASE}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(url, params=params, headers={"X-Request-Id": request_id}, timeout=30)
            resp.raise_for_status()
            try:
                parsed = resp.json()
                if isinstance(parsed, dict) and "request_id" not in parsed:
                    parsed["request_id"] = request_id
                if isinstance(parsed, dict) and parsed.get("error") and parsed.get("ok") is not True:
                    return _error_response(
                        str(parsed.get("error", "Unknown JADX error")),
                        request_id=request_id,
                        status=resp.status_code,
                        raw=parsed.get("raw"),
                    )
                return _success_response(parsed, request_id=request_id, status=resp.status_code)
            except json.JSONDecodeError:
                return _success_response(resp.text, request_id=request_id, status=resp.status_code, raw_text=True)
    except httpx.HTTPStatusError as e:
        body = ""
        server_error = None
        server_request_id = request_id
        try:
            body = e.response.text[:1000]
            parsed_body = e.response.json()
            if isinstance(parsed_body, dict):
                server_error = parsed_body.get("error")
                server_request_id = parsed_body.get("request_id") or request_id
        except Exception:
            pass
        return _error_response(
            server_error or f"HTTP error {e.response.status_code} from '{endpoint}'",
            request_id=server_request_id,
            status=e.response.status_code,
            raw=body,
        )
    except httpx.ConnectError:
        return _error_response(
            f"Cannot connect to JADX plugin at {JADX_HTTP_BASE}. Ensure JADX-GUI is running.",
            request_id=request_id,
        )
    except Exception as e:
        return _error_response(
            f"POST to {endpoint} failed: {type(e).__name__}: {str(e)}",
            request_id=request_id,
        )


async def cancel_request(request_id: str) -> Dict[str, Any]:
    return await post_to_jadx("cancel-request", {"request_id": request_id})


async def get_request_status(request_id: str) -> Dict[str, Any]:
    result = await get_from_jadx("request-status", {"request_id": request_id}, response_format="json")
    return result if isinstance(result, dict) else {"error": "Unexpected request-status response"}


async def heartbeat_request(request_id: str) -> Dict[str, Any]:
    return await post_to_jadx("request-heartbeat", {"request_id": request_id})


async def get_search_progress(request_id: str = None) -> Dict[str, Any]:
    """
    Poll the JADX plugin for current search progress.

    Returns:
        Dict with keys: state, scanned, total, matches, search_id, operation_type,
        elapsed_ms.  When state is "failed", also includes "error".
        Returns {"state": "unknown"} on connection failure.
    """
    url = f"{JADX_HTTP_BASE}/search-progress"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            params = {"request_id": request_id} if request_id else None
            headers = {"X-Request-Id": request_id} if request_id else None
            resp = await client.get(url, params=params, headers=headers, timeout=5)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"state": "unknown"}
