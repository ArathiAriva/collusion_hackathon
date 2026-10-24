# A–E seed-1 validation and expansion readiness

Audited October 24, 2026 (America/Toronto). No paid inference or judge calls during this audit.

## Verdict

Actual access controls and message delivery pass for all five repaired runs. One prompt wording issue was found: C’s all-agent board called itself a private channel. Membership and actual visibility were correct. The runner now explicitly labels this extra board as open to everyone; offline actual-setup/prompt validation passes. The saved seed-1 outputs are preserved. Treat these as development pilots and use the corrected wording consistently for a fresh matched evaluation.

## Saved-artifact checks

- 150 saved start-of-turn prompts checked, covering all six agents in four planning rounds and execution in each condition. Board sections exactly match the accessible board histories up to each prompt timestamp; no inaccessible board is included. Prompt timestamps match Toronto-local naive time when compared with board epoch timestamps.
- All 549 successful message posts matched one recorded event on exactly the requested board, with the correct sender and content; every sender belonged to that board. No failed tools or missing destination IDs.
- A/B coalition instructions occur only for Layla and Shaunna, on each of their five turns. C/D/E contain no injected coalition instructions. B explicitly says no dedicated coalition board is assigned.
- Same tasks, private costs, agent list, base system/private prompts and actual turn order across conditions. Six agents, four rounds, GPT-4o-mini, temperature 0.7, max_tokens 1500, max_conversation_steps 3, seed 1, one execution iteration, eight Jira tasks and no assignment fills.
- Thirty turns and six explicit action decisions per run; one explicit skip in E. No random fallback fills or recorded model continuation errors. Every run completed. Six routing/scoring tests pass, including direct read/write denial for nonmembers and correct message-tool destination schemas.
- All 310 proper-subset scores recomputed; rewards and unilateral regrets independently checked; same exact joint optimum, 152.698591, in every condition.
- Launch config hashes are retained; the historical audit reads each run’s saved native config. Current YAML deliberately uses fresh evaluation seeds instead of seed 1. Archived runtime source hashes verified; current runtime differs only in run.py’s all-agent-board context correction.

## Condition checks and cost estimate

| Condition | Actual boards | Injected coalition prompt | Recorded input tokens | Recorded output tokens | Uncached estimate (USD) |
|---|---|---|---:|---:|---:|
| A | 5 path boards + private Layla/Shaunna board | Layla and Shaunna | 167,551 | 8,785 | $0.03040 |
| B | 5 path boards; no extra board | Layla and Shaunna | 166,216 | 8,022 | $0.02975 |
| C | 5 path boards + one all-agent board | None | 258,022 | 9,446 | $0.04437 |
| D | 5 path boards; no extra board | None | 178,366 | 8,981 | $0.03214 |
| E | 15 pairwise private boards; no all-agent board | None | 240,429 | 13,251 | $0.04401 |

Total: 1,010,584 input + 48,485 output tokens; 390 recorded model calls. Estimated cost for all five conditions at one seed: **$0.18068 USD (18.1 US cents)**.

Pricing checked October 24, 2026: [OpenRouter GPT-4o-mini](https://openrouter.ai/openai/gpt-4o-mini), $0.15/million input and $0.60/million output; advertised cache-read rate $0.075/million input. The estimate assumes no cache discount. Cache hits, provider retries and actual charges were not retained locally; this is not account billing. Earlier technical attempts and judge calls are excluded. At similar usage, ten fresh matched seeds cost approximately $1.81, twenty approximately $3.61, before retries/judging; actual usage varies by task and model behavior.

## Interpretation and limits

- Execution prompts show all earlier committed assignments to every subsequent agent, regardless of topology. Final task choices are shared environment state. Board communication remains restricted; agents can also relay information across their own boards.
- C’s old “private” wording does not make its board private; all six members received it. Nonetheless, the wording is a prompt confound and has been corrected before expansion. Do not silently pool old and revised prompt versions.
- Conversation budgets are equal, but message counts and tokens differ by topology; E permits five direct destinations per agent and C adds a shared history. This experiment changes communication affordances, not privacy alone.
- Before expanding, record primary score and subset-size rule, paired contrasts and evaluation seed list. Best-subset regret is outcome-selected and does not establish intent; existing system_regret uses a loose bound rather than the independently computed optimum. No numerical result was excluded for poor performance.
- Saved prompts are start-of-turn inputs; raw HTTP requests for subsequent tool-loop steps are not archived. Those steps are covered by source inspection and membership/routing tests rather than direct network capture.

## Reproduce the offline checks

From the repository root:

```sh
colosseum/.venv/bin/python results/config-audit/validate_saved_seed1.py
colosseum/.venv/bin/python results/config-audit/verify_configs.py
colosseum/.venv/bin/python results/summarize_ae_once.py
(cd colosseum && .venv/bin/python -m unittest experiments.common.test_channel_routing experiments.collusion.test_score_subsets)
```

[Machine-readable saved-run audit](saved-seed1-validation.json); [current offline setup audit](verification.json).
