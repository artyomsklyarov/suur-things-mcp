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
