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
