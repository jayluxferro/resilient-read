from pathlib import Path

from resilient_read.reader import make_cursor, read_bytes, read_lines, read_next, read_tail, search_then_page


def test_read_bytes_and_cursor(tmp_path: Path) -> None:
    f = tmp_path / "big.txt"
    f.write_text("abcdef" * 1000, encoding="utf-8")

    ws = [tmp_path]
    first = read_bytes(ws, "big.txt", offset=0, max_bytes=100)
    assert first["ok"] is True
    assert first["bytes_read"] == 100
    assert first["next_offset"] == 100
    assert first["eof"] is False

    c = make_cursor(ws, "big.txt", offset=100, max_bytes=120)
    nxt = read_next(ws, c["cursor"])
    assert nxt["offset"] == 100
    assert nxt["bytes_read"] == 120
    assert nxt["next_offset"] == 220


def test_read_lines_window(tmp_path: Path) -> None:
    ws = [tmp_path]
    f = tmp_path / "code.py"
    f.write_text("\n".join([f"line_{i}" for i in range(1, 21)]) + "\n", encoding="utf-8")

    out = read_lines(ws, "code.py", start_line=5, max_lines=4)
    assert out["lines_returned"] == 4
    assert out["start_line"] == 5
    assert out["end_line"] == 8
    assert "5|line_5" in out["content"]
    assert "8|line_8" in out["content"]


def test_read_tail(tmp_path: Path) -> None:
    ws = [tmp_path]
    f = tmp_path / "app.log"
    f.write_text("\n".join([f"entry {i}" for i in range(1, 31)]) + "\n", encoding="utf-8")

    tail = read_tail(ws, "app.log", max_lines=3)
    assert tail["start_line"] == 28
    assert tail["end_line"] == 30
    assert "28|entry 28" in tail["content"]
    assert "30|entry 30" in tail["content"]


def test_search_then_page(tmp_path: Path) -> None:
    ws = [tmp_path]
    f = tmp_path / "mix.txt"
    f.write_text(
        "\n".join(
            [
                "alpha",
                "beta",
                "needle-one",
                "delta",
                "needle-two",
                "zeta",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = search_then_page(ws, "mix.txt", query="needle", max_matches=1)
    assert out["matches_returned"] == 1
    assert out["next_from_line"] == 4
    assert out["matches"][0]["match_line"] == 3
    assert out["has_more"] is True

    out2 = search_then_page(ws, "mix.txt", query="needle", from_line=6, max_matches=1)
    assert out2["matches_returned"] == 0
    assert out2["has_more"] is False
