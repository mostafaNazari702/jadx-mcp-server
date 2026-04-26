#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [ "fastmcp>=3.0.2", "httpx" ]
# ///

"""
Copyright (c) 2025 jadx mcp server developer(s) (https://github.com/zinja-coder/jadx-ai-mcp)
See the file 'LICENSE' for copying permission
"""

import argparse
import logging
import sys
from fastmcp import FastMCP, Context
from src.banner import jadx_mcp_server_banner
from src.server import config, tools

# Initialize MCP Server
mcp = FastMCP("JADX-AI-MCP Plugin Reverse Engineering Server")

# Bootstrap logger — always writes to stderr to keep stdout clean for stdio transport
logger = logging.getLogger("jadx-mcp-server.bootstrap")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# Import and register ALL tools using correct FastMCP pattern
from src.server.tools.class_tools import (
    fetch_current_class, get_selected_text, get_class_source,
    get_all_classes, get_methods_of_class, get_fields_of_class, get_smali_of_class,
    get_main_application_classes_names, get_main_application_classes_code, get_main_activity_class,
    get_package_tree, get_cache_stats, clear_cache
)
from src.server.tools.search_tools import (
    get_method_by_name, search_method_by_name, search_classes_by_keyword
)
from src.server.tools.resource_tools import (
    get_manifest_component, get_android_manifest, get_strings, get_all_resource_file_names,
    get_resource_file
)
from src.server.tools.refactor_tools import (
    rename_class, rename_method, rename_field, rename_package, rename_variable
)
from src.server.tools.debug_tools import (
    debug_get_stack_frames, debug_get_threads, debug_get_variables
)
from src.server.tools.xrefs_tools import (
    get_xrefs_to_class, get_xrefs_to_method, get_xrefs_to_field
)
from src.server.tools.advanced_tools import (
    find_string_literals as _adv_find_string_literals,
    grep_code as _adv_grep_code,
    find_methods_by_signature as _adv_find_methods_by_signature,
    find_string_constant_dispatchers as _adv_find_string_constant_dispatchers,
    get_callees as _adv_get_callees,
    get_subclasses as _adv_get_subclasses,
    get_superclasses as _adv_get_superclasses,
    get_implementations as _adv_get_implementations,
    find_android_components_deep as _adv_find_android_components_deep,
)
from src.server.envelope import from_jadx as _envelope_from_jadx


# CORRECT REGISTRATION PATTERN for FastMCP
@mcp.tool()
async def fetch_current_class() -> dict:
    """Fetch the currently selected class and its code from the JADX-GUI plugin."""
    return await tools.class_tools.fetch_current_class()


@mcp.tool()
async def get_selected_text() -> dict:
    """Returns the currently selected text in the decompiled code view."""
    return await tools.class_tools.get_selected_text()


@mcp.tool()
async def get_method_by_name(class_name: str, method_name: str) -> dict:
    """Fetch the source code of a method from a specific class.

    Returns the standardized envelope: ``{ok, data, error?, status?, raw?}``.
    On Java decompile failure (e.g. "Method dump skipped") the error path is
    surfaced explicitly via ``ok=False`` instead of being hidden inside a
    ``response`` text field.
    """
    return _envelope_from_jadx(
        await tools.search_tools.get_method_by_name(class_name, method_name)
    )


@mcp.tool()
async def get_all_classes(offset: int = 0, count: int = 0) -> dict:
    """Returns a list of all classes in the project with pagination support."""
    return await tools.class_tools.get_all_classes(offset, count)


@mcp.tool()
async def get_class_source(class_name: str) -> dict:
    """Fetch the Java source of a specific class.

    Returns the standardized envelope: ``{ok, data, error?, status?, raw?}``.
    A missing class or a non-JSON plugin response now surfaces as
    ``{ok: False, error: ..., status: ..., raw: ...}`` rather than being
    masqueraded as data.
    """
    return _envelope_from_jadx(
        await tools.class_tools.get_class_source(class_name)
    )


