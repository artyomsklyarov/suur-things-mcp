# Dream journal

Dream sessions commit separately; no implementation during dreaming.

## Dream 1 — First impression (orientation)

A new user connects an agent, sees familiar tasks, and trusts that local data stays safe. A new contributor should reach a realistic green build in minutes.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| One command for a fixture-backed full green check | High | High | Existing libs | Promote, implemented by orientation harness |
| Recoverable overlay config with lossless unique backups | High | High | Standard library | Promote B02 |
| Safe image storage even with concurrent tabs/symlinks | High | High | Existing store | Promote B01/B03 |
| Keyboard-first dialogs and familiar focus return | High | High | Vanilla JS | Promote B06 |
| Dashboard usable in a narrow split-screen window | High | High | CSS + navigation | Promote B09 |
| Startup survives corrupt cosmetic browser settings | High | High | Small JS | Promote B07 |
| Theme selected states readable in both schemes | High | Medium | Existing tokens | Promote B08 |
| Local review audit showing which suggestions were actually applied | Medium | Medium | Needs UX scope and persistent schema | Park H05 |
| Entire project timeline across tasks, git and plans (ambitious) | Medium | High | Broad new product direction | Park H06 |
| Private on-device semantic task search without external models (ambitious) | Medium | High | Model/dependencies/platform tradeoffs | Park H07 |
| Shared team cloud boards | Low | High | Accounts, hosting, new privacy model | Reject: conflicts with local single-user product |
| Confetti after every completion | Low | Low | Easy | Reject: contradicts calm motion intent |

No code written in this dream. No lucid prototype: all promoted work has direct existing evidence. Next: highest-priority security containment bug, with regression evidence before the fix.

## Dream 2 — Data dreams (after iteration 8)

The app already holds project hierarchy, overlay preferences, modified stamps and live view identity. Surface those reliably before inventing another data store.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Every project, even outside an area, is navigable | High | High | Small resolve-list fix | Promote B14 |
| Latest selected view always wins over delayed data | High | Medium | Request-generation guard | Promote B11 |
| Existing organizer agent/model preferences actually survive saves | High | Medium | Existing sanitizer | Promote B15 |
| Local overlay recovery guide with exact backup examples | High | Medium | New docs file | Promote B12 |
| Show a retryable local-data error without destroying navigation | High | High | Existing startup work | Already built iter 6 |
| Show accessible selection state, not only CSS color | High | High | Existing keyboard epic | Already built iter 8 |
| Time-budget simulation from stored blocks | Medium | Medium | Needs assumptions/UX design | Park H08 |
| Whole-history attention map across task age and git activity (ambitious) | Medium | High | Privacy/retention and product scope | Park H09 |
| Learn a personal task ontology completely on-device (ambitious) | Medium | High | New model/data architecture | Park H10 |
| Automatic unreviewed agent triage | Low | High | Easy to wire, violates review boundary | Reject |
| Send task analytics to a hosted dashboard | Low | Medium | External tracking/infra | Reject |
| Pretty counters for their own sake | Low | Low | Easy | Reject: no core user value |

No code in dream session. No lucid experiment. Next: resolve standalone projects (highest outstanding safe Fix), then the narrow-window epic.

## Dream 3 — Emotion first (two unchanged score iterations)

First use should feel familiar and safe; the hundredth should feel effortless; returning after absence should not feel like a punishment.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Finish compact views so narrow windows feel calm | High | High | Existing active epic | Promote E02 milestone 2 |
| Make small muted/colored labels readable rather than faint | High | High | Existing theme tokens, measured contrast | Promote B16 Accessibility |
| Make failed requests recover in-place | High | High | Already built | Built iteration 6 |
| Return keyboard focus where the user left it | High | High | Already built | Built iterations 7-8 |
| Latest navigation wins, never old tasks under new title | High | Medium | Existing request guard candidate | Promote B11 |
| Keep time-block placement and board stages accessible by destination selector | High | Medium | Future self-contained epic | Promote B17 candidate; no human gate needed |
| Gentle return-from-absence onboarding | Medium | Medium | Evidence about user habits missing | Park: H12 needs user research before inventing behavior |
| Personal agent that negotiates every day around energy (ambitious) | Medium | High | Model execution is metered/outside loop | Park H13 with opt-in review-only plan |
| Shared memory of a decade of work (ambitious) | Medium | High | Privacy/retention/infrastructure decisions | Park H14 |
| Reward streaks and guilt for missed days | Low | Medium | Easy but manipulative | Reject |
| Remove advanced views to simplify the product | Low | Medium | Feature removal forbidden | Reject |
| Theme crossfades everywhere | Low | Low | Easy but adds no value and harms motion intent | Reject |

