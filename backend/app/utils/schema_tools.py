"""JSON Schema inference, OpenAPI import and curl parsing.

Replaces the reference stack's ``generate-schema``, ``to-json-schema`` and
``curlconverter`` npm dependencies with equivalents that have no third-party
requirements beyond PyYAML.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any
from urllib.parse import parse_qsl, urlparse

import yaml

from app.core.exceptions import ValidationError

# --------------------------------------------------------- schema inference
_PY_TO_JSON = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    type(None): "null",
}


def infer_schema(sample: Any) -> dict[str, Any]:
    """Derive a draft-07 JSON Schema from one example document."""
    return {"$schema": "http://json-schema.org/draft-07/schema#", **_infer(sample)}


def _infer(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        properties = {key: _infer(val) for key, val in value.items()}
        # Everything present in the sample is treated as required; the admin
        # trims the list afterwards in the schema editor.
        required = [key for key, val in value.items() if val is not None]
        return {"type": "object", "properties": properties, "required": required}
    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {}}
        merged = _merge([_infer(item) for item in value])
        return {"type": "array", "items": merged}
    json_type = _PY_TO_JSON.get(type(value), "string")
    node: dict[str, Any] = {"type": json_type}
    if json_type == "string" and isinstance(value, str):
        fmt = _guess_format(value)
        if fmt:
            node["format"] = fmt
    return node


def _merge(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse the per-item schemas of an array into one."""
    if not nodes:
        return {}
    first = nodes[0]
    if all(node == first for node in nodes):
        return first
    if all(node.get("type") == "object" for node in nodes):
        properties: dict[str, Any] = {}
        for node in nodes:
            for key, sub in (node.get("properties") or {}).items():
                properties.setdefault(key, sub)
        # A key missing from any sample item cannot be required.
        required = set(nodes[0].get("required", []))
        for node in nodes[1:]:
            required &= set(node.get("required", []))
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(required),
        }
    types = sorted({node.get("type", "string") for node in nodes})
    return {"type": types if len(types) > 1 else types[0]}


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _guess_format(value: str) -> str | None:
    if _ISO_DATETIME.match(value):
        return "date-time"
    if _ISO_DATE.match(value):
        return "date"
    if _EMAIL.match(value):
        return "email"
    if _UUID.match(value):
        return "uuid"
    if value.startswith(("http://", "https://")):
        return "uri"
    return None


