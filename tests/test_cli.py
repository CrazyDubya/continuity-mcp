import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("body,accepted,expected_records", [
    ("[]", True, 0),
    (json.dumps([{"id": "c1", "mapping": {}}]), True, 1),
    ("{}", False, 0),
    (json.dumps({"id": "c1", "mapping": {}}), False, 0),
    ("null", False, 0),
    ('[{"id":"c1","mapping":{}},BROKEN]', False, 0),
])
def test_cli_validates_streamed_root_and_rolls_back(tmp_path, body, accepted, expected_records):
    source = tmp_path / "export.json"
    source.write_text(body, encoding="utf-8")
    database = tmp_path / "archive.sqlite3"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", "from continuity_mcp.cli import main; main()",
         "--db", str(database), "import-chatgpt", str(source)],
        check=False, capture_output=True, text=True, env=env, timeout=10,
    )
    assert (result.returncode == 0) is accepted
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM imports").fetchone()[0] == int(accepted)
        assert connection.execute("SELECT count(*) FROM conversations").fetchone()[0] == expected_records
    if accepted:
        assert json.loads(result.stdout)["conversations"] == expected_records
    else:
        assert not result.stdout.strip()


def test_cli_streams_multiple_parser_buffers_and_rejects_trailing_content(tmp_path):
    records = [
        {"id": f"synthetic-{index}", "mapping": {
            "n1": {"parent": None, "children": [], "message": {
                "id": "m1", "author": {"role": "user"},
                "content": {"parts": ["synthetic local " + "x" * 1024]},
            }}
        }} for index in range(130)
    ]
    valid = json.dumps(records)
    assert len(valid) > 65536
    for name, body, accepted in [
        ("valid", valid, True),
        ("trailing", valid + " true", False),
    ]:
        directory = tmp_path / name
        directory.mkdir()
        source = directory / "export.json"
        source.write_text(body)
        database = directory / "archive.sqlite3"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        result = subprocess.run(
            [sys.executable, "-c", "from continuity_mcp.cli import main; main()",
             "--db", str(database), "import-chatgpt", str(source)],
            check=False, capture_output=True, text=True, env=env, timeout=10,
        )
        assert (result.returncode == 0) is accepted
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT count(*) FROM imports").fetchone()[0] == int(accepted)
            assert connection.execute("SELECT count(*) FROM conversations").fetchone()[0] == (130 if accepted else 0)
            assert connection.execute("SELECT count(*) FROM messages").fetchone()[0] == (130 if accepted else 0)
