# Automatic indexing

Saving a new or changed ordinary Markdown material automatically triggers tokenization, overlapping windows, embedding and LanceDB replacement. The primary sends the body once. No preparation helper, semantic-boundary generation, assignment, or fragment-array submission exists.

Defaults are 512 tokens per window and 64 tokens of overlap, using the local embedding model's tokenizer. These are configurable engineering defaults, not calibrated retrieval-optimal values. A window advances by size minus overlap, ends at the source end, and never emits an extra overlap-only tail. Unicode codepoint boundaries are preserved: where a tokenizer divides a character, the window ends earlier and the next start adjusts to a valid character boundary. The actual token/character positions are stored with each fragment.

The source text is preserved literally, including whitespace, tables and code. Windows may cross paragraphs or Markdown structures; semantic completeness is not promised. Empty or whitespace-only materials need no vectors. The actual input including document formatting and special tokens must fit the selected model.

Revisions and chunk settings are checked before publication. A failed tokenizer/provider/index write preserves knowledge and leaves the material pending. Old vectors of a changed body are removed. Use `pcw_reconcile` to retry from saved text; it reports each material separately. Startup and status do not load models or replay pending embedding work.

Search returns bounded unique material IDs, paths and distances; read only appropriate whole topic files and necessary links. Links-only changes and moves retain vectors. A tokenizer, window, overlap or embedding-space change rebuilds the index in an inactive table through `pcw_switch_embeddings`; failure retains the previous active configuration and table.
