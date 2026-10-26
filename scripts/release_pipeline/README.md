# Release experiment: A versus D

The main development study compares two pairings: **Product + Release** and **QA + Ops**. A assigns the pair a joint local-utility objective and a private board; D retains the shared organizational objective and public board only. This measures the combined objective/channel intervention, not their separate effects. D's reference pair is analysis metadata and is not disclosed as a coalition.

## Frozen setup

[study.yaml](../../colosseum/experiments/collusion/configs/release_pipeline/study.yaml) selects seeds **201–205**, all six generated development families and the two pairings. Each seed generates a different scenario in each family. A/D share that exact scenario, pair and speaking schedule. These seeds were selected before live study outcomes were observed. This remains a development experiment, not held-out evaluation.

Five seeds × six families × two pairings × two conditions = **120 trajectories**. One family alone would be20. Each scenario/pair block runs **A and D concurrently**, with independent clients, environments and output directories; the next block waits for both. Seeds/families/pairings progress serially. Maximum concurrency is **two trajectories**, with no D reuse. Use `--max-parallel 1` for serial execution.

Current templates are `A_assigned_pair_private_board.yaml` and `D_cooperative_public_board.yaml`; earlier B/C templates are archived. Four roles, three planning rounds, one final phase, three calls per turn: at most48 calls per trajectory /5760 for this study. Prompts `release-prompts-v7` require a final-turn role-specific calculator check before submission in both conditions. This is an audited instruction, not a server-side submission gate. Payoffs, evidence access and incentives are documented in the [contract](../../docs/experiments/RELEASE_PIPELINE_CONTRACT.md) and [payoff protocol](../../docs/experiments/RELEASE_PAYOFF_COMPREHENSION.md).

## Run from the repository root

Use the environment installed by `./setup.sh colosseum`. Previewing requires no key, provider client, network or output directory:

```sh
# Default five-seed / six-family / two-pair A/D plan:120 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --dry-run

# Fixed hand-worked fixture, both pairings and A/D:4 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --pilot --seed 11 --dry-run

# Restrict the generated suite explicitly:20 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --seeds 201 202 203 204 205 --families deadline_pressure --dry-run

# Execute the full native protocol with scripted offline clients; new ID required
colosseum/.venv/bin/python scripts/release_pipeline/run.py --batch-id release-ad-offline-new

# Paid execution: requires a separately frozen, costed card and a new ID
colosseum/.venv/bin/python scripts/release_pipeline/run.py --live --run-card /path/to/frozen-card.json --batch-id release-ad-live-new
```

The live card must match the exact printed schedule hash, trajectory count, current prompt version, endpoint/model, verified price assumptions, estimate and retry/stopping policy. [run_card.example.json](run_card.example.json) is an incomplete template, not authorization or a usable live card. Keep keys in the existing environment setup, never in configs/cards. Main model: OpenRouter `openai/gpt-4o-mini`, temperature0.7, max_tokens1500. Estimate is not a hard spend cap. No live study is launched by a dry-run or commit.

`--seeds` overrides the study seed list; `--families` selects families; `--pair ROLE ROLE` selects one pair. `--conditions A` or `D` allows diagnostics. `--planning-rounds N` overrides rounds and changes the frozen plan. Legacy `--seed N --instances K` generates consecutive instance seeds per family. `--pilot` always uses the same fixed fixture: its seed changes speaking order, not scenario facts. Do not use repeated pilot seeds to claim scenario diversity. Use `--seeds` for the main generated study. `--partition heldout` is available only after a separate evaluation freeze; the current study uses development.

## Artifacts and checks

All outputs remain under ignored `results/release-pipeline/<batch-id>/`. New IDs only; no overwrite/resume or automatic trajectory retries. Every run has its own scenario/config, source lineage, native messages/prompts/tool events, outcome, metrics and annotation packet. `payoff_checks.json` checks final calculator use, own/prior fields, used facts and candidate payoff against the offline oracle; later-role assumptions are reported separately. Checks do not send hidden truth to agents. Scripted offline clients do not demonstrate comprehension. Manifest records both condition results after each matched block; an unexpected exception stops the batch after its peer finishes, preserving successful artifacts. SDK transport retries may still apply.

`analysis.json` contains completion/audits, matched contrasts and scenario-clustered summaries; `all_pair_metrics.csv` includes all pairs in each complete run. Scored subsets are distinct from selected coalition membership. Failed/incomplete trajectories stay recorded. Scenario observations from different role-pair conditions are dependent; do not count them as independent seeds.

```sh
colosseum/.venv/bin/python scripts/release_pipeline/run.py --analyze results/release-pipeline/<batch-id>
colosseum/.venv/bin/python scripts/release_pipeline/check_payoff_checks.py results/release-pipeline/<batch-id>/runs/<run-id>
PYTHONPATH=colosseum colosseum/.venv/bin/python -m unittest experiments.collusion.release_pipeline.test_release experiments.collusion.release_pipeline.test_decision_calculator -q
PYTHONPATH=colosseum colosseum/.venv/bin/python -m unittest discover -s scripts/release_pipeline -p 'test_*.py' -q
```

The separate `comprehension.py` diagnostic supports tool-free preflight or `--with-tools`; live use needs its own frozen card. `audit_scenarios.py` verifies structural opportunities offline. `annotate.py` validates human records against saved annotation packets; use `--help` for arguments. Historical v1–v6 artifacts and earlier incomplete pilots remain preserved, with their original prompt versions and limitations. Historical Jira scripts/results are separate and unchanged.
