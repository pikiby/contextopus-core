# TUI demonstration artifacts

These are actual headless Textual 8.2.8 screenshots of the approved initial
layout. Every screen is clearly marked EXAMPLE and uses synthetic data from
`tests/test_contextopus_tui.py::DemoApplication`; none is evidence of a live
index, model, daemon, or connected MCP client.

`main-{wide,narrow}.svg` and `settings-{wide,narrow}.svg` show 79 and 40 column
terminals. `preview-*` shows the keyboard settings preview. PNG files render
those SVG captures; `settings-demo.gif` animates main → settings → preview.

Regenerate SVG captures from the repository root:

```sh
env -u NO_COLOR PYTHONPATH=src python docs/media/tui/capture_demo.py
python docs/media/tui/render_png.py
```

Headless checks cover keyboard selection, include-archived changes, revision
preview/application, returning, narrow/wide line limits, unknown values, and
resize without adding chart measurements. Inline live launch uses
`contextopus tui` and the central application's query/execute API.

The historical Session Search compatibility adapter delegates status/search over its existing Unix
socket. Opening its TUI returns a launch descriptor to the terminal client.
The external actor still owns its index, queue, deduplication, occurrences,
and tail cursor; these screenshots predate the separate Session Search Core module. See the
[module repository](https://github.com/pikiby/contextopus-session-search) for its
current indexing and ownership model.

PNG/GIF rendering uses existing system librsvg and Cairo plus Pillow. SVG whitespace is explicitly preserved during rasterization so aligned columns remain aligned. The capture process honors NO_COLOR at runtime; it is unset only for these color demonstrations.

Installed-module preflight on 2026-10-14 found `/usr/bin/session-search` using
its own Python environment. The Contextopus test environment had no
`session_search` import, yet the adapter correctly discovered the executable
and returned `[/usr/bin/session-search, tui]` as a shell-free launch descriptor.
The existing socket was absent, so daemon status remained unavailable. The
installed TUI opened and exited with Q (exit 0), showing saved counts while its
indexer was stopped. This preflight started no indexing work and migrated no
data. The demo frames remain synthetic examples.

## 1.2.0 selection and modules

`selection-1.2-wide.svg/png` and `modules-1.2-wide.svg/png` capture the actual
current Textual application headlessly. `capture_1_2.py` supplies an explicitly
synthetic settings/module fixture and uses the real bundled algorithm catalog.
The EXAMPLE label is part of each screen. A ready preview is fixture state;
no settings or modules are applied, and no live root, daemon or MCP connection
is represented.

Regenerate only these new captures:

```sh
env -u NO_COLOR PYTHONPATH=src .venv/bin/python docs/media/tui/capture_1_2.py
.venv/bin/python docs/media/tui/render_png.py docs/media/tui/selection-1.2-wide.svg docs/media/tui/modules-1.2-wide.svg
```

The renderer accepts optional SVG paths, leaving earlier published captures
unchanged. These are static render examples, not evidence of keyboard operation
or a live installation.
