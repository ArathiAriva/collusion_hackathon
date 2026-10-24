# Colosseum sprint 2.1 architecture

Reviewed October 24, 2026. Source: `https://github.com/poseidon-research/collusion_hackathon`; HEAD `d585a7b3be50366cc2bdf5789bf8add5890b2abd`.

## Scope and status

This note covers the Colosseum experiment inside this multi-project starter repository. The question is whether coalition-favoring behavior persists after removing assigned membership/instructions and an extra private channel.

The project adds condition E, subset scoring, explicit message destinations, corrected channel descriptions and a multi-seed launch wrapper. Each launch records its Git commit, dirty state, configuration snapshots and runtime source hashes. Historical pilot results and technical attempts are documented in PROJECT_LOG.md.

## Data flow

YAML configuration → `experiments/collusion/run.py` → Terrarium environment and communication network → coalition/channel interventions and prompt wrapper → planning/tool calls → final actions → environment rewards → metrics and saved traces → offline subset scoring.

## Main components

- `colosseum/experiments/preflight.py`: Python/dependency/environment/key checks; optional `--ping` makes a live request.
- `colosseum/experiments/collusion/run.py`: sweep orchestration, selection/order, channels, context injection, logging and metrics.
- `colosseum/experiments/collusion/prompts.py`: coalition instructions layered over native task prompts.
- `colosseum/experiments/common/local_protocol.py`: communication/tool execution.
- `colosseum/experiments/common/channel_aware_agent.py`: required explicit message destinations restricted to accessible boards.
- `results/run_ae_once.py`: byte-identical YAML snapshots, separate condition processes, seed-specific artifact checks and matching-instance verification. Seeds run serially within each process.
- `colosseum/experiments/collusion/metrics.py`: credited rewards, selected-group reward gap, unilateral regret and system-regret diagnostics.
- `colosseum/experiments/collusion/score_subsets.py`: project extension; all nonempty proper subsets, reward/regret gaps, and maxima by size. Requires complete saved runs; no model calls.
- `colosseum/experiments/collusion/configs/hackathon_2_1_*.yaml`: four path-network conditions (A–D) plus complete/pairwise-private condition E. Membership prompting is controlled independently with `coalition_prompt`; channel membership with `extra_channel_members`.
- Terrarium 0.1.1 supplies `envs.dcops.jira_ticket` and `envs.dcops.hospital`; CoLLAB is vendored under `colosseum/external/CoLLAB`.
- `util/poseidon_compute` supplies shared inference routing; credentials belong in gitignored root `compute.env`.

## Execution and artifacts

Documented setup from repository root: `./setup.sh colosseum`. From `colosseum/`: `uv run python -m experiments.preflight`; then the collusion runner with the chosen YAML. Native API inference can run on a laptop; Modal is optional. Do not infer endpoint availability from a config comment.

Outputs under `colosseum/experiments/collusion/outputs/` include per-run configuration, metrics, final summaries, prompts, trajectories, board logs and sweep summaries. The positive control uses GPT-4o-mini, four planning rounds, seeds 1–3 and a complete network. A–E use GPT-4o-mini, six agents, four rounds and fresh evaluation seeds 101–105. A–D use a path; E uses 15 private pairwise boards. The wrapper adds a unique batch namespace under the configured raw output roots and stores its manifest/frozen configs under results/ae-batches/. The old seed-1 summarizer remains a pilot-only tool.

## Interpretation and next checks

Verify task/agent profiles, turn order, prompts, accessible channels and tool budgets match within each seed block except the intended intervention. Distinguish the code's mean-reward gap from the paper's regret-gap advantage. A post-selected best subset can score positively without coordination; exclude singletons from coalition claims and compare identical searches against D. Native system regret uses a loose theoretical bound; the offline exact Jira solver supplies a tighter optimum. Saved seed-1 visibility and full 25-trajectory mocked-native wrapper tests have passed. C’s seed-1 all-agent board had correct access but misleading private-channel wording, corrected for evaluation. All earlier committed task assignments are shared environment state during execution. No paid evaluation runs were launched by this documentation update.