@mcp.tool()
async def search_method_by_name(method_name: str, ctx: Context = None) -> dict:
    """Search for a method name across all classes."""
    report_progress = ctx.report_progress if ctx else None
    return await tools.search_tools.search_method_by_name(method_name, report_progress=report_progress)


@mcp.tool()
async def get_methods_of_class(class_name: str) -> dict:
    """List all method names in a class."""
    return await tools.class_tools.get_methods_of_class(class_name)


@mcp.tool()
async def search_classes_by_keyword(
    search_term: str,
    package: str = "",
    search_in: str = "class",
    offset: int = 0,
    count: int = 20,
    ctx: Context = None,
) -> dict:
    """Search for classes containing a specific keyword with flexible filtering options.

    This tool performs a comprehensive search across decompiled Android code, allowing you to:
    1. Search within specific packages by providing a package name
    2. Target specific search scopes (class names, method names, fields, code content, comments)
    3. Combine multiple search scopes for precise results

    Args:
        search_term: The keyword or string to search for. This is the main search query.

        package (optional): Package name to limit the search scope.
            - If empty string (default), searches across all packages in the APK
            - If provided, only searches within classes belonging to the specified package
            - Example: "com.example.app" to search only in that package

        search_in (optional): Comma-separated list of search scopes to target.
            Valid values:
            - "class": Search in class names only
            - "method": Search in method names only
            - "field": Search in field names only
            - "code": Search in code content (method bodies, statements, etc.)
            - "comment": Search in comments

            You can specify one or multiple scopes:
            - Single scope: "class" (only class names)
            - Multiple scopes: "class,method" (class names OR method names)
            - Combined: "class,method,code" (searches in all three scopes)

            Default: "class" (class-name metadata search; instant on large APKs).
            IMPORTANT: "code" / "comment" require full source decompilation and can
            take minutes on 100K+ class APKs — opt in explicitly. Prefer
            `find_string_literals` or `grep_code` when you need code-level matches
            with line context.
            For multi-scope FAST searches use "class,method,field" (all metadata).


        offset (optional): Starting index for pagination. Default: 0
        count (optional): Maximum number of results to return. Default: 20

    Returns:
        dict: Paginated list of classes containing the search term, with metadata about matches

    MCP Tool: search_classes_by_keyword
    Description: Advanced search tool that finds classes matching a keyword with package filtering
                 and scope targeting capabilities. Use this when you need to find specific code
                 patterns, class names, method names, or other identifiers across the decompiled APK."""
    report_progress = ctx.report_progress if ctx else None
    return await tools.search_tools.search_classes_by_keyword(
        search_term, package, search_in, offset, count, report_progress=report_progress
    )


@mcp.tool()
async def get_fields_of_class(class_name: str) -> dict:
    """List all field names in a class."""
    return await tools.class_tools.get_fields_of_class(class_name)


@mcp.tool()
async def get_smali_of_class(class_name: str) -> dict:
    """Fetch the smali representation of a class."""
    return await tools.class_tools.get_smali_of_class(class_name)


@mcp.tool()
async def get_manifest_component(component_type: str, only_exported: bool = False) -> dict:
    """Retrieve specified component data from AndroidManifest.xml, support filter exported components.
    Support standard Android components: activity, provider, service, receiver."""
    return _envelope_from_jadx(
        await tools.resource_tools.get_manifest_component(component_type, only_exported)
    )


@mcp.tool()
async def get_android_manifest() -> dict:
    """Retrieve and return the AndroidManifest.xml content."""
    return await tools.resource_tools.get_android_manifest()


@mcp.tool()
async def get_strings(offset: int = 0, count: int = 0) -> dict:
    """Retrieve contents of strings.xml files."""
    return await tools.resource_tools.get_strings(offset, count)


@mcp.tool()
async def get_all_resource_file_names(offset: int = 0, count: int = 0) -> dict:
    """Retrieve all resource files names."""
    return await tools.resource_tools.get_all_resource_file_names(offset, count)


@mcp.tool()
async def get_resource_file(resource_name: str) -> dict:
    """Retrieve resource file content."""
    return await tools.resource_tools.get_resource_file(resource_name)


