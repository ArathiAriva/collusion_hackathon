# Shared-board report configurations (A–E)

These are the corrected shared-board configs used in the report. Use the
[run instructions](../../../../../scripts/shared_board/README.md) for setup,
offline previews, seed-1 pilots, main runs, output paths and tests.

| Condition | Public board | Private boards | Coalition instructions |
|---|---|---|---|
| A | All six agents | One assigned pair | Assigned pair |
| B | All six agents | None | Assigned pair |
| C | All six agents | One reference pair | None |
| D | All six agents | None | None |
| E | All six agents | All 15 pairs | None |

GPT-4o-mini/OpenRouter, six agents, eight Jira tasks, four planning rounds, three
model calls per turn, one iteration, temperature 0.7, 1500 output tokens, no
assignment filling, seeds 101–105. All conditions explicitly describe the common
board as public. C/D/E retain reference identities only for analysis.

Complete topology with consolidated channels supplies A–D's global board. E uses
unconsolidated complete channels for private pairs and an extra all-agent board;
its `secret_channel_enabled` flag does not make that global board private.

The separate [seed1_pilot/](seed1_pilot/) copies are development-only. The
[oversight extension F](oversight_pressure/README.md) equals A plus a configurable
notice. The A–E launcher reads exactly the five YAMLs in this directory, excluding
subdirectories. Generated `CONFIG_CHECK.json` files are local audit artifacts,
not source configuration or prerequisites.

See the [experiment plan](../../../../../docs/experiments/SHARED_BOARD_EXPERIMENT_PLAN.md).
