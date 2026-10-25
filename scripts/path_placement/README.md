# Interior path-placement experiment

This earlier A/B follow-up moves the same coalition identities from path endpoints
to positions 2 and 5. It is separate from the shared-board report experiment.

See the [config and run guide](../../colosseum/experiments/collusion/configs/interior_placement/README.md).
From the repository root:

```sh
colosseum/.venv/bin/python scripts/path_placement/run_interior_ab.py --dry-run
colosseum/.venv/bin/python scripts/path_placement/run_interior_ab.py \
  --batch-id ab-interior-reproduction-001
```

The first command is offline. The second spends API credit, runs two condition
processes with serial seeds, and uses a fresh output namespace. It reuses the
common launcher in `scripts/shared_board/`, without changing task, prompt, model
or reward settings. Generated artifacts stay under the ignored results/native
output directories.