@mcp.tool()
async def get_main_application_classes_names() -> dict:
    """Fetch main application classes' names from Manifest package."""
    return await tools.class_tools.get_main_application_classes_names()


@mcp.tool()
async def get_main_application_classes_code(offset: int = 0, count: int = 0) -> dict:
    """Fetch main application classes' code with pagination."""
    return await tools.class_tools.get_main_application_classes_code(offset, count)


@mcp.tool()
async def get_main_activity_class() -> dict:
    """Fetch the main activity class from AndroidManifest.xml."""
    return await tools.class_tools.get_main_activity_class()


@mcp.tool()
async def get_package_tree() -> dict:
    """Get all packages in the APK sorted by class count. Shows total_classes, total_packages, and per-package name, class_count, is_likely_library. Use this first to understand the APK structure before searching."""
    return await tools.class_tools.get_package_tree()


@mcp.tool()
async def get_cache_stats() -> dict:
    """Get decompilation cache statistics: hits, misses, hit_rate, cached_classes, compressed_mb, compression_ratio."""
    return await tools.class_tools.get_cache_stats()


@mcp.tool()
async def clear_cache() -> dict:
    """Clear the decompilation source cache and reset counters. Use when switching APKs or to free memory."""
    return await tools.class_tools.clear_cache()


@mcp.tool()
async def cancel_request(request_id: str) -> dict:
    """Request cooperative cancellation for a long-running JADX plugin request."""
    return await config.cancel_request(request_id)


@mcp.tool()
async def get_request_status(request_id: str) -> dict:
    """Get cooperative request status for a request_id returned by another tool."""
    return await config.get_request_status(request_id)


@mcp.tool()
async def heartbeat_request(request_id: str) -> dict:
    """Refresh heartbeat metadata for a long-running JADX plugin request."""
    return await config.heartbeat_request(request_id)


@mcp.tool()
async def rename_class(class_name: str, new_name: str) -> dict:
    """Renames a specific class."""
    return await tools.refactor_tools.rename_class(class_name, new_name)


@mcp.tool()
async def rename_method(method_name: str, new_name: str) -> dict:
    """Renames a specific method."""
    return await tools.refactor_tools.rename_method(method_name, new_name)


@mcp.tool()
async def rename_field(class_name: str, field_name: str, new_name: str) -> dict:
    """Renames a specific field."""
    return await tools.refactor_tools.rename_field(class_name, field_name, new_name)


@mcp.tool()
async def rename_package(old_package_name: str, new_package_name: str) -> dict:
    """Renames a package and all its classes."""
    return await tools.refactor_tools.rename_package(old_package_name, new_package_name)


@mcp.tool()
async def rename_variable(class_name: str, method_name: str, variable_name: str, new_name: str, reg: str = None, ssa: str = None) -> dict:
    """Renames a specific variable in a method."""
    return await tools.refactor_tools.rename_variable(class_name, method_name, variable_name, new_name, reg, ssa)


@mcp.tool()
async def debug_get_stack_frames() -> dict:
    """Get current stack frames (call stack)."""
    return await tools.debug_tools.debug_get_stack_frames()


@mcp.tool()
async def debug_get_threads() -> dict:
    """Get all threads in the debugged process."""
    return await tools.debug_tools.debug_get_threads()


@mcp.tool()
async def debug_get_variables() -> dict:
    """Get current variables when process is suspended."""
    return await tools.debug_tools.debug_get_variables()


@mcp.tool()
async def get_xrefs_to_class(class_name: str, offset: int = 0, count: int = 20, include_lines: bool = False) -> dict:
    """Find all references to a class. Set include_lines=True to annotate each entry with 1-based line numbers (class-level hint) inside the referencing class."""
    return await tools.xrefs_tools.get_xrefs_to_class(class_name, offset, count, include_lines)


