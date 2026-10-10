# 0.10.0 verification

Local gate on 2026-10-10: `.venv/bin/python .autoloop/scripts/verify.py release-0.10.0`.

- Ruff, compilation and offline source/wheel build passed.
- 238 tests passed; zero skips/errors/failures confirmed through pytest JUnit.
- One existing Starlette/TestClient/httpx deprecation remains.
- `uv lock --check --offline` passed (52 resolved packages).
- Local wheel: version 0.10.0, Python >=3.10, packaged frontend byte-identical to source.
- Local sdist contains all five root handoff documents.
- Tracked release-content credential-pattern scan found no matching private-key/provider/GitHub credentials; values were not printed. Synthetic artifacts only.
- Local handoff links and `git diff --check` passed.

Evidence: [full release gate](../../../.autoloop/artifacts/release-0.10.0.txt).

[PR #53](https://github.com/artyomsklyarov/suur-things-mcp/pull/53) passed its required CI (229 passed, nine environment skips, one test-client warning), then merged at `bfbb51cec06e898ccb9b64747d442a9f8733e002`. [GitHub v0.10.0](https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.10.0) is public. [PyPI publishing failed](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094300758) before uploading: the pinned action rejects the build backend's metadata 2.5. Fresh version-specific PyPI JSON returned 404. The patch release is 0.10.1 with explicit metadata 2.4 for both targets; the 0.10.0 tag remains intact. Local builds are not publication proof; fixture tests are not live Things mutation or live model acceptance.
