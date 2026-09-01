"""Sphinx configuration for the seal user documentation.

Pages are MyST Markdown, the same dialect the rest of the repository is
written in, so a page reads the same in a checkout as it does on the
rendered site.
"""

project = "Seal"
author = "Seal contributors"
copyright = "Seal contributors"

REPO_URL = "https://github.com/vdel/seal"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
]

# README.md documents how to build this site rather than being part of it,
# and _build is Sphinx's own output.
exclude_patterns = ["_build", "README.md", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
# Headings down to <h3> get an anchor, so a page can link to a specific
# section of another one.
myst_heading_anchors = 3

html_theme = "furo"
html_title = "Seal"
html_theme_options = {
    "source_repository": REPO_URL,
    "source_branch": "main",
    "source_directory": "docs/",
}

# Every prompt style a page shows, so "copy" yields a runnable command
# rather than the shell's own prompt.
copybutton_prompt_text = r"\$ "
copybutton_prompt_is_regexp = True