@mcp.tool()
async def get_xrefs_to_method(
    class_name: str, method_name: str, offset: int = 0, count: int = 20, include_lines: bool = False
) -> dict:
    """Find all references to a method. Set include_lines=True to annotate each entry with 1-based line numbers (class-level hint) inside the referencing class."""
    return await tools.xrefs_tools.get_xrefs_to_method(
        class_name, method_name, offset, count, include_lines
    )


@mcp.tool()
async def get_xrefs_to_field(
    class_name: str, field_name: str, offset: int = 0, count: int = 20, include_lines: bool = False
) -> dict:
    """Find all references to a field. Set include_lines=True to annotate each entry with 1-based line numbers (class-level hint) inside the referencing class."""
    return await tools.xrefs_tools.get_xrefs_to_field(
        class_name, field_name, offset, count, include_lines
    )


# advanced RE Tools (v6.4.0 plugin)
# these tools eliminate the most common AI dead-ends in obfuscated APK
# analysis: code-string search, regex grep with snippets, signature-based
# method search, outbound call graph traversal, deep class-hierarchy queries,
# and inheritance-based Android component discovery.
@mcp.tool()
async def find_string_literals(
    pattern: str,
    regex: bool = False,
    case_sensitive: bool = False,
    package: str = "",
    max_literal_len: int = 256,
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    ctx: Context = None,
) -> dict:
    """Find string literals (\"...\") whose value matches `pattern`. Returns line-level hits with snippets.

    Faster and more precise than `search_classes_by_keyword(search_in="code")` because it
    matches ONLY inside literals — eliminating false hits inside identifiers/method bodies.
    Use this first when chasing URLs, intent extras, deep links, error messages,
    config keys, or any other behavioral fingerprint.

    Args:
        pattern: Substring (default) or Java regex (when regex=True).
        regex: Treat `pattern` as a regex. Default False.
        case_sensitive: Default False.
        package: Optional package prefix filter.
        max_literal_len: Skip literals longer than this (default 256, avoids data blobs).
        max_hits: Hard cap on total hits collected before truncation (default 5000,
            absolute ceiling 50000). When the cap is reached the response includes
            `truncated: true`.
        offset, count: Pagination over the (capped) result set.
    """
    report_progress = ctx.report_progress if ctx else None
    return await _adv_find_string_literals(
        pattern=pattern, regex=regex, case_sensitive=case_sensitive,
        package=package, max_literal_len=max_literal_len, max_hits=max_hits,
        offset=offset, count=count, report_progress=report_progress,
    )


@mcp.tool()
async def grep_code(
    pattern: str,
    regex: bool = False,
    case_sensitive: bool = False,
    context: int = 1,
    package: str = "",
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    ctx: Context = None,
) -> dict:
    """Full-source regex grep with line-snippet context. Returns one entry per matching line.

    Unlike `search_classes_by_keyword` which only returns matching class names, this
    returns each individual line hit with surrounding context — dramatically reducing
    the round-trips needed to drill into a finding.

    Args:
        pattern: Substring (default) or Java regex.
        regex: Treat `pattern` as a regex.
        case_sensitive: Default False.
        context: Lines of context around each hit (0-10, default 1).
        package: Optional package prefix filter.
        max_hits: Hard cap on total hits collected before truncation (default 5000,
            absolute ceiling 50000). When the cap is reached the response includes
            `truncated: true`.
        offset, count: Pagination over the (capped) result set.
    """
    report_progress = ctx.report_progress if ctx else None
    return await _adv_grep_code(
        pattern=pattern, regex=regex, case_sensitive=case_sensitive,
        context=context, package=package, max_hits=max_hits,
        offset=offset, count=count, report_progress=report_progress,
    )


