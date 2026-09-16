import tempfile
from repo_intelligence.memory.store import InvestigationStore


def test_create_and_retrieve_investigation():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        store = InvestigationStore(f"sqlite:///{tmp.name}")
        inv_id = store.create_investigation(repo="r", branch="main", commit="abc")
        store.add_message(inv_id, "user", "How is this file implemented?")
        store.add_finding(inv_id, "symbol", "sym:1", note="Important symbol")

        inv = store.get_investigation(inv_id)
        assert inv is not None
        assert inv["repo"] == "r"
        assert len(inv["messages"]) == 1
        assert len(inv["findings"]) == 1

        investigations = store.list_investigations()
        assert len(investigations) == 1
