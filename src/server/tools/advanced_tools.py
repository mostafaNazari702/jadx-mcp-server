"""
Wrappers for the advanced endpoints added in the v6.4.0 Java plugin:
/find-string-literals, /grep-code, /find-methods-by-signature, /get-callees,
/get-subclasses, /get-superclasses, /get-implementations and
/find-android-components-deep.

These are more powerful than the basic search tools and are
realy useful when dealing with obfuscated APKs.
"""

import asyncio
import logging
import uuid
from typing import Optional

from src.PaginationUtils import PaginationUtils
from src.server.config import get_from_jadx
from src.server.tools.search_tools import _poll_progress

logger = logging.getLogger("jadx-mcp-server.advanced")


# find-string-literals
async def find_string_literals(
    pattern: str,
    regex: bool = False,
    case_sensitive: bool = False,
    package: str = "",
    max_literal_len: int = 256,
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    report_progress=None,
) -> dict:
    """
    Search for string literals across all decompiled classes.
    Does a substring match by default, pass regex=True for regex.

    Really useful for finding URLs, error messages, tracking keys etc
    since those usualy live directly in string literals.

    Args:
        pattern: Substring or regex to match against literal values.
        regex: Treat pattern as a regex. Default False.
        case_sensitive: Default False.
        package: Optional package prefix to narrow the scan.
        max_literal_len: Skip literals longer than this (default 256).
        offset, count: Pagination.
        report_progress: Optional progress callback.

    Returns:
        dict with `items` (list of hits) and `pagination`.
    """
    request_id = uuid.uuid4().hex
    progress_task = asyncio.create_task(_poll_progress(report_progress, request_id=request_id))
    try:
        return await PaginationUtils.get_paginated_data(
            endpoint="find-string-literals",
            offset=offset,
            count=count,
            additional_params={
                "pattern": pattern,
                "regex": "true" if regex else "false",
                "case_sens": "true" if case_sensitive else "false",
                "package": package,
                "max_literal_len": str(max_literal_len),
                "max_hits": str(max_hits),
                "request_id": request_id,
            },
            data_extractor=lambda parsed: parsed.get("items", []),
            fetch_function=get_from_jadx,
        )
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass


# /grep-code
async def grep_code(
    pattern: str,
    regex: bool = False,
    case_sensitive: bool = False,
    context: int = 1,
    package: str = "",
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    report_progress=None,
) -> dict:
    """
    Grep the decompiled source of all classes for a pattern.
    Returns the matching lines with some context around them.

    More usefull than search_classes_by_keyword when you want to know
    exactly where in the code something appears.

    Args:
        pattern: Substring (default) or regex (when regex=True).
        regex: Treat pattern as a Java regex.
        case_sensitive: Default False.
        context: Lines of context to include around each hit (0-10, default 1).
        package: Optional package prefix.
        offset, count: Pagination.

    Returns:
        dict with `items` (list of {class, line, match, snippet}) and `pagination`.
    """
    request_id = uuid.uuid4().hex
    progress_task = asyncio.create_task(_poll_progress(report_progress, request_id=request_id))
    try:
        return await PaginationUtils.get_paginated_data(
            endpoint="grep-code",
            offset=offset,
            count=count,
            additional_params={
                "pattern": pattern,
                "regex": "true" if regex else "false",
                "case_sens": "true" if case_sensitive else "false",
                "context": str(context),
                "package": package,
                "max_hits": str(max_hits),
                "request_id": request_id,
            },
            data_extractor=lambda parsed: parsed.get("items", []),
            fetch_function=get_from_jadx,
        )
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass


# /find-methods-by-signature
async def find_methods_by_signature(
    name_pattern: str = "",
    return_type: str = "",
    param_types: str = "",
    param_count: Optional[int] = None,
    class_pattern: str = "",
    package: str = "",
    offset: int = 0,
    count: int = 50,
    report_progress=None,
) -> dict:
    """
    Search for methods by their signature using smali, no decompilation needed.
    All filters are AND-ed, leave a filter empty to skip it.
    At least one filter is required.

    Args:
        name_pattern: Regex on the method name (case-insensitive).
        return_type: Substring of the smali return descriptor, e.g.:
              "Z"                   - boolean
              "Ljava/lang/String;"  - java.lang.String
              "Intent;"             - anything with Intent in the type
        param_types: Comma-separated type substrings, all must be present, e.g.:
              "String,Intent"       - needs at least one String and one Intent param
        param_count: Exact number of paramters.
        class_pattern: Regex on the containing class name.
        package: Package prefix, faster then class_pattern for simple filtering.
        offset, count: Pagination.

    Returns:
        dict with `items`: [{class, method, params, return_type, access}].
    """
    additional = {}
    if name_pattern:
        additional["name_pattern"] = name_pattern
    if return_type:
        additional["return_type"] = return_type
    if param_types:
        additional["param_types"] = param_types
    if param_count is not None:
        additional["param_count"] = str(param_count)
    if class_pattern:
        additional["class_pattern"] = class_pattern
    if package:
        additional["package"] = package

    request_id = uuid.uuid4().hex
    additional["request_id"] = request_id
    progress_task = asyncio.create_task(_poll_progress(report_progress, request_id=request_id))
    try:
        return await PaginationUtils.get_paginated_data(
            endpoint="find-methods-by-signature",
            offset=offset,
            count=count,
            additional_params=additional,
            data_extractor=lambda parsed: parsed.get("items", []),
            fetch_function=get_from_jadx,
        )
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass


