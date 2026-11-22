import verifiers.v1 as vf

from eval_qc_env.servers.base import FamilyToolset


class RetrievalToolset(FamilyToolset):
    TOOL_PREFIX = "helpcenter"

    @vf.tool
    def search(self, query: str) -> str:
        """Return the top 5 help center pages as doc_id and title."""
        return self._call("search", query=query)

    @vf.tool
    def read(self, doc_id: str) -> str:
        """Return the full page text."""
        return self._call("read", doc_id=doc_id)

    @vf.tool
    def answer(self, doc_id: str, value: str, quote: str) -> str:
        """Record the final answer: page id, value, and a 5 to 40 word quote copied from the page."""
        return self._call("answer", doc_id=doc_id, value=value, quote=quote)


if __name__ == "__main__":
    RetrievalToolset.run()
