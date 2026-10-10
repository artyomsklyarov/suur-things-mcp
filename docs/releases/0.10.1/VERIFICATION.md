# 0.10.1 verification

Packaging correction only: wheel and sdist explicitly emit core metadata 2.4; the full 0.10.0 product update is retained. The [decision](DECISION.md) records the failed 0.10.0 attempt and supported fix.

Local gate: `.venv/bin/python .autoloop/scripts/verify.py release-0.10.1`; [output](../../../.autoloop/artifacts/release-0.10.1.txt). Both distribution metadata headers were inspected for version 0.10.1, metadata 2.4 and Python >=3.10. No production task mutation or live model call is part of this gate.

Local gate passed: 238 tests, zero skips/errors/failures, Ruff, compilation and offline builds; one existing test-client deprecation. `uv lock --check --offline` passed. [Required CI](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094495612) passed: 229 passed, nine environment skips, one test-client warning. [PR #54](https://github.com/artyomsklyarov/suur-things-mcp/pull/54) merged at `a8561fb88285fc8cdc9824723b611ccf91312d39`. [GitHub v0.10.1](https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.10.1) published at that commit on 2026-10-10 23:19:23 UTC; [PyPI workflow](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094617491) succeeded.

Fresh [version-specific PyPI JSON](https://pypi.org/pypi/suur-things-mcp/0.10.1/json) and both distribution downloads were inspected. Registry SHA-256 values match downloaded bytes; both metadata headers are 2.4/version 0.10.1/Python >=3.10. Wheel version source, six runtime modules and frontend are byte-identical to release source. All five root docs are in the source distribution. See [machine-readable receipt](PYPI-RECEIPT.json) for URLs, hashes, sizes and upload times.

The downloaded wheel installed in a disposable Python 3.14.2 environment with `--no-deps`; isolated import/version and packaged frontend checks passed. This does not test dependency resolution, run the MCP server/dashboard, or access real Things data. Personal installation/restart and live mutation/model/manual accessibility acceptance remain separate.

The release tag is the source checkpoint; subsequent GitHub documentation contains publication receipts that could not have existed when that source distribution was built. No tag rewriting or package replacement was performed.
