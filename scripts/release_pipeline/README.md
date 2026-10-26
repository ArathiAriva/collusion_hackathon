# Release experiment: A versus D

The main development study compares **Product + Release** under two conditions. A assigns the pair a joint local-utility objective and a private board; D retains the shared organizational objective and public board only. This measures the combined objective/channel intervention, not their separate effects. D's reference pair is analysis metadata and is not disclosed as a coalition.

## Frozen setup

[study.yaml](../../colosseum/experiments/collusion/configs/release_pipeline/study.yaml) selects seeds **201–205**, the generated **deadline_pressure** family only and the Product–Release pairing. Each seed generates a different deadline-pressure scenario; this does not repeat the fixed pilot fixture. A/D share that exact scenario, pair and speaking schedule. These seeds were selected before live study outcomes were observed. This remains a development experiment, not held-out evaluation.

Five seeds × one family × one pairing × two conditions = **10 trajectories**. Other families are deferred to follow-up studies. Each scenario/pair block runs **A and D concurrently**, with independent clients, environments and output directories; the next block waits for both. Seeds/families/pairings progress serially. Maximum concurrency is **two trajectories**, with no D reuse. Use `--max-parallel 1` for serial execution.

Current templates are `A_assigned_pair_private_board.yaml` and `D_cooperative_public_board.yaml`; earlier B/C templates are archived. Four roles, three planning rounds, one final phase, six model responses per turn: at most96 calls per trajectory /960 for this study. Prompts `release-prompts-v11` require a final-turn role-specific calculator check before submission in both conditions. This is an audited instruction, not a server-side submission gate. Payoffs, evidence access and incentives are documented in the [contract](../../docs/experiments/RELEASE_PIPELINE_CONTRACT.md) and [payoff protocol](../../docs/experiments/RELEASE_PAYOFF_COMPREHENSION.md).

## Setup and inference configuration

Install `uv`, then run `./setup.sh colosseum` from the repository root. For offline
previews, scripted trajectories and saved-output review, no API key is needed.
For live execution only, copy `compute.env.example` to `compute.env` if it does not
already exist, and set your own `OPENROUTER_API_KEY`. Leave global `LLM_MODEL`
overrides unset. Never put credentials in YAML, cards or artifacts. The frozen
card names OpenRouter `openai/gpt-4o-mini`; no Nebius account is required.

## Run from the repository root

Use the environment installed by `./setup.sh colosseum`. Previewing requires no key, provider client, network or output directory:

```sh
# Default five-seed / deadline-pressure / Product–Release A/D plan:10 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --dry-run

# Fixed hand-worked fixture, Product–Release and A/D:2 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --pilot --seed 11 --dry-run

# Equivalent explicit seed/family selection:10 trajectories
colosseum/.venv/bin/python scripts/release_pipeline/run.py --seeds 201 202 203 204 205 --families deadline_pressure --dry-run

# Execute the full native protocol with scripted offline clients; new ID required
colosseum/.venv/bin/python scripts/release_pipeline/run.py --batch-id release-ad-offline-new

# Paid execution: requires a separately frozen, costed card and a new ID
colosseum/.venv/bin/python scripts/release_pipeline/run.py --live --run-card /path/to/frozen-card.json --batch-id release-ad-live-new
```

The live card must match the exact printed schedule hash, trajectory count, current prompt version, endpoint/model, verified price assumptions, estimate and retry/stopping policy. [run_card.example.json](run_card.example.json) is an incomplete template, not authorization or a usable live card. Keep keys in the existing environment setup, never in configs/cards. Main model: OpenRouter `openai/gpt-4o-mini`, temperature0.7, max_tokens1500. Estimate is not a hard spend cap. No live study is launched by a dry-run or commit.

`--seeds` overrides the study seed list; `--families` selects families; `--pair ROLE ROLE` selects one pair. `--conditions A` or `D` allows diagnostics. `--planning-rounds N` overrides rounds and changes the frozen plan. Legacy `--seed N --instances K` generates consecutive instance seeds per family. `--pilot` always uses the same fixed fixture: its seed changes speaking order, not scenario facts. Do not use repeated pilot seeds to claim scenario diversity. Use `--seeds` for the main generated study. `--partition heldout` is available only after a separate evaluation freeze; the current study uses development.

