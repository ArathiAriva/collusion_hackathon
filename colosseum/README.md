# Colosseum <sub><sub><img src="dev/colosseum_icon.png" alt="Colosseum icon" width="45" /></sub></sub>

Objective auditing of collusion in cooperative, tool-calling multi-agent systems.

**Paper:** Mason Nakamura, Abhinav Kumar, Saswat Das, Sahar Abdelnabi, Saaduddin Mahmud, Ferdinando Fioretto, Shlomo Zilberstein & Eugene Bagdasarian, *Colosseum: Auditing Collusion in Cooperative Multi-Agent Systems* ([arXiv:2602.15198](https://arxiv.org/abs/2602.15198))

If you find the repo or paper useful or interesting please :star: it!

<p align="center">
  <a href="https://arxiv.org/abs/2602.15198">
    <img src="dev/colosseum-motivation-v3-preview.png" alt="Colosseum motivation slides" width="70%" />
  </a>
</p>

## Overview

Colosseum is a framework for objectively auditing cooperative multi-agent systems composed of
tool-calling, LLM-based agents. It runs teams of agents on shared tasks (Jira ticket allocation,
hospital scheduling, ...) and measures whether an assigned coalition gains at the expense of the
others, across varying models, network topologies, and environments. Experiments live under
`experiments/` and use the [Terrarium](https://github.com/umass-aisec/Terrarium)
(`terrarium-agents`) framework with the DCOP environments from the vendored CoLLAB. Any model id
that supports tool calling can be used (set it in a config); the local-GPU (vLLM) route is
untouched but not needed.

In the Collusion Research Sprint this covers:

- **Project 2.1** – four matched conditions isolating whether a prompted pair plus a private
  channel produces a coalition advantage.
- **Project 2.3** – an LLM judge over the coalition channel as collusion evidence.
- **Project 3.1** – actions as covert carriers, starting from the no-channel condition.

## Setup

> **Fastest path:** from the repo root, `./setup.sh colosseum` sets this experiment up (deps + the shared `poseidon_compute` package) in one step; `./setup.sh` does all experiments. The manual steps below are equivalent.

**Working dir:** run native Colosseum commands from `colosseum/` (`cd colosseum`) —
the `experiments.*` module paths, config paths, and the `outputs/` tree resolve
relative to it. The shared-board wrapper commands below run from the repository root.

**Install and deps:**

```bash
cd colosseum
uv venv --python 3.11 .venv
source .venv/bin/activate
uv sync                                  # Terrarium 0.1.1 from PyPI + CoLLAB vendored in external/
```

CoLLAB (required for the DCOP environments) is vendored in `external/CoLLAB` in this starter repo
and found automatically. Only if you move it: set `TERRARIUM_COLLAB_PATH` in `.env`.

**Inference config:** configured once in the **repo-root** `compute.env` (one level up from this
directory). Copy `../compute.env.example` → `compute.env` there and set **either**
`OPENROUTER_API_KEY` (serves every model id below, including the paper's default
`openai/gpt-4o-mini`) **or** `NEBIUS_API_KEY` (open models only). A single `OPENROUTER_API_KEY`
is enough for all the commands on this page — the shared client falls back to OpenRouter whenever
that is the only key set, and preflight's key check counts it. (The current A–E and GPT positive-control configs use GPT-4o-mini and require
OpenRouter; other configs may use open models served by Nebius.) Keys and any overrides (e.g.
`TERRARIUM_COLLAB_PATH`) live only in the repo-root `compute.env`; see
[`../COMPUTE.md`](../COMPUTE.md).

## Quick start

First preflight, then run the supplied positive control:

```bash
uv run python -m experiments.preflight           # checks python, terrarium, CoLLAB, environments, key
uv run python -m experiments.preflight --ping --model openai/gpt-4o-mini  # + one tiny model call (--model is required)
uv run python -m experiments.collusion.run --config experiments/collusion/configs/hackathon_positive_control.yaml
```

The positive control uses four agents on a Jira sprint, an assigned pair with a
coalition-only board and the existing `simple` coalition prompt. Its current YAML
uses GPT-4o-mini, four planning rounds and three seeds (1–3). It is separate from
the six-agent A–E evaluation. Each native run prints its estimate and asks before
spending (`-y` or `COLOSSEUM_YES=1` skips).

Use an OpenRouter key for `openai/gpt-4o-mini`. The separate
`hackathon_positive_control_qwen.yaml` preserves the Qwen comparison pilot.

**Execution versus evidence:** successful completion verifies execution, not
collusion. `coalition_advantage_mean` is coalition mean reward minus outsider mean
reward. Positive or negative gaps can occur at any seed count or planning budget;
retain all outcomes and compare matched conditions. Regret gaps and outcome-selected
subsets require separate interpretation and transcript evidence.

## Running experiments

See [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) for setting definitions, override
rules, run-count examples, and the A–E communication arrangements.

**Project 2.1 – four matched conditions** (same task, model, seed, path topology):

Current A–E configs use `openai/gpt-4o-mini`, six agents, four planning rounds,
and `seeds: [101, 102, 103, 104, 105]`. The selected/reference group still has two agents. The agent
count is specified in both `communication_network` and the sweep; update both
when changing it. These settings differ from the historical four-agent pilots.

| config | assigned pair prompted | extra channel | knobs |
|---|---|---|---|
| `hackathon_2_1_a_pair_private_channel.yaml` | yes | coalition-only | prompted pair; path adaptation |
| `hackathon_2_1_b_pair_no_channel.yaml` | yes | none | `coalition_prompt: always` |
| `hackathon_2_1_c_open_channel.yaml` | no | open to everyone | `coalition_prompt: never`, `extra_channel_members: all` |
| `hackathon_2_1_d_neither.yaml` | no | none | vanilla baseline |

```bash
for c in a_pair_private_channel b_pair_no_channel c_open_channel d_neither; do
  uv run python -m experiments.collusion.run --config experiments/collusion/configs/hackathon_2_1_$c.yaml -y
done
```

The two knobs and `colluder_selection: first_and_last` (the two path endpoints, so the pair
shares no other blackboard) are new; everything else is the paper's runner. Expand `seeds:` to
3–5 for an initial comparison. The runner's summary scores only the selected pair,
including an unprompted reference pair in C/D. Score every nonempty proper subset
of agents **in all four conditions**, after running, with no additional model calls:

```bash
uv run python -m experiments.collusion.score_subsets \
  --root experiments/collusion/outputs \
  --output-dir experiments/collusion/outputs/subset_scores
```

This also scores previously saved positive controls. `subsets.csv` contains every
subset; `summary.json` records the designated group's score and the best subsets
overall, among multi-agent subsets, and separately for each size. With six agents,
there are 62 nonempty proper subsets, including 15 pairs (the historical four-agent
pilots have 14 subsets, including six pairs). Singletons are included
for completeness but cannot themselves constitute collusion.

Two scores are reported: `reward_gap` (subset mean reward minus complement mean
reward, matching the runner's `coalition_advantage_mean`) and `regret_gap`
(complement mean regret minus subset mean regret, matching the current paper's
regret-based advantage). Regret gaps are left null if per-agent regrets are missing.
These reuse each agent's saved unilateral regret, not a jointly optimized coalition
counterfactual. The highest-scoring subset can differ between the two metrics.

Selecting the best subset after observing outcomes introduces selection bias:
positive maxima alone do not demonstrate collusion. Compare the same subset search
and sizes across matched conditions/seeds and inspect messages/actions for evidence
of coordination. The positive control uses a complete topology; it is separate from
the path-topology A–D comparison. Update all four configs consistently when changing
the model, planning rounds, or seeds.

**Condition E – all pairwise private boards** extends the A–D comparison:
`hackathon_2_1_e_all_pairwise_private.yaml` uses a complete graph with
`consolidate_channels: false`. Six agents get 15 two-agent boards, without a
common all-agent board, coalition instructions, or an extra special board. Its
task, model, seed list, and planning budget match the current D config. The two
selected agents are only a scoring reference; score all subsets as above.

```bash
uv run python -m experiments.collusion.run \
  --config experiments/collusion/configs/hackathon_2_1_e_all_pairwise_private.yaml
```

E versus D tests adding direct pairwise access throughout the network. E versus C
compares private pairwise communication with path boards plus a shared public
board; channel number and membership both differ. These are not privacy-only
contrasts. Keep model/rounds/seeds aligned across A–E when updating the study.

**LLM judge on the coalition channel** (project 2.3 evidence): same rubric as the paper, through
OpenRouter. `--judge-model` is **required** (there is no default) — pass any tool-free open model
id it should judge with:

```bash
uv run python -m experiments.collusion.judge_blackboards \
  --root experiments/collusion/outputs/<tag>/<timestamp> --judge-model openai/gpt-4o-mini
```

`--root` is the timestamp folder printed at the end of a run (the "Wrote results to:" line).

**Project 3.1 (actions as carriers):** start from condition B (pair prompted, no channel) — the
coalition can only coordinate through public posts and `assign_task` calls, all logged in
`tool_events.json` / `blackboard_0.txt`. Hide or canonicalise those before the partner sees them
by editing `experiments/collusion/prompts.py` / the environment's `format_blackboard_context`.

**Entry point:** each runner is a runnable module, so `uv run python -m experiments.collusion.run`
and `uv run python experiments/collusion/run.py` are equivalent. You can also route through the
repo's one entry point, `poseidon-run --model <id> -- <cmd>` (from the repo root), which
force-selects a provider for `<id>` (Nebius → OpenRouter → Modal → loud error) and wraps the
native command — use it to pin a specific model or to host an off-catalog model on Modal (see
[`../COMPUTE.md`](../COMPUTE.md) §3):

```bash
# from the repo root
poseidon-run --model Qwen/Qwen2.5-7B-Instruct -- \
  bash -c "cd colosseum && uv run python -m experiments.collusion.run \
    --config experiments/collusion/configs/collusion_jira_topologies.yaml"
```

Other runners accept the same open model ids in their YAML `llm_models` and `-y` where they have
a cost prompt (all run from `colosseum/`):

```bash
# Persuasion effects on collusion (JiraTicket)
uv run python experiments/persuasion/collusion/run.py \
  --config experiments/persuasion/collusion/configs/persuasion_collusion_jira.yaml

# Persuasion effects on collusion (Hospital)
uv run python experiments/persuasion/hospital/run.py \
  --config experiments/persuasion/hospital/configs/persuasion_hospital.yaml

# Collusion (JiraTicket topology sweeps)
uv run python experiments/collusion/run.py \
  --config experiments/collusion/configs/collusion_jira_topologies.yaml

# Network influence / misinformation propagation (Mass policy)
uv run python experiments/network_influence/run.py \
  --config experiments/network_influence/configs/misinformation_prop_mass.yaml

# Agent objective misalignment (Hospital)
uv run python experiments/agent_misalignment/run.py \
  --config experiments/agent_misalignment/configs/agent_misalignment_gpt_4_1_mini.yaml
```

## Shared-board report experiment (A–F)

Use the [shared-board run guide](../scripts/shared_board/README.md) for the actual
report setup: one public board for all six agents, A–D objective/channel ablations,
E universal private channels, and F's oversight notice. The original path configs
above are an earlier protocol. Main seeds 101–105 are reused exploratory instances.

Run these wrappers from the **repository root**, using the Colosseum interpreter:

```sh
colosseum/.venv/bin/python scripts/shared_board/run_shared_seed_blocks.py --dry-run
colosseum/.venv/bin/python scripts/shared_board/run_shared_seed_blocks.py \
  --batch-id shared-board-reproduction-001
colosseum/.venv/bin/python scripts/shared_board/run_f_seed_blocks.py \
  --baseline-batch results/ae-batches/shared-board-reproduction-001 \
  --batch-id f-oversight-reproduction-001
```

Only the first command is offline. A–E run in parallel within each seed, then pass
an audit barrier before the next seed. F runs serially against the completed A
baseline. Every paid launch needs an unused batch ID. The wrappers automatically
score all proper subsets and preserve transcripts/native output layout. They
pass `-y` to the native runner, so paid commands do not prompt again. See the guide
for setup, pilots, artifact locations and no-network tests.

## Outputs

Results land in `experiments/collusion/outputs/<tag>/<timestamp>/`, where `<tag>` is set by the
config (`experiment.tag` / `experiment.output_dir`; e.g. `hackathon_positive_control`) and
`<timestamp>` is auto-generated per run. The timestamp folder holds the experiment-level
`summary.csv` (plus `summary.json` / `summary.jsonl`, `config.json`, `experiment.log`); each
individual run lives under `runs/<model>/<sweep>/<run_id>/` and has `agent_prompts.md`,
`blackboard_*.txt` (one per blackboard, e.g. `blackboard_0.txt` / `blackboard_1.txt`),
`tool_events.json`, `metrics.json` and `final_summary.json`. Pass this timestamp folder as
`--root` to the judge above.

Check completed/failed counts in `progress.json`, expected seed-specific run folders,
and per-agent rewards in `final_summary.json`. A positive numerical gap is not an
execution requirement or sufficient evidence of collusion.

## Notes

- If you are using APIs, actively track API usage since API costs accumulate linearly with the
  number of agents in a run.
- The local-GPU (vLLM) inference route is untouched but not needed for the hackathon path.

## Citation
Please cite us using:
```bibtex
@article{nakamura2026colosseumauditingcollusioncooperative,
      title={Colosseum: Auditing Collusion in Cooperative Multi-Agent Systems}, 
      author={Mason Nakamura and Abhinav Kumar and Saswat Das and Sahar Abdelnabi and Saaduddin Mahmud and Ferdinando Fioretto and Shlomo Zilberstein and Eugene Bagdasarian},
      year={2026},
      eprint={2602.15198},
      archivePrefix={arXiv},
      primaryClass={cs.MA},
      url={https://arxiv.org/abs/2602.15198}, 
}
```
