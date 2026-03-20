"""
Utility functions for OpenSearch index naming in multi-model setup.

Documents with different embedding models are written to separate indices
(e.g. documents_text_embedding_3_small, documents_text_embedding_3_large).
Search uses an alias that spans all model-specific indices.
"""

from utils.embedding_fields import normalize_model_name
from utils.logging_config import get_logger

logger = get_logger(__name__)


def get_index_name_for_model(base: str, model: str) -> str:
    """
    Get the model-specific index name.

    Args:
        base: Base index name (alias), e.g. "documents"
        model: Embedding model name, e.g. "text-embedding-3-small"

    Returns:
        Index name like "documents_text_embedding_3_small"
    """
    if not model or not model.strip():
        return base
    normalized = normalize_model_name(model.strip())
    return f"{base}_{normalized}"


async def ensure_documents_alias(opensearch_client, alias_name: str, model_index_name: str):
    """
    Ensure alias points to all document indices (legacy + model-specific).
    Supports migration: legacy index 'documents' + new model indices 'documents_*'.
    """
    try:
        target_indices = set()
        target_indices.add(model_index_name)

        try:
            meta = await opensearch_client.indices.get(index=alias_name)
            if alias_name in meta:
                target_indices.add(alias_name)
        except Exception:
            pass

        try:
            resp = await opensearch_client.cat.indices(
                index=f"{alias_name}_*",
                format="json",
                h="index",
            )
            for entry in resp:
                target_indices.add(entry["index"])
        except Exception:
            pass

        if not target_indices:
            return

        try:
            current = await opensearch_client.indices.get_alias(name=alias_name)
            current_indices = set(current.keys())
        except Exception:
            current_indices = set()

        actions = []
        for idx in current_indices - target_indices:
            actions.append({"remove": {"index": idx, "alias": alias_name}})
        for idx in target_indices - current_indices:
            actions.append({"add": {"index": idx, "alias": alias_name}})

        if actions:
            await opensearch_client.indices.update_aliases(body={"actions": actions})
            logger.debug(
                "Updated documents alias",
                alias_name=alias_name,
                indices=list(target_indices),
            )
    except Exception as e:
        logger.warning(
            "Failed to update documents alias",
            error=str(e),
            alias_name=alias_name,
        )


async def ensure_index_exists_for_model(opensearch_client, embedding_model: str):
    """
    Ensure model-specific index exists. Creates index and updates alias if needed.
    Call before first write with a new embedding model.
    """
    from config.settings import get_index_name, get_openrag_config
    from utils.embeddings import create_dynamic_index_body

    base = get_openrag_config().knowledge.index_name
    model_index_name = get_index_name_for_model(base, embedding_model)

    if await opensearch_client.indices.exists(index=model_index_name):
        return

    config = get_openrag_config()
    provider = config.knowledge.embedding_provider
    provider_config = config.get_embedding_provider_config()
    endpoint = getattr(provider_config, "endpoint", None)

    dynamic_index_body = await create_dynamic_index_body(
        embedding_model,
        provider=provider,
        endpoint=endpoint,
    )
    await opensearch_client.indices.create(
        index=model_index_name, body=dynamic_index_body
    )
    logger.info(
        "Created OpenSearch index for model (on-demand)",
        index_name=model_index_name,
        embedding_model=embedding_model,
    )
    await ensure_documents_alias(opensearch_client, base, model_index_name)
