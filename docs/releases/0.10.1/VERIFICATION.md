# 0.10.1 verification

Packaging correction only: wheel and sdist explicitly emit core metadata 2.4; the full 0.10.0 product update is retained. The [decision](DECISION.md) records the failed 0.10.0 attempt and supported fix.

Local gate: `.venv/bin/python .autoloop/scripts/verify.py release-0.10.1`; [output](../../../.autoloop/artifacts/release-0.10.1.txt). Both distribution metadata headers were inspected for version 0.10.1, metadata 2.4 and Python >=3.10. No production task mutation or live model call is part of this gate.

Local gate passed: 238 tests, zero skips/errors/failures, Ruff, compilation and offline builds; one existing test-client deprecation. `uv lock --check --offline` passed. Required CI, normal merge, GitHub release, PyPI job and public file hashes are recorded after they are observed. See STATUS.MD for current publication state.
