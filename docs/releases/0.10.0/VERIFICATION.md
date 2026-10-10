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

GitHub CI/merge/release and public PyPI distribution receipts are pending here until observed. Local builds are not publication proof; fixture tests are not live Things mutation or live model acceptance.
