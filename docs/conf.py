project = "sdb"
copyright = "2019 Delphix, 2025 CoreWeave"
author = "Serapheim Dimitropoulos"

try:
    from sdb._version import version as release
except ImportError:
    release = "dev"

extensions = [
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "drgn": ("https://drgn.readthedocs.io/en/latest", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "furo"
html_title = "sdb"

html_theme_options = {
    "source_repository": "https://github.com/sdimitro/sdb",
    "source_branch": "master",
    "source_directory": "docs/",
}

copybutton_prompt_text = r"sdb> |\$ |>>> "
copybutton_prompt_is_regexp = True
