# Saved results and reviewer reproduction

This is the committed results snapshot dated **2026-10-26**. Full raw records are
compressed to keep thousands of repeated source snapshots and transcripts out of
the working tree. [catalog.json](catalog.json) lists every file, size and SHA-256,
plus each archive checksum. Extraction preserves original repository-relative paths.
Credentials, Python caches, OS metadata and document layout previews are excluded.
Historical source copies and scripts inside the archives are provenance records;
the supported entry points live under `scripts/`.

## Studies and evidence status

| Study | Saved observations | Status and interpretation |
|---|---|---|
| Jira shared-board A–E | Seeds101–105;25 trajectories | Completed exploratory report study; same five task instances across conditions |
| Jira F oversight | Seeds101–105;5 trajectories plus saved A baseline | Completed prompt-only extension; no enforced monitoring or sanctions |
| Release v9 A/D, Product–Release, deadline pressure | Seeds201–204;8 completed,2 interrupted | Stopped for repeated evidence-copy errors; agent-declared numeric evidence |
| Release v10 A/D, same pairing/family | Seeds201–203;6 completed,4 not started | Stopped for repeated preview inconsistencies; owner-selected evidence receipts |
| Release v11 | No live trajectories | Current code has an offline-tested prior-decision binding fix; it is not the version that generated v9/v10 results |

Read the [Jira report](reports/shared-board-eval-v2-summary.md),
[F report](reports/f-oversight-eval-v1-summary.md),
[release v9 report](reports/release-v9/REPORT.md) and
[release v10 report](reports/release-v10/REPORT.md).
Release CSV/JSON exports are beside those reports. These small exports duplicate
the archived records for browsing. The archives also retain earlier path studies,
pilots, scripted offline runs, diagnostics, stopped runs and source/run-card lineage.
They are development records, not additional independent evidence for the reports.
Do not pool protocol versions, pilots or scripted clients with main LLM runs.

| Archive | Contents |
|---|---|
| `release-20261026.tar.gz` | Release development batches, scenarios, prompts, tools, decisions, calculators, manifests, frozen source/cards and design audit |
| `jira-20261026.tar.gz` | Jira batch records, analyses and native Colosseum transcripts/outputs, including report A–F and earlier exploratory runs |
| `figures-20261026.tar.gz` | Saved figures and plot provenance under original figure paths |

The catalog is authoritative for exact membership. Original manifests may contain
the author's absolute paths; they are retained as historical metadata. The review
command below remaps native output paths to the extracted tree and needs no access
to that machine. Model sampling at temperature0.7 is stochastic: reproducing saved
scores is exact; new live trajectories need not produce the same conversations.

## Offline reproduction from a fresh clone

Install `uv`, then run `./setup.sh colosseum` from the repository root. Dependency
installation can use the network; the following review commands make no inference
requests and require no API key. Choose an extraction destination that does not
already contain any archived files. Existing files are never overwritten.

```sh
python3 scripts/artifacts/results_bundle.py --destination /tmp/collusion-review

colosseum/.venv/bin/python scripts/artifacts/review_results.py \
  --root /tmp/collusion-review --output /tmp/collusion-review-checks.json

colosseum/.venv/bin/python scripts/release_pipeline/summarize_completed.py \
  /tmp/collusion-review/results/release-pipeline/release-product-release-deadline-v10-20261026 \
  --output /tmp/collusion-review-v10-summary
```

The extractor verifies archive and per-file hashes before writing. Use
`--bundles release jira` to omit figures, or a single bundle for selective review.
`review_results.py` requires both release and Jira bundles. It recalculates Jira
rewards, all62 proper subsets and exact optima; checks planning/private visibility
and F's notice/input match; and audits saved v9/v10 release trajectories and their
calculator/scoring records. Technical payoff-check flags remain in its summary.
Expected counts: Jira25+5 audited runs; release v9 four matched seeds, v10 three.
The [saved verification output](reports/offline-verification.json) records those checks.

Recreate editable figures and derivative subset metrics using
[scripts/analysis](../../scripts/analysis/README.md), with extracted inputs.

## Run new studies

Use the [Jira guide](../../scripts/shared_board/README.md) for setup, A–E/F pilot/main
commands, model/seed settings and costs, and the
[release guide](../../scripts/release_pipeline/README.md) for offline/live A/D commands
and its frozen-card protocol. New outputs require new batch IDs. Keep model overrides
such as `LLM_MODEL` unset to preserve configured model identities. Set your own
OpenRouter key only in the ignored `compute.env`; archives contain no credentials.

To examine the historical release code in isolation, create a separate checkout at
`1286a1f` (v9) or `9f4a110` (v10); their source snapshots and run cards are in the
archives. Current main uses v11 and cannot accept old prompt-version cards. Historical
runs were intentionally stopped; rerunning them is a new development experiment,
not completion of the old batch. Do not overwrite archived manifests or silently
replace failed trajectories. Recorded API prices/costs are historical estimates,
not current billing guarantees or measured cache discounts.