# ------------------------------------------------------------ spec parsing
def parse_spec(text: str) -> dict[str, Any]:
    """Load an OpenAPI document given as JSON or YAML."""
    text = (text or "").strip()
    if not text:
        raise ValidationError("Specification is empty.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValidationError("Specification is not valid JSON or YAML.") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("Specification must be a JSON or YAML object.")
    return parsed


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def endpoints_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an OpenAPI document into importable endpoint records."""
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        raise ValidationError("Specification has no usable 'paths' section.")

    components = spec.get("components", {}).get("schemas", {})
    shared_responses = spec.get("components", {}).get("responses", {})
    results: list[dict[str, Any]] = []

    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        shared_params = operations.get("parameters") or []
        for method, operation in operations.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            params = list(shared_params) + list(operation.get("parameters") or [])
            results.append(
                {
                    "endpoint_url": path,
                    "method": method.upper(),
                    "display_name": operation.get("summary")
                    or operation.get("operationId")
                    or f"{method.upper()} {path}",
                    "description": operation.get("description"),
                    "path_params": _params_by_location(params, "path"),
                    "query_params": _params_by_location(params, "query"),
                    "header_params": _params_by_location(params, "header"),
                    "request_schema": _request_schema(operation, components),
                    "request_sample": _example_from_schema(
                        _request_schema(operation, components), components
                    ),
                    "responses": _responses(operation, components, shared_responses),
                    "api_keywords": operation.get("tags") or [],
                }
            )
    return results


def _params_by_location(params: list[Any], location: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for param in params:
        if not isinstance(param, dict) or param.get("in") != location:
            continue
        out[param.get("name", "")] = {
            "required": bool(param.get("required")),
            "schema": param.get("schema") or {"type": "string"},
            "description": param.get("description"),
        }
    return out


def _request_schema(
    operation: dict[str, Any], components: dict[str, Any]
) -> dict[str, Any] | None:
    content = (operation.get("requestBody") or {}).get("content") or {}
    media = content.get("application/json") or next(iter(content.values()), None)
    if not isinstance(media, dict):
        return None
    return _resolve_refs(media.get("schema"), components)


def _responses(
    operation: dict[str, Any],
    components: dict[str, Any],
    shared_responses: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for status, response in (operation.get("responses") or {}).items():
        if not isinstance(response, dict):
            continue
        # Shared responses: ``$ref: '#/components/responses/401Unauthorized'``.
        ref = response.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/responses/"):
            response = (shared_responses or {}).get(ref.rsplit("/", 1)[-1]) or {}
        content = response.get("content") or {}
        media = content.get("application/json") or next(iter(content.values()), None)
        schema = (
            _resolve_refs(media.get("schema"), components)
            if isinstance(media, dict)
            else None
        )
        out.append(
            {
                "status_code": str(status),
                "description": response.get("description"),
                "res_schema": schema,
                "res_json": _example_from_schema(schema, components),
            }
        )
    return out


def _resolve_refs(schema: Any, components: dict[str, Any], depth: int = 0) -> Any:
    """Inline ``$ref`` pointers so stored schemas are self-contained.

    Bounded depth keeps a recursive model (a tree node referencing itself)
    from looping forever.
    """
    if depth > 8 or schema is None:
        return schema
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            target = components.get(ref.rsplit("/", 1)[-1])
            return _resolve_refs(target, components, depth + 1) if target else {}
        resolved = {
            key: _resolve_refs(val, components, depth + 1)
            for key, val in schema.items()
        }
        return _merge_all_of(resolved)
    if isinstance(schema, list):
        return [_resolve_refs(item, components, depth + 1) for item in schema]
    return schema


def _merge_all_of(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten ``allOf`` into one object schema.

    Envelopes are commonly written as ``allOf: [StandardResponse, {data: ...}]``;
    merging lets the field tree and the sample generator see one object, with
    later parts overriding earlier ones (as the more specific definition).
    """
    parts = schema.get("allOf")
    if not isinstance(parts, list) or not all(isinstance(p, dict) for p in parts):
        return schema
    merged: dict[str, Any] = {k: v for k, v in schema.items() if k != "allOf"}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for part in [*parts, merged]:
        properties.update(part.get("properties") or {})
        required += [r for r in part.get("required") or [] if r not in required]
        for key, value in part.items():
            if key not in ("properties", "required", "allOf"):
                merged.setdefault(key, value)
    if properties:
        merged["properties"] = properties
        merged.setdefault("type", "object")
    if required:
        merged["required"] = required
    return merged


_TYPE_EXAMPLES = {
    "string": "string",
    "integer": 0,
    "number": 0,
    "boolean": True,
    "null": None,
}


def _example_from_schema(
    schema: Any, components: dict[str, Any], depth: int = 0
) -> Any:
    """Build a filled-in sample body so "try it" opens with something usable."""
    if depth > 6 or not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    schema = _resolve_refs(schema, components, depth)
    if not isinstance(schema, dict):
        return None
    if "default" in schema:
        return schema["default"]

    # Optional fields are usually ``anyOf: [<real type>, null]``; sample the
    # first alternative that is not null.
    alternatives = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(alternatives, list) and alternatives:
        chosen = next(
            (alt for alt in alternatives if not (isinstance(alt, dict) and alt.get("type") == "null")),
            alternatives[0],
        )
        return _example_from_schema(chosen, components, depth + 1)

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        return {
            key: _example_from_schema(sub, components, depth + 1)
            for key, sub in (schema.get("properties") or {}).items()
        }
    if schema_type == "array":
        item = _example_from_schema(schema.get("items"), components, depth + 1)
        return [item] if item is not None else []
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if schema.get("format") == "date":
        return "2026-01-01"
    if schema.get("format") == "date-time":
        return "2026-01-01T00:00:00Z"
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), "string")
    return _TYPE_EXAMPLES.get(schema_type or "string", "string")


