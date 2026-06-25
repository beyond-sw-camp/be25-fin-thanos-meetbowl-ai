from app.pipelines.chunking import split_document_into_chunks


def test_long_markdown_table_is_split_by_rows_with_header_repeated() -> None:
    table = "\n".join(
        [
            "| Category | Risk | Value |",
            "| --- | --- | --- |",
            "| Cybersecurity | Medium | 26.6% |",
            "| CBRN | Low | 4.2% |",
            "| Biological | Low | 1.1% |",
        ]
    )

    chunks = split_document_into_chunks(
        title="Deep Research System Card",
        content=table,
        max_chars=95,
        overlap_chars=10,
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert "| Category | Risk | Value |" in chunk.content
        assert "| --- | --- | --- |" in chunk.content
        assert not chunk.content.endswith("| Cybersecurity | Medium")
    assert any("| CBRN | Low | 4.2% |" in chunk.content for chunk in chunks)


def test_short_markdown_table_stays_in_one_chunk() -> None:
    table = "\n".join(
        [
            "| Category | Risk |",
            "| --- | --- |",
            "| CBRN | Low |",
        ]
    )

    chunks = split_document_into_chunks(
        title="System Card",
        content=table,
        max_chars=500,
        overlap_chars=50,
    )

    assert len(chunks) == 1
    assert chunks[0].content == table