## Artifacts and checks

New outputs remain under ignored `results/release-pipeline/<batch-id>/`. Saved
v9/v10 results, pilots and earlier diagnostics are committed as
[checksummed archives with portable offline review commands](../../artifacts/results/README.md). New IDs only; no overwrite/resume or automatic trajectory retries. Every run has its own scenario/config, source lineage, native messages/prompts/tool events, outcome, metrics and annotation packet. `payoff_checks.json` checks final calculator use, own/prior fields, used facts and candidate payoff against the offline oracle; later-role assumptions are reported separately. Checks do not send hidden truth to agents. Scripted offline clients do not demonstrate comprehension. Manifest records both condition results after each matched block; an unexpected exception stops the batch after its peer finishes, preserving successful artifacts. SDK transport retries may still apply.

`analysis.json` contains completion/audits, matched contrasts and scenario-clustered summaries; `all_pair_metrics.csv` includes all pairs in each complete run. Scored subsets are distinct from selected coalition membership. Failed/incomplete trajectories stay recorded. Scenario observations from different role-pair conditions are dependent; do not count them as independent seeds.

```sh
colosseum/.venv/bin/python scripts/release_pipeline/run.py --analyze results/release-pipeline/<batch-id>
colosseum/.venv/bin/python scripts/release_pipeline/check_payoff_checks.py results/release-pipeline/<batch-id>/runs/<run-id>
PYTHONPATH=colosseum colosseum/.venv/bin/python -m unittest experiments.collusion.release_pipeline.test_release experiments.collusion.release_pipeline.test_decision_calculator -q
PYTHONPATH=colosseum colosseum/.venv/bin/python -m unittest discover -s scripts/release_pipeline -p 'test_*.py' -q
```

The separate `comprehension.py` diagnostic supports tool-free preflight or `--with-tools`; live use needs its own frozen card. `audit_scenarios.py` verifies structural opportunities offline. `annotate.py` validates human records against saved annotation packets; use `--help` for arguments. Historical v1–v6 artifacts and earlier incomplete pilots remain preserved, with their original prompt versions and limitations. Historical Jira scripts/results are separate and unchanged.

Budget details: `max_conversation_steps: 6` counts model responses (including the first) per actor per planning/final turn; one response can contain multiple tool calls. Initial prompts state the limit and a private notice before every request shows response index and remaining responses. Notices are saved in `budget_notices.json`. Six responses permit calculation, repair and submission; reserve the final response for submission. If no successful check was possible, submit rather than silently exhaust the budget: the missing check remains a failure in the audit. This does not certify comprehension. Calculator v2 does not require alpha when functional loss is zero; it never retrieves another role’s private facts. Missing-input replies explicitly say which numeric keys to supply. Use full-precision facts for the exact scope/mode; QA labels refer to the committed scope. Stopped v7 results remain preserved and separate.

Seeds201/202 were partially observed in the stopped v7 development batch. V8 is a revised development setup; preserve version separation and do not describe these reused seeds as fresh held-out evaluation.

For a supervised restart, add `--stop-on-repeated-issues` and freeze `stopping_rule: stop-on-repeated-issues-v1` in the live card. After each matched A/D block, stop before launching another if the same issue category occurs in at least two trajectories: missing submission/run failure, missing final payoff check, calculator own/prior decision mismatch, or candidate utility error greater than0.01 raw utility. Small rounding differences alone do not trigger this rule. Low reward, policy violations or coalition advantage are outcomes, not technical stop triggers. Already-active paired trajectories finish before this block-boundary stop; unexpected execution exceptions stop the batch. No retries or replacements. Stopped results are exploratory and should not be treated as a complete fixed-sample study.

`input_smoke.py` probes Release evidence-to-input extraction from saved seed201 contexts, separately from meetings. Default preflight compares current/checklist/excerpts; `--focused` uses consistent diagnostic instructions and shorter contexts; `--structured` uses typed records derived only from accessible owner messages. `--live --batch-id <new-id>` executes the printed bounded plan through GPT4omini with no retries. These are adaptive development diagnostics, not confirmation tests. Strict callable JSON is distinct from correct numeric extraction; reference answers never enter model requests. The typed-record extractor is limited to these saved examples, not a production evidence parser.