@mcp.tool()
async def find_methods_by_signature(
    name_pattern: str = "",
    return_type: str = "",
    param_types: str = "",
    param_count: int = -1,
    class_pattern: str = "",
    package: str = "",
    offset: int = 0,
    count: int = 50,
    ctx: Context = None,
) -> dict:
    """Filter methods by structural signature using smali metadata (no decompilation needed).

    All filters AND-combine; an empty/omitted filter means \"any\". At least one filter required.

    Args:
        name_pattern: Regex on method name (case-insensitive).
        return_type: Substring of smali return descriptor. Examples: \"Z\" (boolean),
            \"Ljava/lang/String;\", \"Landroid/content/Intent;\", \"[B\" (byte[]),
            \"Intent;\" (any *Intent).
        param_types: Comma-separated substrings; ALL must appear in param list.
            Examples: \"Ljava/lang/String;\" (one String), \"String,Intent\" (one each),
            \"android/net/Uri\" (any Uri param).
        param_count: Exact arg count. Pass -1 (default) for \"any\".
        class_pattern: Regex on containing class FQN.
        package: Faster alternative when only a package prefix filter is needed.
        offset, count: Pagination.

    Returns: items: [{class, method, params, return_type, access}].
    """
    report_progress = ctx.report_progress if ctx else None
    return await _adv_find_methods_by_signature(
        name_pattern=name_pattern, return_type=return_type,
        param_types=param_types,
        param_count=(None if param_count is None or param_count < 0 else param_count),
        class_pattern=class_pattern, package=package,
        offset=offset, count=count, report_progress=report_progress,
    )


@mcp.tool()
async def find_string_constant_dispatchers(
    getter_methods: str = "optString,getString,getAction,getType,getScheme",
    package: str = "",
    max_hits: int = 5000,
    offset: int = 0,
    count: int = 50,
    ctx: Context = None,
) -> dict:
    """Find methods that branch on a string returned by a known "key getter".

    Smali-only scan (no decompile pass) — designed for the very common RE
    pattern of finding metadata/event/action dispatchers such as:

        String cls = json.optString("CLASS", "");
        switch (cls) {
            case "twitch-stitched-ad": ...
            case "twitch-maf-ad": ...
        }

    or

        String action = intent.getAction();
        if ("ACTION_FOO".equals(action)) { ... }

    For each matching method returns the dispatch key (the const-string
    argument to the getter, e.g. "CLASS") AND every string literal
    compared against the value via String.equals / equalsIgnoreCase.
    Both `switch(String)` and if/else chains lower to the same equals
    pattern, so a single scan catches both.

    Use this BEFORE chasing classes by name — it collapses the multi-turn
    "find dispatcher → enumerate cases → xref each case" workflow into one.

    Args:
        getter_methods: Comma-separated method-name filter for the dispatch
            source (default catches the most common Android/JSON keys).
            Add e.g. "get" to widen, restrict to "optString" to narrow.
        package: Optional package prefix filter.
        max_hits: Cap on dispatcher methods (absolute ceiling 50000).
        offset, count: Pagination over the (capped) result set.

    Returns: standardized envelope wrapping
        items: [{class, method, params, return_type, access,
                 key_getter, getter_owner, key_literal, cases, case_count}]
    """
    report_progress = ctx.report_progress if ctx else None
    return _envelope_from_jadx(
        await _adv_find_string_constant_dispatchers(
            getter_methods=getter_methods, package=package, max_hits=max_hits,
            offset=offset, count=count, report_progress=report_progress,
        )
    )


@mcp.tool()
async def get_callees(
    class_name: str,
    method_name: str,
    param_signature: str = "",
) -> dict:
    """List every method invoked by the given method (outbound call graph).

    Inverse of `get_xrefs_to_method`. Critical for tracing forward through obfuscated
    helper chains to find the real Android API call at the leaf.

    Args:
        class_name: Fully-qualified class name.
        method_name: Method name.
        param_signature: Optional smali parameter descriptor for overload disambiguation
            (e.g. ``"Ljava/lang/String;I"``). Empty = first overload wins.

    Returns: {target_class, target_method, callee_count, callees: [{class, method, params, return_type, opcode}]}.
    """
    return await _adv_get_callees(class_name, method_name, param_signature=param_signature)


@mcp.tool()
async def get_subclasses(
    class_name: str, transitive: bool = False, offset: int = 0, count: int = 100
) -> dict:
    """List classes that extend the given class.

    Args:
        class_name: Fully-qualified class name (Java dotted form).
        transitive: If True, include sub-subclasses recursively. Default False (direct only).
        offset, count: Pagination.
    """
    return await _adv_get_subclasses(class_name, transitive=transitive, offset=offset, count=count)


