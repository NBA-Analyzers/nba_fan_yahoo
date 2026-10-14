"""The pages' inline scripts must be valid JavaScript.

A stray tag inside an inline script makes the whole script fail to parse, which leaves
the page with no data and no error on the server. Server tests don't run page scripts,
so this checks them directly.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "static"
PAGES = sorted(STATIC.rglob("*.html"))


def inline_scripts(html: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def as_plain_js(script: str) -> str:
    """Pages are Jinja templates: {{ value }} becomes null and {% tags %} disappear."""
    return re.sub(r"\{%.*?%\}", "", re.sub(r"\{\{.*?\}\}", "null", script, flags=re.S), flags=re.S)


def test_there_are_pages_to_check():
    assert any(inline_scripts(p.read_text(encoding="utf-8")) for p in PAGES)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_tag_is_nested_inside_an_inline_script(page):
    for script in inline_scripts(page.read_text(encoding="utf-8")):
        assert "<script" not in script and "</script" not in script, f"stray script tag inside {page.name}"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to check syntax")
@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_inline_scripts_are_valid_javascript(page, tmp_path):
    for i, script in enumerate(inline_scripts(page.read_text(encoding="utf-8"))):
        path = tmp_path / f"{page.stem}_{i}.js"
        path.write_text(as_plain_js(script), encoding="utf-8")
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{page.name} script {i}: {result.stderr.strip().splitlines()[-1]}"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to check syntax")
def test_the_shared_widget_script_is_valid_javascript():
    result = subprocess.run(["node", "--check", str(STATIC / "slots.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