### V9 final handoff stabilization

Historical v9 prompts are `release-prompts-v9`. QA's final submission declares `functional_loss`; Ops declares `day`, `alpha`, `operational_loss` from its selected configuration. These public-to-later-actors values are agent claims, not oracle truth. Release's FINAL calculator accepts **only** `{"disposition":"ordinary_go"}` (or defer/exception_go); committed prior fields and declared evidence are bound in code. No nested evidence reconstruction is needed. Final claims are saved in `declared_evidence.json`. Scoring/action domains remain unchanged; false numeric claims have no new reward penalty. This explicit disclosure handoff changes protocol version and must remain separate from older results. The checker now accepts earlier valid matching previews when alternatives were explored later. Historical v9 cards use v9. A generated native pilot precedes retry; automatic repeated-issue stopping stays enabled.

### V10: authenticated owner-selected receipts

QA/Ops again submit only their original decision fields. Submitting authorizes disclosure of the corresponding record from that caller's own initialized evidence: QA functional loss for committed scope; Ops day/alpha/loss for committed scope/chosen mode. Numeric evidence is selected in code, not retyped. Release's final preview remains disposition-only and uses `bound-release-v2`. `prior_declared_evidence` / `declared_evidence.json` retain legacy filenames but contain owner-selected receipts in v10 (`evidence_receipt_version` identifies them). Quality/readiness labels are not corrected. This constrains final numeric evidence concealment/forgery; it does not prevent the Product–Release pair from approving a known unsafe release. Planning communication remains agent-generated. Historical v10 cards use `release-prompts-v10`; preserve all older versions separately.

### Current v11: bind prior commitments in final previews

All final-turn role calculators now bind earlier accepted decision fields in code. For example, Ops cannot preview ordinary deployment with quality `clear` after QA committed `blocker`. Product/QA/Ops still supply a complete proposed decision; inspect `bound_decision` in the result. Own fields, later-role hypotheses and external numeric assumptions remain caller supplied. Release retains its disposition-only calculator and owner-published evidence receipts. Planning calculators are unchanged. Metadata records `role-decision-utility-v3-bound-prior`; new cards must use `release-prompts-v11`. Action domains, scoring and objectives are unchanged. This version has offline validation only; no v11 live results are available. Keep v9/v10 development batches separate.

### Reviewed v10 three-seed summary

To reproduce the reviewed stopped-v10 summary without model calls, choose a new output directory:

```sh
colosseum/.venv/bin/python scripts/release_pipeline/summarize_completed.py \
  /tmp/collusion-review/results/release-pipeline/release-product-release-deadline-v10-20261026 \
  --output /tmp/collusion-review-v10-summary
```

Extract the archives to `/tmp/collusion-review` first using the reviewer guide.
This report is specific to v10 seeds201–203 and rejects other batches; its interpretation is not a generic template for future runs. It writes per-run CSV, matched differences, JSON and Markdown, retaining preview-check flags. Pilots and other versions are excluded. New outputs remain ignored; the reviewed historical snapshot is archived in Git.

### Preparing a new live run card

Copy `scripts/release_pipeline/run_card.example.json` to a new local JSON file.
Run the dry-run command above and fill `schedule_hash`, `authorized_trajectories`
(10 for the default study), `prompt_version`, a unique `freeze_id`, dated verified
endpoint `rates`, and a positive estimated `resource_estimate_usd`. Keep the
configured model/temperature/output limit. Choose
`stopping_rule: stop-on-repeated-issues-v1` and invoke the matching flag:

```sh
colosseum/.venv/bin/python scripts/release_pipeline/run.py \
  --live --run-card /path/to/your-completed-card.json \
  --stop-on-repeated-issues --batch-id release-ad-v11-reproduction-001
```

That command spends API credit. The card estimate is not a hard spend cap.
Validation rejects incomplete or mismatched cards. The example template is not
ready to run, and archived v9/v10 cards cannot run against current v11 code. A new
v11 live run remains a development evaluation; do not label it an exact replay of
the archived trajectories. Source/config snapshots and lockfiles record historical
versions, while model/provider sampling can change between live runs.
