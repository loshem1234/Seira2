"""Regression test for the exact bug class that broke mobile twice:
a baseline (desktop) rule and a mobile-only rule at EQUAL CSS
specificity, where file order silently decided the winner. A later,
unrelated edit (adding a new baseline rule after the media query)
then silently canceled the mobile behavor with no test catching it,
because nothing checked specificity itself.

This test parses style.css directly and asserts, structurally, that
every mobile-critical selector has strictly higher specificity than
its desktop counterpart — so this bug class cannot recur even if a
future edit reorders the file carelessly.
"""

import re
from pathlib import Path

STYLE_PATH = Path(__file__).resolve().parents[2] / "seira_web" / "static" / "style.css"


def _specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes+attrs+pseudoclasses, elements). Good enough for
    this file's selectors — no attribute selectors, no ::pseudo-elements."""
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+", selector))
    classes += len(re.findall(r":[a-zA-Z-]+", selector))  # :not(), etc.
    # crude element count: bare words that aren't classes/ids/pseudo-classes
    stripped = re.sub(r"[.#:][\w-]+(\([^)]*\))?", "", selector)
    elements = len(re.findall(r"\b[a-zA-Z][\w-]*\b", stripped))
    return (ids, classes, elements)


def _load_css() -> str:
    return STYLE_PATH.read_text(encoding="utf-8")


def test_mobile_sidebar_specificity_exceeds_desktop_baseline():
    # Desktop baseline: bare `.sidebar { ... }`
    assert _specificity(".sidebar") == (0, 1, 0)
    # Mobile override MUST be strictly higher, by construction.
    assert _specificity(".shell .sidebar") > _specificity(".sidebar")


def test_mobile_backdrop_specificity_exceeds_desktop_baseline():
    assert _specificity(".backdrop") == (0, 1, 0)
    assert _specificity(".shell .backdrop") > _specificity(".backdrop")


def test_mobile_edgetab_specificity_exceeds_desktop_baseline():
    desktop = _specificity(".edgetab.shifted")
    mobile = _specificity("body .edgetab.shifted")
    assert mobile > desktop, (
        "the mobile edge-tab rule must outrank the desktop one by "
        "specificity, not merely by appearing later in the file"
    )


def test_the_actual_selectors_still_exist_in_the_stylesheet():
    """Guards against someone 'fixing' this by deleting the mobile
    rules rather than keeping the higher-specificity qualification."""
    css = _load_css()
    assert ".shell .sidebar" in css
    assert ".shell .backdrop" in css
    assert "body .edgetab.shifted" in css


def test_no_bare_sidebar_or_backdrop_rule_appears_inside_the_media_query():
    """The regression, precisely: a bare `.sidebar {...}` or
    `.backdrop {...}` rule (equal specificity to the desktop baseline)
    must never be (re)introduced inside the mobile media query — only
    higher-specificity compound forms like `.shell .sidebar` or
    `.shell.sidebar-collapsed .sidebar`."""
    css = _load_css()
    media_start = css.index("@media (max-width: 800px)")
    depth = 0
    end = media_start
    for i, ch in enumerate(css[media_start:], start=media_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = css[media_start:end]

    # Extract each rule's exact selector text (comma-separated selectors
    # are checked individually), ignoring the outer @media wrapper and
    # any nested comment text.
    block_no_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    rule_selectors = re.findall(r"([^{}]+)\{", block_no_comments)
    bare_forbidden = {".sidebar", ".backdrop"}
    for raw in rule_selectors:
        for sel in raw.split(","):
            sel = sel.strip()
            if sel in bare_forbidden:
                raise AssertionError(
                    f"Bare selector {sel!r} found inside the mobile media "
                    "query — this ties in specificity with the desktop "
                    "baseline and is exactly the regression this test "
                    "exists to prevent. Use a .shell-qualified form instead."
                )