No code. No lucid experiment. Existing E02 continues next. H11 is reclassified into a feasible Medium backlog candidate B17; preferred interaction is not itself a real human blocker.

## Dream 4 — Steal from elsewhere (after iterations 12-13)

What if this felt as dependable as a database, as navigable as an editor, and as direct as a spreadsheet?

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Email-client rule: latest selected mailbox wins | High | Medium | Request generation | Promote existing B11 |
| Spreadsheet destination picker beside draggable content | High | Medium | Native selects/time inputs | Already promoted B17 |
| IDE preferences survive unrelated saves | High | Medium | Existing sanitizer | Promote existing B15 |
| Unix-style reproducible contributor verification guide | High | Medium | New documentation | Promote existing B12 |
| Database-style atomic upload budget | High | High | Existing lock | Built iter 3 |
| Document editor recovery copies retain original bytes | High | High | Existing backups | Built iter 2 |
| OS-style dialog focus and Escape stack | High | High | Existing focus manager | Built iter 7 |
| Terminal-theme legibility across text colors | High | High | Existing measured tokens | Built iter 12 |
| Version-control-like rollback of reviewed agent changes (ambitious) | Medium | High | Real writes/history/migration | Park H15 |
| Multiplayer collaborative whiteboard for all projects (ambitious) | Low | High | New accounts/hosting/privacy | Reject: single-user local architecture and outside guardrails |
| Animated radar showing every background poll | Low | Low | Easy | Reject: undermines established quiet refresh |
| Excel ribbon exposing all actions at once | Low | Low | Easy | Reject: wastes scarce task space and duplicates palette |

No implementation. No new backlog item or lucid prototype. Existing self-contained fixes remain higher value than expanding the product.

## Dream 5 — A day in the life (after iterations 14-15)

A developer checks Today beside an editor, prioritizes one task, reviews a proposal, and returns to the same project later. The biggest remaining gap is using advanced placement without a pointer.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Rank tasks with a named native destination picker | High | Medium | Existing tags/overlay actions | Promote existing B17 |
| Schedule an explicit start time without dragging | High | Medium | Existing timeline overlay | Promote same B17 |
| Move a project stage using a keyboard | High | Medium | Existing board placement | Promote same B17 |
| Verify all advanced actions without opening Things | High | Medium | Intercepted browser routes | Promote B17 safety-net milestone |
| Contributor runs green checks before their first edit | High | Medium | Existing fixture scripts | Promote existing B12 |
| Wait-free switching among lists | High | Medium | Existing request ownership | Built iter 15 |
| Readable quiet metadata in both themes | High | High | Measured shared tokens | Built iter 12 |
| Preferences remember which organizer was chosen | High | Medium | Existing config fields | Built iter 14 |
| A workspace-aware agent autonomously negotiates an entire quarter (ambitious) | Medium | High | Metered agent plus organizational rules | Park H16 |
| A private shared timeline across multiple people's Things libraries (ambitious) | Low | High | New identity/sync/data permissions | Reject: outside local single-user architecture |
| Schedule tasks by guessed duration | Low | Medium | Would invent data | Reject: explicit user-entered durations only |
| Add badges for every available action | Low | Low | Easy | Reject: distracts from the core task list |

No code. No new product epic beyond already promoted B17. Next B12 has lower risk; then protect the existing drag actions before the keyboard epic. Dream session 6 also due after product iteration 16 under the eight-iteration cadence.

## Dream 6 — Remove a constraint (eight-iteration cadence)

With unlimited time and resources, the tool could be an operating environment for a person's projects. Waking up, the current product still benefits most from reaching existing actions with a keyboard.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Every existing placement action has a direct keyboard route | High | Medium | Existing actions/native controls | Promote existing B17 |
| Each drag action has fixture evidence before changing it | High | Medium | Existing browser suite | Promote B17 protection slice |
| Screen-reader labels tell task and destination together | High | Medium | Native controls/labels | Promote same B17 |
| Broken settings never erase the user's review context | High | High | Existing guards | Built iter 6/13 |
| Per-user intelligence learned from a decade of tasks (ambitious) | Medium | High | Models/privacy/retention | Park existing H10/H14 |
| A distributed private project operating system (ambitious) | Low | High | Hosting/accounts/sync/security | Reject: outside local MCP/dashboard scope |
| Compare a live organizer across many paid models | Medium | Medium | Metered execution | Park H17 |
| Cross-device remote dashboard | Low | Medium | New exposed auth/network architecture | Reject: weakens local boundary without demonstrated need |
| Direct SQLite writes for instant feedback | Low | High | Technically possible but forbidden boundary | Reject: official URL Scheme is the write authority |
| Replace Things with a new task database | Low | High | Large data migration | Reject: removes the product's integration value |
| Plugin marketplace for arbitrary automation | Low | Medium | Trust/signing/accounts | Reject: new execution/security product without evidence |
| Build custom selects to imitate native widgets | Low | Low | Easy but maintenance-heavy | Reject: native controls already provide keyboard semantics |

