import pytest
from unittest.mock import AsyncMock, Mock, patch

from api.upload import normalize_path as upload_normalize_path
from models.processors import DocumentFileProcessor, TaskProcessor
from services.task_service import TaskService
from utils.embeddings import create_dynamic_index_body


def test_normalize_path_rules():
    assert upload_normalize_path(r".\docs\\finance//a.pdf/") == "docs/finance/a.pdf"
    assert upload_normalize_path("./docs//x.pdf") == "docs/x.pdf"


@pytest.mark.asyncio
async def test_task_service_sets_filetask_relative_path():
    service = TaskService(document_service=Mock())
    processor = Mock()
    processor.__class__.__name__ = "DummyProcessor"

    with patch("asyncio.create_task") as create_task_mock:
        fake_task = Mock()
        fake_task.add_done_callback = Mock()
        create_task_mock.return_value = fake_task

        task_id = await service.create_custom_task(
            user_id="u1",
            items=["/tmp/docs/a.pdf"],
            processor=processor,
            relative_paths={"/tmp/docs/a.pdf": "docs/a.pdf"},
        )

    file_task = service.task_store["u1"][task_id].file_tasks["/tmp/docs/a.pdf"]
    assert file_task.relative_path == "docs/a.pdf"


@pytest.mark.asyncio
async def test_document_file_processor_passes_relative_path():
    processor = DocumentFileProcessor(
        document_service=Mock(),
        owner_user_id="u1",
    )
    upload_task = Mock()
    upload_task.successful_files = 0
    upload_task.failed_files = 0
    upload_task.processed_files = 0
    file_task = Mock()
    file_task.relative_path = "docs/finance/a.pdf"

    with patch("utils.hash_utils.hash_id", return_value="h1"), \
         patch("os.path.getsize", return_value=10), \
         patch.object(processor, "process_document_standard", new=AsyncMock(return_value={"status": "indexed"})) as proc_mock:
        await processor.process_item(upload_task, "/tmp/a.pdf", file_task)

    assert proc_mock.await_count == 1
    assert proc_mock.await_args.kwargs["relative_path"] == "docs/finance/a.pdf"


@pytest.mark.asyncio
async def test_process_document_standard_sets_document_path_and_dedups_by_relative_path():
    opensearch_client = AsyncMock()
    opensearch_client.search = AsyncMock(return_value={"hits": {"hits": []}})
    opensearch_client.index = AsyncMock(return_value={"result": "created"})
    opensearch_client.indices.put_mapping = AsyncMock(return_value={"acknowledged": True})
    session_manager = Mock()
    session_manager.get_user_opensearch_client.return_value = opensearch_client
    document_service = Mock()
    document_service.session_manager = session_manager
    processor = TaskProcessor(document_service=document_service)

    fake_clients = Mock()
    fake_embed_resp = Mock()
    fake_embed_resp.data = [Mock(embedding=[0.1, 0.2])]
    fake_clients.patched_embedding_client.embeddings.create = AsyncMock(return_value=fake_embed_resp)
    fake_clients.docling_http_client = Mock()

    with patch("config.settings.clients", fake_clients), \
         patch("config.settings.get_embedding_model", return_value="text-embedding-3-small"), \
         patch("config.settings.get_index_name_for_model", return_value="documents_text_embedding_3_small"), \
         patch("config.settings.get_openrag_config", return_value=Mock(knowledge=Mock(embedding_model="text-embedding-3-small"))), \
         patch("services.document_service.chunk_texts_for_embeddings", return_value=[["hello"]]), \
         patch("utils.index_utils.ensure_index_exists_for_model", new=AsyncMock()), \
         patch("utils.embedding_fields.ensure_embedding_field_exists", new=AsyncMock(return_value="chunk_embedding")), \
         patch("utils.document_processing.process_text_file", return_value={"filename": "a.pdf", "mimetype": "application/pdf", "chunks": [{"page": 1, "text": "hello"}]}):
        await processor.process_document_standard(
            file_path="/tmp/a.txt",
            file_hash="hash-1",
            owner_user_id="u1",
            original_filename="a.pdf",
            relative_path="docs/finance/a.pdf",
            jwt_token="jwt",
        )

    first_search_body = opensearch_client.search.await_args.kwargs["body"]
    path_filters = first_search_body["query"]["bool"]["filter"]
    assert {"term": {"document_path": "docs/finance/a.pdf"}} in path_filters

    indexed_body = opensearch_client.index.await_args.kwargs["body"]
    assert indexed_body["document_path"] == "docs/finance/a.pdf"
    assert indexed_body["document_id"] == "docs/finance/a.pdf"


