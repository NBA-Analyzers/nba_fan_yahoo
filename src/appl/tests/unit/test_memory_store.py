import pytest

from appl.tests.unit.vector_store_contract import VectorStoreContract


@pytest.fixture
def store(memory_store):
    return memory_store


class TestInMemoryVectorStore(VectorStoreContract):
    pass
