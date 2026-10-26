# Product–Release / deadline pressure: A versus D

Use the [run guide](../../../../../scripts/release_pipeline/README.md). `study.yaml` declares seeds201–205, generated deadline_pressure only, Product–Release only, A/D, maximum2 parallel trajectories and6 model responses per actor turn. This is10 trajectories.

`A_assigned_pair_private_board.yaml` assigns the pair a local-utility objective and private board in addition to public discussion. `D_cooperative_public_board.yaml` keeps the shared objective and public board only; its reference pair is not disclosed as a coalition. Their combined difference does not isolate channel from objective effects.

Four roles, three planning rounds and one final phase. Current prompts v8 require final payoff calculation, with explicit six-response budgets and dynamic notices. Missing checks are retained; final submission should not be omitted when the budget ends. Other pairings/families and archived B/C are deferred; an explicit `--pair`/`--families` override is for separate diagnostics/follow-ups. Existing stopped v7 results remain unchanged.
