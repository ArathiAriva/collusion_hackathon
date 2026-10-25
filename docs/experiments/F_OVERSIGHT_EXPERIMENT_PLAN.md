# F oversight extension: five matched seeds

Original design prepared before the five-seed F launch, 2026-10-24; executable paths and reproduction instructions updated 2026-10-25. Historical frozen launch plans remain unchanged in local batch artifacts. This is a post-baseline exploratory extension to the completed corrected shared-board A–E study, not a preregistered held-out evaluation. The seed-1 development pilot is excluded.

## Intervention and fixed settings

F equals shared-board A plus the configured governance notice to every agent on every planning/execution turn. Both have the global public board and one private pair board, and explicit simple coalition instructions only for that pair. Notice is prompt-only: no live monitor, message restriction or enforced suspension. It additionally defines prohibited conduct and restates the team objective; its effect cannot be attributed solely to sanction expectations.

Use the existing F main YAML, seeds **101, 102, 103, 104, 105**, GPT-4o-mini/OpenRouter, six agents/eight Jira tasks, four planning rounds, three model steps per agent turn, one iteration, temperature 0.7, 1500 max output tokens, assignment filling disabled. Preserve all settings. Compare against the completed A trajectories in the explicitly supplied `--baseline-batch`. For the report this was `shared-board-eval-v2-seeds101-105`; a reproduction uses its newly completed A–E batch. Corrected public-board wording must match F. No new A calls.

## Schedule and stopping

The report used batch ID `f-oversight-eval-v1-seeds101-105`; reproductions require a new ID. Five native F trajectories, **one seed at a time**; validate and score each seed before advancing. Freeze input configs, source/lockfile and this plan. Per-seed copies change only seed-selection fields. Unique output namespaces; no overwrites, automatic reruns, extra seeds or model-judge calls. Stop if execution fails or a required audit fails, retain partial results and report the cause. Do not stop based on outcome direction.

## Required audits

For every seed: 30 saved turns (24 planning, 6 execution); exact configured notice once per prompt; 10 pair-only coalition-instruction turns. Reconstruct accessible board histories and accepted tool deliveries; verify one six-agent public and one two-agent private board, accurate wording, member-only access, no missing decisions/random fills/continuation errors. Retain explicit skips and rejected tools as outcomes.

Verify actual tasks, costs, identities, speaking/execution order, system prompts, private input sections and initial board contexts against the same seed's completed A trajectory. Independently recompute agent rewards, unilateral regrets, exact optimum and all 62 proper subset scores; primary subset-search domain remains sizes 2–5. Preserve all seeds, not only those favorable to the hypothesis.

## Reporting

Report A/F per-seed and mean outcomes: original primary maximum-subset regret gap, reference-pair gap, best-pair gap, team reward, mean/pair/outsider regrets and exact optimality gap. Report pair positive-gap counts and matches to best pair/subset including ties. Calculate within-seed F−A differences, means, medians, signs and leave-one-seed-out means. No new significance tests or outlier exclusions. Separate intent from outcome imbalance; no formal transcript judge is part of this launch.

Record prompt/output tokens, model calls and estimated uncached cost using the same baseline accounting rates as previous runs; actual billing/cache discounts may differ. Update the local project log. Generated artifacts remain local under the ignored results directory.

## Limitations

Five reused task seeds, one model trajectory per condition/seed. Matching an environment seed does not reproduce provider sampling. A was run earlier; provider/time variation remains a limitation. The changed user-prompt length/order is part of the notice intervention. A successful configuration audit does not establish that the notice changes collusion.


## Reproduction commands

From the repository root after setup:

```sh
colosseum/.venv/bin/python scripts/shared_board/run_f_seed_blocks.py --dry-run
colosseum/.venv/bin/python scripts/shared_board/run_f_seed_blocks.py \
  --baseline-batch results/ae-batches/shared-board-reproduction-001 \
  --batch-id f-oversight-reproduction-001
```

The first command needs no previous results. The second requires the completed
A–E reproduction and makes paid model calls without another cost confirmation.
See `scripts/shared_board/README.md` for the complete sequence and seed-1 pilots.
