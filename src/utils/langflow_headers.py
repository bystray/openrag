"""Utility functions for building Langflow request headers."""

from typing import Any, Dict, Optional

from utils.container_utils import transform_localhost_url


def preview_token_safe(token: Optional[str], prefix_len: int = 8) -> str:
    """Short non-secret preview for logs (never log full JWT/API keys)."""
    if not token:
        return "(empty)"
    t = str(token).strip()
    if len(t) <= prefix_len:
        return "(short)"
    return f"{t[:prefix_len]}…(len={len(t)})"


def set_langflow_jwt_headers(headers: Dict[str, str], jwt_token: Optional[str]) -> None:
    """Pass user JWT into Langflow global variable ``JWT`` for OpenSearch / flows.

    Langflow accepts global-var headers in multiple casings depending on version
    and client; ingestion uses ``X-Langflow-Global-Var-*`` (see langflow_file_service).
    Chat previously sent only ``X-LANGFLOW-GLOBAL-VAR-JWT``, which can fail to merge
    into the flow — OpenSearch node then keeps placeholder ``jwt_token`` → 401.
    """
    if not jwt_token:
        return
    # Canonical (matches Langflow docs / ingest path)
    headers["X-Langflow-Global-Var-JWT"] = jwt_token
    # Alternate casing used by chat client paths
    headers["X-LANGFLOW-GLOBAL-VAR-JWT"] = jwt_token


def log_langflow_extra_headers(logger: Any, message: str, headers: Dict[str, str]) -> None:
    """Log Langflow global-var header keys and JWT preview only (no secrets)."""
    jwt_preview = preview_token_safe(
        headers.get("X-Langflow-Global-Var-JWT")
        or headers.get("X-LANGFLOW-GLOBAL-VAR-JWT")
    )
    logger.info(message, header_keys=sorted(headers.keys()), jwt_header_preview=jwt_preview)


def add_provider_credentials_to_headers(headers: Dict[str, str], config) -> None:
    """Add provider credentials to headers as Langflow global variables.
    
    Args:
        headers: Dictionary of headers to add credentials to
        config: OpenRAGConfig object containing provider configurations
    """
    # Add OpenAI credentials
    if config.providers.openai.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-OPENAI_API_KEY"] = str(config.providers.openai.api_key)
    
    # Add Anthropic credentials
    if config.providers.anthropic.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-ANTHROPIC_API_KEY"] = str(config.providers.anthropic.api_key)
    
    # Add WatsonX credentials
    if config.providers.watsonx.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-WATSONX_APIKEY"] = str(config.providers.watsonx.api_key)
    
    if config.providers.watsonx.project_id:
        headers["X-LANGFLOW-GLOBAL-VAR-WATSONX_PROJECT_ID"] = str(config.providers.watsonx.project_id)
    
    # Add Ollama endpoint (with localhost transformation)
    if config.providers.ollama.endpoint:
        ollama_endpoint = transform_localhost_url(config.providers.ollama.endpoint, is_langflow=True)
        headers["X-LANGFLOW-GLOBAL-VAR-OLLAMA_BASE_URL"] = str(ollama_endpoint)


def build_mcp_global_vars_from_config(config) -> Dict[str, str]:
    """Build MCP global variables dictionary from OpenRAG configuration.
    
    Args:
        config: OpenRAGConfig object containing provider configurations
        
    Returns:
        Dictionary of global variables for MCP servers (without X-Langflow-Global-Var prefix)
    """
    global_vars = {}
    
    # Add OpenAI credentials
    if config.providers.openai.api_key:
        global_vars["OPENAI_API_KEY"] = config.providers.openai.api_key
    
    # Add Anthropic credentials
    if config.providers.anthropic.api_key:
        global_vars["ANTHROPIC_API_KEY"] = config.providers.anthropic.api_key
    
    # Add WatsonX credentials
    if config.providers.watsonx.api_key:
        global_vars["WATSONX_APIKEY"] = config.providers.watsonx.api_key
    
    if config.providers.watsonx.project_id:
        global_vars["WATSONX_PROJECT_ID"] = config.providers.watsonx.project_id
    
    # Add Ollama endpoint (with localhost transformation)
    if config.providers.ollama.endpoint:
        ollama_endpoint = transform_localhost_url(config.providers.ollama.endpoint, is_langflow=True)
        global_vars["OLLAMA_BASE_URL"] = ollama_endpoint
    
    # Add selected embedding model
    if config.knowledge.embedding_model:
        global_vars["SELECTED_EMBEDDING_MODEL"] = config.knowledge.embedding_model
    
    return global_vars

