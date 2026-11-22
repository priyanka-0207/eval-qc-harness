import verifiers.v1 as vf

from eval_qc_env.servers.base import FamilyToolset


class DataQCToolset(FamilyToolset):
    TOOL_PREFIX = "warehouse"

    @vf.tool
    def describe(self) -> str:
        """Return the table schemas and row counts."""
        return self._call("describe")

    @vf.tool
    def run_sql(self, query: str) -> str:
        """Run one read-only SQL query and return up to 100 rows."""
        return self._call("run_sql", query=query)

    @vf.tool
    def flag(self, row_ids: list[int]) -> str:
        """Flag rows that break a rule, by row_id."""
        return self._call("flag", row_ids=row_ids)


if __name__ == "__main__":
    DataQCToolset.run()
