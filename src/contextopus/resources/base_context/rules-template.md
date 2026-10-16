# Context instruction template

Use this checklist to propose rules for one selected context. Read its current INSTRUCTIONS and preserve rules outside the user's direct request.

```yaml
allow_implicit_updates: false
knowledge_approval_required: false
instructions_approval_required: true
git_history_enabled: true
material_max_tokens: 1024
create_required_sources: false
```

State the context's purpose, boundaries, evidence requirements, source checks and desired presentation. Keep these six independent settings in YAML frontmatter. Missing legacy `instructions_approval_required` and `knowledge_approval_required` values mean true. The packaged product documentation context deliberately starts with a null size limit; ordinary contexts start with 1024 tokens.

For creation, use the canonical create procedure and ask about the standard bundle or customized choices. For existing contexts, apply only on a direct instruction-edit request through `instructions_read`, `instructions_prepare`, present exact changes, then `instructions_apply` under the CURRENT instruction approval policy. A proposed false value cannot waive an existing true approval requirement. Reading this template does not authorize applying it or changing other contexts.
