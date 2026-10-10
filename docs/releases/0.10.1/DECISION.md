# Packaging recovery decision — 2026-10-10

The authorized 0.10.0 GitHub release succeeded, but [its existing PyPI action](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094300758) failed before uploading with `InvalidDistribution: Invalid distribution metadata: '2.5' is not a valid metadata version`.

[Hatchling's history](https://hatch.pypa.io/latest/history/hatchling/) records a new default of 2.5. The documented [wheel](https://hatch.pypa.io/latest/plugins/builder/wheel/) and [source](https://hatch.pypa.io/latest/plugins/builder/sdist/) targets allow `core-metadata-version`. Explicitly select 2.4 for both targets, a format used by prior successful publications. All current project metadata fits that format. Check actual generated METADATA/PKG-INFO rather than relying on configuration alone.

Publish this correction as 0.10.1, retaining the public 0.10.0 tag and history. Re-run local strict verification and required CI. No new dependency, build-backend downgrade, credential/environment/action change, tag replacement or live Things write is needed. Do not weaken or skip metadata validation. If public publication still fails, diagnose that specific failure before any retry.
