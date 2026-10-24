# Matched A–E batch wrapper

`run_ae_once.py` now runs **all configured seeds** in each of the five conditions.
It does not select new seeds, edit YAML, change prompts or rewards, or call an
LLM itself. Each child runs the existing Colosseum CLI using a byte-for-byte
snapshot of its input YAML.

From the repository root, inspect the plan without writing files or calling models:

```sh
colosseum/.venv/bin/python results/run_ae_once.py --dry-run
```

The current YAML files specify fresh evaluation seeds `[101, 102, 103, 104, 105]`
in all five conditions: 25 trajectories total. The wrapper does not expand or
modify this list. Seed 1 remains development/pilot data. The wrapper follows native seed precedence: sweep seeds, experiment
seeds, then simulation seed, with `runs_per_setting` truncation if configured.
It rejects duplicate seeds, unmatched condition settings, and additional sweep
axes rather than guessing how to pair them.

Once the experiment is authorized and the plan is checked, launch with:

```sh
colosseum/.venv/bin/python results/run_ae_once.py
```

This launches paid inference and passes the native runner's `-y` flag. Optional
`--workers 1` through `--workers 5` controls condition-process concurrency (default
2). Seeds within each condition run serially via `--max-concurrent-runs 1` to keep
native process-global random state isolated between seeds. That is a scheduling
override, not a change to task, model or conversation settings. Default maximum
simultaneous trajectories is two, not two processes multiplied by two seed threads.

## Storage and provenance

Each invocation creates a unique UTC timestamp/UUID batch ID. A supplied
`--batch-id my-study-v1` must not already exist. Storage is:

```text
results/ae-batches/<batch-id>/
  manifest.json
  configs/<original-A-config-name>.yaml
  configs/<original-B-config-name>.yaml
  ...
  console-A.log
  console-B.log
  ...

colosseum/<configured experiment.output_dir>/<batch-id>/<native-timestamp>/
  config.json
  progress.json
  summary.csv
  summary.json
  summary.jsonl
  experiment.log
  runs/<model>/<sweep>/<native-run-id-with-seed>/
    run_config.json
    agent_prompts.json
    agent_prompts.md
    agent_turns.json
    agent_trajectories.json
    blackboards.json
    blackboard_*.txt
    tool_events.json
    metrics.json
    final_summary.json
    ...
```

The raw path remains under each config's native output root. Only the batch-ID
namespace is added with native `--out-dir`; Colosseum owns every file beneath its
native timestamp directory. Absolute configured output roots are supported too.

The manifest includes exact input hashes/snapshots, launch commands, Git commit
and dirty state, runtime source hashes, condition status, native output roots and
an explicit index of every condition/seed/run directory. It is updated atomically
as conditions complete. Five seeds should produce 25 indexed trajectories.

No pilot manifest, pilot console or earlier raw run is overwritten. Existing
batch namespaces are refused. Child failures retain console and partial native
outputs; there are no automatic retries. Ctrl-C terminates active child processes
and records interruption. Native partial progress may still say `running`; the
wrapper manifest records interruption independently. This wrapper does not resume
or silently combine prior attempts; use a fresh batch ID for a new attempt.

A batch is complete only when all five children succeed, native progress and
summary counts match the expected unique seeds, required per-run artifacts exist,
and reconstructed tasks, private costs, agent names and actual turn order match
across A–E **within each seed**. These checks run after inference and cannot
retroactively prevent costs if a validation failure is found.

A completed wrapper batch means execution/storage/matching checks passed; it does
not certify collusion or favorable outcomes. Existing routing/privacy tests and
configuration audits remain separate. The old `summarize_ae_once.py` and
`validate_saved_seed1.py` deliberately remain historical single-seed tools; do not
point them at these new manifests. Native summaries cover each configured seed;
new cross-condition analysis can use the manifest's `conditions[].trajectories`.

## Offline validation

```sh
colosseum/.venv/bin/python -m unittest discover -s results -p test_run_ae_once.py -v
```

The integration test launches the real native CLI for all 25 condition/seed
combinations using temporary five-seed configs, a mocked provider and blocked
network access. It verifies native storage, frozen inputs, matched instances and
protection of original configs, runtime source and pilot files. Other tests check
rejection of mismatched/duplicate seeds and preservation of failed attempts
without retries. Temporary integration outputs are removed after the test.