# /get-callees
async def get_callees(
    class_name: str,
    method_name: str,
    param_signature: str = "",
) -> dict:
    """
    Returns all the methods that a given method calls.
    Basically the opposite of get_xrefs_to_method.

    Useful for tracing what a method actually does, or following
    a call chain through obfuscated helper wrappers.

    Args:
        class_name: Fully-qualified class name.
        method_name: Method name. If there are overloads, pass param_signature
            to pick the right one, otherwise the first one found is used.
        param_signature: Optional smali param descriptor to pick a specific
            overload, e.g. "Ljava/lang/String;I" for (String, int).

    Returns:
        dict with target_class, target_method, callee_count and callees list.
    """
    params = {"class_name": class_name, "method_name": method_name}
    if param_signature:
        params["param_signature"] = param_signature
    return await get_from_jadx("get-callees", params)


# /get-subclasses
async def get_subclasses(
    class_name: str,
    transitive: bool = False,
    offset: int = 0,
    count: int = 100,
) -> dict:
    """
    List classes that extend the given class.

    Args:
        class_name: Fully-qualified class name.
        transitive: If True, returns the whole descendant tree not just direct children.
        offset, count: Pagination.
    """
    return await PaginationUtils.get_paginated_data(
        endpoint="get-subclasses",
        offset=offset,
        count=count,
        additional_params={
            "class_name": class_name,
            "transitive": "true" if transitive else "false",
        },
        data_extractor=lambda parsed: parsed.get("items", []),
        fetch_function=get_from_jadx,
    )


# /get-superclasses
async def get_superclasses(class_name: str) -> dict:
    """
    Returns the parent classes and interfaces for a given class.

    Returns:
        dict with class, super_chain and direct_interfaces.

    Handy for figuring out what an obfuscated class actualy is
    (e.g. tracing it back to AppCompatActivity or BroadcastReceiver).
    """
    return await get_from_jadx("get-superclasses", {"class_name": class_name})


# /get-implementations
async def get_implementations(
    interface_name: str,
    offset: int = 0,
    count: int = 100,
) -> dict:
    """
    Returns all classes that implement the given interface,
    including ones that inherit the implementation from a parent.
    """
    return await PaginationUtils.get_paginated_data(
        endpoint="get-implementations",
        offset=offset,
        count=count,
        additional_params={"interface_name": interface_name},
        data_extractor=lambda parsed: parsed.get("items", []),
        fetch_function=get_from_jadx,
    )


# /find-android-components-deep
async def find_android_components_deep(
    component_type: str,
    offset: int = 0,
    count: int = 100,
) -> dict:
    """
    Find Android components by walking the inheritance tree from framework base classes.
    This also catches things not in the manifest like Fragments and dynamic receivers.

    App classes come before library classes in the results.

    Args:
        component_type: One of:
            "activity"       - Activities (AppCompat variants included)
            "fragment"       - Fragments (androidx + support-v4)
            "service"        - Services (IntentService, JobService etc)
            "receiver"       - BroadcastReceivers
            "provider"       - ContentProviders
            "application"    - Application subclasses
            "webview-client" - WebViewClient / WebChromeClient
            "webview"        - WebView subclasses
        offset, count: Pagination.

    Returns:
        dict with `items`: list of class name strings.
    """
    return await PaginationUtils.get_paginated_data(
        endpoint="find-android-components-deep",
        offset=offset,
        count=count,
        additional_params={"type": component_type},
        data_extractor=lambda parsed: parsed.get("items", []),
        fetch_function=get_from_jadx,
    )


# /find-string-constant-dispatchers
async def find_string_constant_dispatchers(
    getter_methods: str = "optString,getString,getAction,getType,getScheme",
    package: str = "",
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    report_progress=None,
) -> dict:
    """
    Smali-only scan for methods that branch on a string returned by a known
    "key getter" call (e.g. ``json.optString("CLASS")``, ``intent.getAction()``).

    For each matching method, returns the dispatch key and the full set of
    string literals compared against it via ``String.equals`` /
    ``equalsIgnoreCase``. This is the lowering pattern used by both
    ``switch(String)`` and ``if/else`` chains, so a single scan catches both.

    Use this whenever you need to find all "actions", "event types",
    "metadata classes" etc. that a method handles, without paying for full
    decompilation.

    Args:
        getter_methods: Comma-separated method-name filter for the dispatch
            source. Default catches the most common Android/RE keys.
        package: Optional package prefix.
        max_hits: Cap on dispatcher methods returned (absolute ceiling 50000).
        offset, count: Pagination over the (capped) result set.
        report_progress: Optional FastMCP ``ctx.report_progress`` forwarder.

    Returns: standardized envelope wrapping
        ``{items: [{class, method, params, return_type, access,
                    key_getter, getter_owner, key_literal, cases, case_count}],
           pagination: {...}, truncated?: bool, truncated_reason?: str}``.
    """
    request_id = uuid.uuid4().hex
    progress_task = asyncio.create_task(_poll_progress(report_progress, request_id=request_id))
    try:
        return await PaginationUtils.get_paginated_data(
            endpoint="find-string-constant-dispatchers",
            offset=offset,
            count=count,
            additional_params={
                "getter_methods": getter_methods,
                "package": package,
                "max_hits": str(max_hits),
                "request_id": request_id,
            },
            data_extractor=lambda parsed: parsed.get("items", []),
            fetch_function=get_from_jadx,
        )
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