No code, new dependency or fresh epic. Continue only the already-supported placement gap; then assess stopping against the scorecard and final dream.

## Dream 7 — The 10x version (after iterations 17-18)

The best local task companion would make familiar actions predictable and approachable rather than accumulating features.

| Idea | Fit | Impact | Buildability | Waking label |
|---|---|---|---|---|
| Explicit scheduling reachable from each task | High | Medium | Existing active epic | Promote E03 remaining slice |
| Successful placement preserves keyboard context | High | Medium | Existing preview | Built iter 18 |
| Failure leaves the previous placement and task intact | High | High | Existing preview | Built iter 18 |
| Drag and keyboard reach the same task semantics | High | Medium | Existing protected actions | Built/protected iter 17-18 |
| First use survives missing optional settings | High | High | Existing startup | Built iter 6 |
| Advanced controls automatically fit a split window | High | Medium | Existing compact layout | Built iter 11; verify E03 completion |
| Whole personal history queried by a private model (ambitious) | Medium | High | Models/storage/privacy | Park existing H07/H14 |
| Cross-organization agent operating system (ambitious) | Low | High | Accounts/hosting/governance | Reject: different product |
| Transparent compensating undo for reviewed changes | Medium | High | Needs live-write conflict/retention design | Park existing H15 |
| Voice-first task management | Medium | Medium | Microphone permissions manifest is sensitive | Park H18 |
| Always-on background task classification | Low | Medium | Metered work/unreviewed updates | Reject: violates explicit review boundary |
| Animated gamified dashboard home | Low | Low | Easy | Reject: calm Things-style list already fits intent |

No code, fresh promotable backlog item or lucid prototype. Finish E03 and holistic review before the final dream.

## Dream 8 — Ten years from now (after iterations 19–20)
No product code. Imagine a durable personal task companion: opening it years later still reveals the same task vocabulary, a trustworthy record of saved material, and controls that work without remembering gestures. Growth should not erode trust in small operations.

| Idea | Fit / impact / buildability | Disposition and reason |
|---|---|---|
| Saved attachments stay visibly successful even when Things note synchronization is unavailable | high / medium / local small | Promote B18: regression then preserve the existing best-effort success contract |
| A green verification badge means every browser check actually ran | high / medium / local small | Promote B19: enforce zero skipped checks in the fixture gate |
| One coherent keyboard vocabulary across future task views | high / medium / already built | Reject new work: E01/E03 provide this foundation; protect it rather than inventing another layer |
| A decade of searchable personal history, including why decisions changed (ambitious) | medium / high / privacy and storage policy | Park H14 existing retention/export/indexing plan |
| A private cross-device task/attachment mesh with offline conflict resolution (ambitious) | medium / high / new infrastructure | Park H19: synthetic conflict specification first, then choose sync backend, encryption and accounts; no cloud setup in this run |
| Preserve damaged overlay bytes for forensic recovery years later | high / medium / already built | Reject duplicate work: digest recovery and guide now exist |
| Archive every screenshot and every personal task change automatically | low / uncertain / storage and privacy cost | Reject automatic collection: no demonstrated value justifies retaining personal history |
| Reuse the dashboard for other task providers | low / uncertain / architectural expansion | Reject: Things is the product boundary and generic adapters would dilute it |
| Quiet compact layout that feels familiar after a long absence | high / medium / already built | Reject duplicate work: E02, menu focus and light/dark rendering are covered |
| A self-updating task companion that deploys its own fixes | medium / uncertain / release authorization | Reject autonomy expansion: deployment is outside this loop and current local gate is appropriate |
| Guaranteed transactional undo for every Things action | medium / high / external acceptance uncertain | Park H15: retained compensating-write/conflict/retention plan; never claim atomic Things writes |
| A synthetic example everyone can safely use to learn the system | high / medium / already built | Reject duplicate work: fixture captures and verification guide already offer it |

Waking up: finish the two concrete trust-boundary improvements from holistic review. No new epic; no dependency or accounts. All other ideas are already satisfied, rejected for product fit, or genuinely blocked by live-write/privacy/infrastructure decisions.
