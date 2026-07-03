"""
T2.12 (AMENDMENT-005): Compose-and-run engine.

Reads process specs from config/processes.yaml and assembles LLM calls:
- Resolves business config fields
- Assembles module context via context_assembly (views.yaml)
- Runs dynamic variable builders (existing_ideas, kill_lessons, etc.)
- Applies transforms (join_comma, truncate_N, json_truncate_N)
- Calls adapter.complete() with the assembled variables + schema + backend

Routes contain zero inline module wiring — they call:
    result, prov = compose_and_run("ideas_generate", business_slug, dynamic_vars, ...)
"""

import os
import json
import yaml
import importlib
from typing import Any


class ProcessError(Exception):
    """Process registry or composition error."""
    pass


def load_process_registry(config_dir: str = "config") -> dict:
    """Load config/processes.yaml. Returns the parsed dict."""
    path = os.path.join(config_dir, "processes.yaml")
    if not os.path.exists(path):
        raise ProcessError(f"processes.yaml not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data or "processes" not in data:
        raise ProcessError("processes.yaml missing 'processes' key")
    return data


def _resolve_schema(schema_ref: str, registry: dict, inline_schemas: dict = None):
    """Resolve a schema reference to a JSON schema dict.
    Format: 'module.Class' or 'inline:name'"""
    schemas = registry.get("schemas", {})
    if schema_ref not in schemas:
        raise ProcessError(f"Schema '{schema_ref}' not found in registry")

    ref = schemas[schema_ref]

    if ref.startswith("inline:"):
        name = ref.split("inline:")[1]
        if inline_schemas and name in inline_schemas:
            return inline_schemas[name]
        raise ProcessError(f"Inline schema '{name}' not provided")

    # module.Class format — import dynamically
    parts = ref.rsplit(".", 1)
    if len(parts) == 2:
        module_path, class_name = parts
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    raise ProcessError(f"Cannot resolve schema ref: {ref}")


def _apply_transform(value: Any, transform: str) -> str:
    """Apply a named transform to a value."""
    if transform == "join_comma":
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)
    elif transform == "join_newline_bullet":
        if isinstance(value, list):
            return "\n".join(f"- {v}" for v in value)
        return str(value)
    elif transform.startswith("truncate_"):
        limit = int(transform.split("_")[1])
        if isinstance(value, str):
            return value[:limit]
        return str(value)[:limit]
    elif transform.startswith("json_truncate_"):
        limit = int(transform.split("_")[2])
        if isinstance(value, (dict, list)):
            return json.dumps(value)[:limit]
        return str(value)[:limit]
    return str(value) if value is not None else ""


def _resolve_input(spec: dict, business: dict, dynamic: dict,
                   builders: dict, module_vars: dict) -> Any:
    """Resolve a single input from its spec."""
    source = spec.get("source", "dynamic")
    field = spec.get("field")
    transform = spec.get("transform")
    default = spec.get("default")
    template = spec.get("template")
    builder_name = spec.get("builder")
    value = spec.get("value")

    # Resolve by source
    if source == "static":
        result = value
    elif source == "business":
        # Navigate dotted path: "business.name" → business["business"]["name"]
        parts = field.split(".")
        result = business
        for part in parts:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                result = None
                break
        if result is None and default is not None:
            result = default
    elif source == "dynamic":
        if builder_name and builder_name in builders:
            result = builders[builder_name]()
        elif field and field in dynamic:
            result = dynamic[field]
        elif default is not None:
            result = default
        else:
            result = dynamic.get(field, "")
    elif source == "module_views":
        # module_vars is already assembled — just pass through
        return module_vars  # special: gets spread into variables
    else:
        result = default if default is not None else ""

    # Apply template
    if template and isinstance(result, str):
        try:
            result = template.format(**dynamic)
        except (KeyError, IndexError):
            pass

    # Apply transform
    if transform:
        result = _apply_transform(result, transform)

    return result


def compose_and_run(
    process_name: str,
    business_slug: str,
    dynamic: dict,
    models_config: dict,
    db_path: str = "data/viralfactory.db",
    config_dir: str = "config",
    modules_dir: str = "modules",
    prompts_dir: str = "prompts",
    builders: dict = None,
    inline_schemas: dict = None,
    business_config: dict = None,
    adapter=None,
):
    """Compose and run a process from the registry.

    Args:
        process_name: key in processes.yaml (e.g. "ideas_generate")
        business_slug: for module context assembly
        dynamic: dict of dynamic variables from the route
        models_config: models config dict (for adapter)
        db_path: SQLite DB path
        config_dir: config directory path
        modules_dir: modules directory
        prompts_dir: prompts directory
        builders: dict of {builder_name: callable} for dynamic variable builders
        inline_schemas: dict of {name: schema_dict} for inline schemas
        business_config: pre-loaded business config (skip re-loading if provided)
        adapter: pre-created LLMAdapter (skip creation if provided)

    Returns:
        (result_dict, provenance_summary)
    """
    registry = load_process_registry(config_dir)
    processes = registry["processes"]

    if process_name not in processes:
        raise ProcessError(f"Process '{process_name}' not found in processes.yaml")

    spec = processes[process_name]
    prompt_file = spec["prompt_file"]
    backend = spec.get("backend", "default")
    schema_ref = spec.get("schema")
    context_template = spec.get("context_template", process_name)
    inputs_spec = spec.get("inputs", {})

    # Load business config if not provided
    if business_config is None:
        from config_loader import load_all, ConfigError
        try:
            config = load_all(config_dir)
            business_config = config["business"]
        except ConfigError as e:
            raise ProcessError(f"Config error: {e}")

    # Assemble module context
    from context_assembly import assemble_module_context
    module_vars, module_prov = assemble_module_context(
        prompt_file, business_slug,
        dynamic=dynamic,
        db_path=db_path, modules_dir=modules_dir, prompts_dir=prompts_dir,
    )

    # Build variables
    builders = builders or {}
    variables = {}

    for var_name, input_spec in inputs_spec.items():
        # Handle plain string values (e.g. module_views: "prompt_file")
        if isinstance(input_spec, str):
            if var_name == "module_views":
                variables.update(module_vars)
            continue
        if input_spec.get("source") == "module_views":
            # Spread module context variables
            variables.update(module_vars)
        else:
            value = _resolve_input(input_spec, business_config, dynamic, builders, module_vars)
            variables[var_name] = value

    # Resolve schema
    schema = None
    if schema_ref:
        schema = _resolve_schema(schema_ref, registry, inline_schemas)

    # Build context string
    format_ctx = {"module_prov": module_prov, "business_slug": business_slug}
    format_ctx.update({k: v for k, v in dynamic.items() if isinstance(v, (str, int))})
    format_ctx.update({k: v for k, v in variables.items() if isinstance(v, (str, int)) and k not in format_ctx})
    try:
        context = context_template.format(**format_ctx)
    except (KeyError, IndexError):
        context = f"{process_name} | module_ctx: {module_prov}"

    # Create adapter if not provided
    if adapter is None:
        from llm_adapter import LLMAdapter
        adapter = LLMAdapter(models_config, db_path=db_path, prompts_dir=prompts_dir)

    # Run the LLM call
    result = adapter.complete(
        prompt_file=prompt_file,
        variables=variables,
        schema=schema,
        backend=backend,
        context=context,
        business_slug=business_slug,
    )

    return result, module_prov