@mcp.tool()
async def get_superclasses(class_name: str) -> dict:
    """Walk the class's ancestor chain and list its directly-implemented interfaces.

    Use to resolve an obfuscated class to its framework type (e.g. confirm a single-letter
    obfuscated class is really an `AppCompatActivity` subclass).

    Returns: {class, super_chain (closest first, java.lang.Object last), direct_interfaces}.
    """
    return await _adv_get_superclasses(class_name)


@mcp.tool()
async def get_implementations(
    interface_name: str, offset: int = 0, count: int = 100
) -> dict:
    """List every class that implements the given interface (directly OR via a parent).

    Args:
        interface_name: Fully-qualified interface name.
        offset, count: Pagination.
    """
    return await _adv_get_implementations(interface_name, offset=offset, count=count)


@mcp.tool()
async def find_android_components_deep(
    component_type: str, offset: int = 0, count: int = 100
) -> dict:
    """Find Android components by descending from framework base classes.

    Catches components NOT registered in AndroidManifest.xml — Fragments, dynamically
    registered receivers, abstract base activities, custom WebView clients, etc. —
    which `get_manifest_component` cannot see. App-package classes returned BEFORE library
    classes (heuristic sort).

    Args:
        component_type: One of:
            activity        — android.app.Activity + AppCompat / Fragment / Component variants
            fragment        — android.app.Fragment + androidx + support-v4
            service         — Service + IntentService + JobService + JobIntentService
            receiver        — android.content.BroadcastReceiver
            provider        — android.content.ContentProvider
            application     — android.app.Application
            webview-client  — WebViewClient + WebChromeClient
            webview         — android.webkit.WebView subclasses
        offset, count: Pagination.
    """
    return await _adv_find_android_components_deep(component_type, offset=offset, count=count)


def main():
    parser = argparse.ArgumentParser("MCP Server for Jadx")
    parser.add_argument(
        "--http",
        help="Serve MCP Server over HTTP stream.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--host",
        help="Host address to bind for --http (default: 127.0.0.1, use 0.0.0.0 for remote access). "
             "WARNING: non-localhost binds expose the server over plain HTTP with no authentication.",
        default="127.0.0.1",
        type=str
    )
    parser.add_argument(
        "--port", help="Port for --http (default:8651)", default=8651, type=int
    )
    parser.add_argument(
        "--jadx-port",
        help="JADX AI MCP Plugin port (default:8650)",
        default=8650,
        type=int,
    )
    parser.add_argument(
        "--jadx-host",
        help="JADX AI MCP Plugin host (default:127.0.0.1). "
             "Security: non-localhost may expose plugin to network; use trusted network/firewall.",
        default="127.0.0.1",
        type=str,
    )
    args = parser.parse_args()

    # Configure
    config.set_jadx_host(args.jadx_host)
    config.set_jadx_port(args.jadx_port)

    # Security warning for non-localhost bind address
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "\n⚠️  SECURITY WARNING: Binding to non-localhost address '%s'.\n"
            "   The MCP server uses plain HTTP with NO authentication.\n"
            "   Anyone on the network can connect and use all MCP tools.\n"
            "   Only use this on trusted networks or behind a firewall.",
            args.host
        )

    # Banner & Health Check — always logs to stderr to keep stdout clean for stdio transport
    try:
        logger.info(jadx_mcp_server_banner())
    except Exception:
        logger.info(
            "[JADX AI MCP Server] v3.3.5 | MCP Port: %s | JADX Host: %s | JADX Port: %s",
            args.port,
            args.jadx_host,
            args.jadx_port,
        )

    logger.info("Testing JADX AI MCP Plugin connectivity...")
    result = config.health_ping()
    logger.info("Health check result: %s", result)

    # Run Server
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        # StdIO transport must keep stdout reserved for MCP frames.
        mcp.run()


if __name__ == "__main__":
    main()
