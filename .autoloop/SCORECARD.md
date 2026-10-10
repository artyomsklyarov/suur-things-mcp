# Scorecard

Scores 1-5; baseline and current are equal at orientation. Judgments are bounded by synthetic fixture tests, not real Things write acceptance.

| Dimension | Before | Current | Evidence / limitation |
|---|---:|---:|---|
| Correctness | 4 | 4 | 113 tests, local build green; real URL Scheme integration requires human |
| Reliability | 3 | 4 | Lossless config recovery, atomic caps and resilient startup; list race remains medium |
| Test coverage | 3 | 4 | Real Chromium + fixture SQL; recovery/concurrency/agent safety protected; intercepted browser workflow suite, iter-5.txt |
| Code quality | 4 | 4 | Ruff green, idiomatic modules; compact HTML is large, no rewrite justified |
| Architecture | 4 | 4 | Read/write split, overlay store, thin tools; preserves intent |
| Security | 3 | 4 | Nonce CSP, origins, token redaction; attachment path containment enforced; five regressions in iter-1.txt |
| Performance | 4 | 4 | Threaded reads + cheap cursor; no new benchmark claim |
| UX | 3 | 4 | Full-width small windows, accessible menu/dialog focus, 320/390/768px all-view tests; iter-11 |
| UI | 3 | 4 | Desktop styling retained, compact views no longer clip; 20 inspected light/dark populated/empty screenshots, iter-11; sampled small-text contrast >=4.86 light / >=4.93 dark, iter-12-ratios.txt |
| Accessibility | 2 | 4 | Clickable div/span controls, modal names, labeled fields, inert background and focus containment/return; sidebar/filter/task keyboard access and palette selection semantics; advanced drag views remain a limitation |
| Product completeness | 4 | 4 | Documented phases done; live integration validation outside loop scope |
| Docs / DX | 4 | 4 | README + CLAUDE architecture + tests; autonomous fixture harness now available |
| SEO / discoverability | N/A | N/A | Local desktop dashboard, not public website |
| Content quality | N/A | N/A | Software repo, not knowledge base |

Iteration 2: reliability remains 3 pending concurrency/frontend work; config recovery now handles six invalid payloads, unique recoveries, unreadable-file fail-closed and malformed link lists. Coverage improves with 12 new tests, 130 total. Evidence iter-2-before.txt / iter-2.txt.

Iteration 3: eight simultaneous uploads now accept exactly the configured two; metadata/file counts match. Concurrent direct saves both complete with valid JSON and no temporary leftovers. Reliability stays 3 pending startup work. Total 132 tests.

Iteration 4: seven organizer safety failures now pass, including IDs outside submitted scope and duplicate IDs; 139 tests. Reliability/test coverage still 3 until frontend failure/accessibility coverage.

Iteration 9: standalone-project route now resolves correctly, proven by synthetic browser test and actual fixture empty-project screenshots. Correctness remains 4, UX remains 3 pending narrow layout. 155 tests.

Holistic iteration 10: all dimensions rescored in artifacts/holistic-10.txt. Scores unchanged, UX/UI 3 because compact layout is a preview until all views pass. Preview measurable geometry improves 118px -> 390px; no new exceptions or warnings. 156 tests.

Iteration 12: sampled sidebar counts/headings, matrix/level names/subtitles, preferences hints/labels/buttons now all meet 4.5:1. Minimum light 2.48 -> 4.86, dark 3.19 -> 4.93. Accessibility remains 4, not a claim of exhaustive WCAG conformance. 161 tests.

Iteration 13: API config/link malformed roots and section/list shapes reject with 400 without changing bytes. Config/item/board I/O errors and upload storage errors have structured envelopes. 26 new tests, 187 total. Correctness/reliability remain 4.

Iteration 14: supported claude/codex agent and nonempty model strings survive save/merge and editor preferences. Malformed values ignored, seven regressions, 194 tests. Reliability/product completeness stay 4.
