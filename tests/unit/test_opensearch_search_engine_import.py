import importlib
import unittest


class TestOpenSearchSearchEngineImport(unittest.TestCase):
    def test_import_smoke(self) -> None:
        try:
            importlib.import_module("src.services.opensearch_search_engine")
        except ModuleNotFoundError as e:
            # This test runs in minimal environments where third-party deps may be absent.
            # The real application environment provides opensearch-py.
            if e.name == "opensearchpy":
                raise unittest.SkipTest("opensearchpy not installed in this environment") from e
            raise