# ------------------------------------------------------------ curl parsing
def parse_curl(command: str) -> dict[str, Any]:
    """Turn a pasted curl command into the try-it console's field set."""
    text = (command or "").strip()
    if not text:
        raise ValidationError("Curl command is empty.")
    # Join shell line continuations before tokenising.
    text = re.sub(r"\\\s*\n", " ", text)
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise ValidationError("Curl command could not be parsed.") from exc

    if not tokens or tokens[0] != "curl":
        raise ValidationError("Command must start with 'curl'.")

    url = ""
    method = ""
    headers: dict[str, str] = {}
    body: Any = None
    index = 1

    while index < len(tokens):
        token = tokens[index]
        if token in {"-X", "--request"} and index + 1 < len(tokens):
            method = tokens[index + 1].upper()
            index += 2
        elif token in {"-H", "--header"} and index + 1 < len(tokens):
            key, _, value = tokens[index + 1].partition(":")
            headers[key.strip()] = value.strip()
            index += 2
        elif token in {
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
        } and index + 1 < len(tokens):
            raw = tokens[index + 1]
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = dict(parse_qsl(raw)) or raw
            index += 2
        elif token in {"-u", "--user"} and index + 1 < len(tokens):
            headers["Authorization"] = f"Basic {tokens[index + 1]}"
            index += 2
        elif token.startswith("-"):
            index += 1  # flags without values (-s, -k, --compressed, ...)
        else:
            url = token
            index += 1

    if not url:
        raise ValidationError("Curl command does not contain a URL.")

    parsed = urlparse(url)
    return {
        "method": method or ("POST" if body is not None else "GET"),
        "url": url,
        "path": parsed.path,
        "headers": headers,
        "query_params": dict(parse_qsl(parsed.query)),
        "body": body,
    }


def build_code_sample(
    language: str,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
) -> str:
    """Render a copy-pasteable client snippet for the API reference page."""
    payload = json.dumps(body, indent=2) if body is not None else ""
    method = (method or "GET").upper()

    if language == "curl":
        parts = [f"curl -X {method} '{url}'"]
        parts += [f"  -H '{key}: {value}'" for key, value in headers.items()]
        if body is not None:
            parts.append(f"  -d '{json.dumps(body)}'")
        return " \\\n".join(parts)

    if language == "python":
        lines = ["import requests", "", f"url = {url!r}", f"headers = {headers!r}"]
        if body is not None:
            lines.append(f"payload = {body!r}")
            lines.append(
                f"response = requests.{method.lower()}(url, json=payload, headers=headers)"
            )
        else:
            lines.append(f"response = requests.{method.lower()}(url, headers=headers)")
        lines.append("print(response.status_code, response.json())")
        return "\n".join(lines)

    if language == "javascript":
        init = {"method": method, "headers": headers}
        init_json = json.dumps(init, indent=2)
        if body is not None:
            init_json = (
                init_json[:-1].rstrip() + f",\n  body: JSON.stringify({payload})\n}}"
            )
        return (
            f"const response = await fetch({json.dumps(url)}, {init_json});\n"
            "const data = await response.json();\n"
            "console.log(response.status, data);"
        )

    if language == "go":
        body_arg = (
            f"bytes.NewBuffer([]byte(`{json.dumps(body)}`))"
            if body is not None
            else "nil"
        )
        header_lines = "".join(
            f'req.Header.Set("{key}", "{value}")\n' for key, value in headers.items()
        )
        return (
            f'req, _ := http.NewRequest("{method}", "{url}", {body_arg})\n'
            f"{header_lines}"
            "resp, err := http.DefaultClient.Do(req)"
        )

    if language == "php":
        return (
            "$ch = curl_init();\n"
            f"curl_setopt($ch, CURLOPT_URL, {json.dumps(url)});\n"
            f"curl_setopt($ch, CURLOPT_CUSTOMREQUEST, {json.dumps(method)});\n"
            "curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n"
            + (
                f"curl_setopt($ch, CURLOPT_POSTFIELDS, {json.dumps(json.dumps(body))});\n"
                if body is not None
                else ""
            )
            + "$response = curl_exec($ch);\ncurl_close($ch);"
        )

    if language == "java":
        return (
            "HttpRequest request = HttpRequest.newBuilder()\n"
            f"    .uri(URI.create({json.dumps(url)}))\n"
            + "".join(
                f"    .header({json.dumps(k)}, {json.dumps(v)})\n"
                for k, v in headers.items()
            )
            + (
                f"    .method({json.dumps(method)}, "
                f"HttpRequest.BodyPublishers.ofString({json.dumps(json.dumps(body))}))\n"
                if body is not None
                else f"    .method({json.dumps(method)}, HttpRequest.BodyPublishers.noBody())\n"
            )
            + "    .build();"
        )

    if language == "csharp":
        return (
            "using var client = new HttpClient();\n"
            f"var request = new HttpRequestMessage(new HttpMethod({json.dumps(method)}), "
            f"{json.dumps(url)});\n"
            + "".join(
                f"request.Headers.Add({json.dumps(k)}, {json.dumps(v)});\n"
                for k, v in headers.items()
            )
            + (
                f"request.Content = new StringContent({json.dumps(json.dumps(body))}, "
                'Encoding.UTF8, "application/json");\n'
                if body is not None
                else ""
            )
            + "var response = await client.SendAsync(request);"
        )

    raise ValidationError(f"Unsupported language '{language}'.")
