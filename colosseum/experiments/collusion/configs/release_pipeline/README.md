# Release go/no-go: A versus D

Use the [release run guide](../../../../../scripts/release_pipeline/README.md). Current templates:

| Config | Objective | Boards |
| --- | --- | --- |
| `A_assigned_pair_private_board.yaml` | Assigned pair prioritizes mean normalized local utility | Public plus pair-private |
| `D_cooperative_public_board.yaml` | All roles retain shared organizational objective | Public only |

The current launcher runs A and D only, defaulting to both. Original condition letters remain in outputs for continuity. D receives no coalition assignment; its matched reference pair is analysis metadata. This comparison changes both the pair objective and private-board access, so it measures their combined effect. It cannot identify their individual effects.

Four roles, three planning rounds by default, three model calls per turn and one final submission phase. Current v7 instructions require final-turn payoff checks in both conditions. Scenarios, reference pairs, speaking schedules and models are matched; Product–Release and QA–Ops are scheduled by default; `--pair` can select one pairing explicitly. Live dispatch requires a frozen card.

Unused B/C templates are preserved under `archive/` for historical context; the current launcher does not dispatch them. Historical run artifacts remain unchanged.

Current selected pairings (2026-10-26): **Product + Release** and **QA + Ops**, chosen for the main A/D comparison after reviewing development opportunity counts (49/120 and47/120). Other pairings are deferred to follow-up studies. This is an exploratory selection based on development data. Default pilot:4 trajectories; five seeds ×two pairings ×two conditions =20 trajectories for one scenario family. The full generated suite has six families, so five instances per family would mean120 trajectories. `--pair` remains an explicit single-pair override. Original pair indices/run IDs and seeds are preserved.

The current generated study is declared in `study.yaml`: seeds201–205, deadline pressure only, two pairings, A/D in parallel, maximum2 trajectories. That is20 trajectories. The dedicated launcher defaults to this declaration; see the run guide for pilot/legacy overrides.
