# Base documentation context

Contextopus ships product guides and templates as ordinary Workspace records. `core.base_status` reports the selected documentation context and installed bundle version. `core.base_plan` is read-only and returns exact incoming changes and `plan_revision`; `core.base_install(plan_revision, confirmation?)` installs that revision using Workspace creation, proposals, shared indexing and Git history. Status and preview do not initialize a context or load embeddings.

The shipped context is `contextopus-base`. Its initial instructions use `material_max_tokens: null` because product guides can be long. Changes to its instructions remain under the normal direct-request and instruction-approval rules. A user-added length limit is respected by later updates, which return `needs_split` rather than changing the rule. If knowledge approval is enabled, installation returns `review_requires_approval` until actual confirmation is supplied.

`core.base_select(context)` points the documentation role at another existing context. This is separate from active task selection and the general settings. Reading base records never changes active instructions. Updating the shipped context preserves the selected role when another context was selected.

The pointer and managed revision receipts live in `core/configuration/base-context.json`. Documents themselves live in the ordinary Workspace knowledge folder and common index; there is no additional documentation store. Modified or deleted managed records cause a conflict that includes incoming text. Updates preserve custom INSTRUCTIONS and retired documents. A colliding unmanaged context is never adopted or overwritten.

Interrupted creation, application and indexing retain their exact plan and proposal receipt. Repeating `core.base_install` with that original revision resumes the operation. Conflicts and user-added rules require review instead of automatic overwrite.

## Installation and upgrade

Explicit `contextopus init` (`core.init`) initializes storage. If no active embedding profile exists, its `setup` result reports `model_setup_required`; no documentation context or algorithm vectors are created yet. Preview and apply the model with `contextopus setupmodel --apply` (or `core.model_plan` then `core.model_apply`). After successful embedding setup, Core refreshes the shared algorithm catalog and installs the bundled documentation through the exact base plan. A later explicit init runs the same preparation for an existing root after a package upgrade.

Read-only status, diagnostics, base previews and algorithm searches never perform this setup. User-modified or deleted managed documents produce an explicit conflict plan. Current knowledge approval produces `review_requires_approval` with the exact plan; pass actual confirmation to `core.base_install` after presenting it. A documentation/catalog delivery failure appears under `setup` as pending and retains the successfully installed model. The response identifies the operation needed to retry. A custom selected documentation role remains selected.

A legacy `.pcw` root still follows the existing explicit relocation procedure before `core.init`; documentation setup does not migrate or replace that storage. Changing the embedding profile rebuilds source documents first, then refreshes derivative algorithm cards for the newly active profile.
