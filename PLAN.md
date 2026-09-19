# PCW implementation

Version 0.9.0 implements [explicit cycles and approved knowledge](docs/context-workspace-design-v2.md).

- Start with explicit invocation, initial tmp cleanup, and permanent context search/read.
- Keep work results and Current in cycle-local tmp; support a designated clean-context cycle agent.
- Prepare exact reviewed knowledge changes, including consolidation and incoming link effects.
- Apply only the approved revision; intermediate writes preserve tmp.
- Close with full tmp cleanup, including no-change/rejected-update cycles; keep other cycles intact.
- Preserve automatic token windows, replaceable embedding providers, filename IDs and knowledge-only checkpoints.
- Keep approval provenance procedural and separate deterministic tool guarantees from real model behavior.

The current test suite contains cycle regressions and an opt-in agent test. See [verification and limits](docs/explicit-cycle-assessment.md). Historical release assessments prove only their stated versions. This source change is not evidence of a published release or an updated installed host.
