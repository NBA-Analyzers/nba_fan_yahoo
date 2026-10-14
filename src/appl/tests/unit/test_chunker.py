from appl.ai.chunker import Chunk, chunk_json, chunk_text


def test_short_text_is_a_single_chunk_with_metadata():
    chunks = chunk_text("hello world", source="rules.pdf")
    assert chunks == [Chunk(text="hello world", source="rules.pdf", index=0)]


def test_empty_or_whitespace_text_gives_no_chunks():
    assert chunk_text("", source="x") == []
    assert chunk_text("   \n  ", source="x") == []


def test_long_text_is_split_and_respects_size():
    text = "word " * 500
    chunks = chunk_text(text, source="x", size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_consecutive_chunks_overlap():
    text = "".join(f"{i:04d}," for i in range(200))
    chunks = chunk_text(text, source="x", size=100, overlap=20)
    assert chunks[0].text[-20:] == chunks[1].text[:20]


def test_no_chunk_is_blank():
    chunks = chunk_text("a" + " " * 300 + "b", source="x", size=50, overlap=10)
    assert all(c.text.strip() for c in chunks)


def test_all_content_is_covered():
    text = " ".join(f"tok{i}" for i in range(300))
    chunks = chunk_text(text, source="x", size=120, overlap=30)
    joined = " ".join(c.text for c in chunks)
    assert all(f"tok{i}" in joined for i in range(300))


def test_overlap_must_be_smaller_than_size():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("abc", source="x", size=10, overlap=10)


def test_json_list_of_records_gives_one_chunk_per_record():
    data = [
        {"name": "LeBron James", "pts": 25.1},
        {"name": "Stephen Curry", "pts": 27.3},
    ]
    chunks = chunk_json(data, source="stats.json")
    assert len(chunks) == 2
    assert "LeBron James" in chunks[0].text and "pts: 25.1" in chunks[0].text
    assert "Stephen Curry" in chunks[1].text
    assert all(c.source == "stats.json" for c in chunks)


def test_json_nested_values_are_readable_text():
    data = {"team": {"name": "Hoopers", "players": ["A", "B"]}}
    text = chunk_json(data, source="t.json")[0].text
    assert "team.name: Hoopers" in text
    assert "A" in text and "B" in text


def test_oversized_json_record_is_split():
    data = [{"notes": "x " * 1000}]
    chunks = chunk_json(data, source="t.json", max_chars=200)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_dict_of_records_gives_one_chunk_per_top_level_key():
    data = {
        "LeBron James": {"season": {"pts": 25.1}},
        "Stephen Curry": {"season": {"pts": 27.3}},
    }
    chunks = chunk_json(data, source="stats.json")
    assert len(chunks) == 2
    assert chunks[0].text.startswith("LeBron James")
    assert "LeBron James.season.pts: 25.1" in chunks[0].text
    assert chunks[1].text.startswith("Stephen Curry")


def test_dict_of_lists_gives_one_chunk_per_key():
    data = {"2025-12-03": [{"home": "A", "away": "B"}], "2025-12-04": [{"home": "C", "away": "D"}]}
    chunks = chunk_json(data, source="schedule.json")
    assert len(chunks) == 2
    assert "2025-12-03" in chunks[0].text and "2025-12-04" not in chunks[0].text


def test_dict_with_scalar_values_stays_one_record():
    chunks = chunk_json({"name": "Hoopers", "size": 12}, source="t.json")
    assert len(chunks) == 1


def test_oversized_record_is_split_only_at_line_boundaries():
    player = {f"stat_{i}": i for i in range(60)}
    chunks = chunk_json({"Big Player": player}, source="s.json", max_chars=300)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 300
        assert all(line.startswith("Big Player.stat_") for line in c.text.splitlines())
    joined = "\n".join(c.text for c in chunks)
    assert all(f"Big Player.stat_{i}: {i}" in joined for i in range(60))
