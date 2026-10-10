# Post-publication CI follow-up

The initial [release-receipts PR CI](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094724655) failed `test_create_dialog_has_named_fields_and_keyboard_close` (228 passed, one failure, nine environment skips). [Original output](../../../.autoloop/artifacts/release-receipts-before-ci.txt) is retained. The earlier source/patch PR checks were green; publication itself succeeded.

New-dialog setup queues textarea sizing/title focus with a zero-delay callback. The test could move focus to Close before that callback ran, then send Enter to the title field. Synchronize the queued setup before explicitly focusing Close, and wait for the show-class removal after Enter. Keep the original closed-dialog and zero-write assertions. No test skip, arbitrary sleep, raised timeout, application-code change or release-tag replacement.

[Five focused repetitions](../../../.autoloop/artifacts/release-receipts-repeat.txt) passed. The [complete fixture gate](../../../.autoloop/artifacts/release-receipts.txt) passed all 238 tests with zero skips/errors/failures, Ruff, compilation and offline builds; one existing test-client deprecation remains. [Final protected-main CI on PR #55](https://github.com/artyomsklyarov/suur-things-mcp/pull/55) must pass normally. These post-publication test/docs updates do not replace the verified 0.10.1 distributions.
