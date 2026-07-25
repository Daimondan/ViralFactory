"""Regression coverage for config-driven rotating search-query ingestion."""

from query_ingestion import QueryIngestionRunner


def test_rotation_is_deterministic_and_changes_with_seed():
    queries = [
        {"query": f"query {n}", "engine": "duckduckgo", "enabled": True}
        for n in range(8)
    ]
    runner = QueryIngestionRunner(db_path=":memory:")

    first = runner.select_queries(queries, {"per_cycle": 3, "seed": "2026-W30"})
    again = runner.select_queries(queries, {"per_cycle": 3, "seed": "2026-W30"})
    next_cycle = runner.select_queries(queries, {"per_cycle": 3, "seed": "2026-W31"})

    assert first == again
    assert len(first) == 3
    assert {item["query"] for item in first} != {item["query"] for item in next_cycle}


def test_ingestion_registers_search_results_as_operator_reviewable_sources(tmp_path):
    runner = QueryIngestionRunner(db_path=str(tmp_path / "vf.db"))
    runner._search = lambda engine, query, date_window_months=None: [{
        "title": "A verified result",
        "url": "https://example.test/result",
        "summary": "A source to review before ideation.",
    }]

    result = runner.run(
        "tenant-a",
        [{"query": "test source", "engine": "duckduckgo", "enabled": True}],
        {"per_cycle": 1, "seed": "fixture"},
    )

    assert result == {"queries_selected": 1, "discovered": 1, "new": 1, "duplicates": 0}
    sources = runner.list_ingested("tenant-a")
    assert len(sources) == 1
    assert sources[0]["source_type"] == "search_item"
    assert sources[0]["status"] == "new"
    assert sources[0]["url"] == "https://example.test/result"