@pytest.mark.asyncio
async def test_same_filename_different_folders_are_different_documents():
    opensearch_client = AsyncMock()
    opensearch_client.search = AsyncMock(side_effect=[
        {"hits": {"hits": []}},  # first file
        {"hits": {"hits": []}},  # second file
    ])
    opensearch_client.index = AsyncMock(return_value={"result": "created"})
    opensearch_client.indices.put_mapping = AsyncMock(return_value={"acknowledged": True})
    session_manager = Mock()
    session_manager.get_user_opensearch_client.return_value = opensearch_client
    document_service = Mock()
    document_service.session_manager = session_manager
    processor = TaskProcessor(document_service=document_service)

    fake_clients = Mock()
    fake_embed_resp = Mock()
    fake_embed_resp.data = [Mock(embedding=[0.1, 0.2])]
    fake_clients.patched_embedding_client.embeddings.create = AsyncMock(return_value=fake_embed_resp)
    fake_clients.docling_http_client = Mock()

    common_patches = [
        patch("config.settings.clients", fake_clients),
        patch("config.settings.get_embedding_model", return_value="text-embedding-3-small"),
        patch("config.settings.get_index_name_for_model", return_value="documents_text_embedding_3_small"),
        patch("config.settings.get_openrag_config", return_value=Mock(knowledge=Mock(embedding_model="text-embedding-3-small"))),
        patch("services.document_service.chunk_texts_for_embeddings", return_value=[["hello"]]),
        patch("utils.index_utils.ensure_index_exists_for_model", new=AsyncMock()),
        patch("utils.embedding_fields.ensure_embedding_field_exists", new=AsyncMock(return_value="chunk_embedding")),
        patch("utils.document_processing.process_text_file", return_value={"filename": "x.pdf", "mimetype": "application/pdf", "chunks": [{"page": 1, "text": "hello"}]}),
    ]
    with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6], common_patches[7]:
        await processor.process_document_standard(
            file_path="/tmp/x1.txt",
            file_hash="same-hash",
            owner_user_id="u1",
            original_filename="x.pdf",
            relative_path="docs/a/x.pdf",
            jwt_token="jwt",
        )
        await processor.process_document_standard(
            file_path="/tmp/x2.txt",
            file_hash="same-hash",
            owner_user_id="u1",
            original_filename="x.pdf",
            relative_path="docs/b/x.pdf",
            jwt_token="jwt",
        )

    assert opensearch_client.index.await_count == 2
    indexed_paths = [call.kwargs["body"]["document_path"] for call in opensearch_client.index.await_args_list]
    assert indexed_paths == ["docs/a/x.pdf", "docs/b/x.pdf"]
    indexed_ids = [call.kwargs["id"] for call in opensearch_client.index.await_args_list]
    assert indexed_ids == ["docs/a/x.pdf_0", "docs/b/x.pdf_0"]


@pytest.mark.asyncio
async def test_backward_compatibility_without_relative_path_uses_document_id_dedup():
    opensearch_client = AsyncMock()
    opensearch_client.search = AsyncMock(return_value={"hits": {"hits": []}})
    opensearch_client.index = AsyncMock(return_value={"result": "created"})
    opensearch_client.indices.put_mapping = AsyncMock(return_value={"acknowledged": True})
    session_manager = Mock()
    session_manager.get_user_opensearch_client.return_value = opensearch_client
    document_service = Mock()
    document_service.session_manager = session_manager
    processor = TaskProcessor(document_service=document_service)

    fake_clients = Mock()
    fake_embed_resp = Mock()
    fake_embed_resp.data = [Mock(embedding=[0.1, 0.2])]
    fake_clients.patched_embedding_client.embeddings.create = AsyncMock(return_value=fake_embed_resp)
    fake_clients.docling_http_client = Mock()

    with patch("config.settings.clients", fake_clients), \
         patch("config.settings.get_embedding_model", return_value="text-embedding-3-small"), \
         patch("config.settings.get_index_name_for_model", return_value="documents_text_embedding_3_small"), \
         patch("config.settings.get_openrag_config", return_value=Mock(knowledge=Mock(embedding_model="text-embedding-3-small"))), \
         patch("services.document_service.chunk_texts_for_embeddings", return_value=[["hello"]]), \
         patch("utils.index_utils.ensure_index_exists_for_model", new=AsyncMock()), \
         patch("utils.embedding_fields.ensure_embedding_field_exists", new=AsyncMock(return_value="chunk_embedding")), \
         patch("utils.document_processing.process_text_file", return_value={"filename": "a.pdf", "mimetype": "application/pdf", "chunks": [{"page": 1, "text": "hello"}]}):
        await processor.process_document_standard(
            file_path="/tmp/a.txt",
            file_hash="legacy-hash",
            owner_user_id="u1",
            original_filename="a.pdf",
            relative_path=None,
            jwt_token="jwt",
        )

    first_search_body = opensearch_client.search.await_args.kwargs["body"]
    assert first_search_body["query"]["term"]["document_id"] == "legacy-hash"
    indexed_body = opensearch_client.index.await_args.kwargs["body"]
    assert indexed_body["document_path"] == "a.pdf"
    assert indexed_body["document_id"] == "legacy-hash"


@pytest.mark.asyncio
async def test_check_document_path_exists_is_scoped_by_owner_and_connector():
    opensearch_client = AsyncMock()
    opensearch_client.search = AsyncMock(return_value={"hits": {"hits": []}})
    processor = TaskProcessor(document_service=Mock())

    await processor.check_document_path_exists(
        "docs/finance/a.pdf",
        opensearch_client,
        owner_user_id="user-1",
        connector_type="local",
    )

    search_body = opensearch_client.search.await_args.kwargs["body"]
    filters = search_body["query"]["bool"]["filter"]
    assert {"term": {"document_path": "docs/finance/a.pdf"}} in filters
    assert {"term": {"owner": "user-1"}} in filters
    assert {"term": {"connector_type": "local"}} in filters


@pytest.mark.asyncio
async def test_dynamic_index_mapping_contains_document_path():
    body = await create_dynamic_index_body("text-embedding-3-small", provider="openai")
    assert body["mappings"]["properties"]["document_path"]["type"] == "keyword"
