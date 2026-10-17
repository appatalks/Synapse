# SYNAPSE technical white paper

[Read/download the PDF](synapse-whitepaper.pdf).

The paper is a developer/evaluator-oriented research snapshot, not a model-quality
certification. Four headline screens and the separately labeled Mistral research
results remain distinct.

## Editable and reproducible source

- [Markdown manuscript](synapse-whitepaper.md): prose, tables, references and page/figure directives.
- [Evidence snapshot](evidence.json): exact medians, source commits/digests and publication boundaries.
- [Renderer](../../scripts/build_whitepaper.py): offline vector diagrams, chart, tables and navigation.

From the repository root, install only the optional document-building dependencies:

```bash
python -m pip install -e '.[paper]'
python scripts/build_whitepaper.py
python tests/test_whitepaper.py
```

Application runtime dependencies remain unchanged. No models, native backend,
GPU, browser, external fonts or network access are required to render the paper
after those optional Python packages are available.

The PDF uses standard PDF fonts and vector figures, searchable text, clickable
references/bookmarks and a fixed evidence date. Metadata contains a fingerprint
of the manuscript, evidence and renderer. Builds are deterministic within the
same ReportLab stack; byte identity across different package versions is not
promised.

The renderer checks the snapshot against locally stored reviewed benchmark files.
If a source record changes, review and refresh the snapshot rather than silently
regenerating a stronger claim. External historical records are identified by
immutable commit URLs and SHA256, not fetched during rendering.

Authoring directives are deliberately limited to page breaks, named figures and
the contents block. Unknown directives fail explicitly. The checked-in PDF is
validated against the current source fingerprint so it cannot silently become stale.
