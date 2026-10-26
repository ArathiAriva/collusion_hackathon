# Recreate report figures and subset metrics

Run from the repository root after `./setup.sh colosseum`. These are the report
plotting programs previously kept under local `results/`; executable copies now
live here. They use Matplotlib and saved data, with no model calls. Historical
script snapshots in the archives remain unchanged.

First extract the committed bundles using the
[reviewer guide](../../artifacts/results/README.md). All output directories below
must be new; change their names for repeat runs.

```sh
# Fixed-pair and whole-team bars, with seed variation and the optimum range
colosseum/.venv/bin/python scripts/analysis/plot_abcd_separate.py \
  --batch /tmp/collusion-review/results/ae-batches/shared-board-eval-v2-seeds101-105 \
  --charts fixed-pair team-reward --formats svg pdf png \
  --output-dir /tmp/jira-report-bars

# Subset distributions and prominently marked reference pair
colosseum/.venv/bin/python scripts/analysis/plot_subset_distributions.py \
  --batch /tmp/collusion-review/results/ae-batches/shared-board-eval-v2-seeds101-105 \
  --output-dir /tmp/jira-subset-distributions --formats svg

# Derived dispersion, top-set rankings and reference-pair inclusion
colosseum/.venv/bin/python scripts/analysis/derive_subset_metrics.py \
  --batch /tmp/collusion-review/results/ae-batches/shared-board-eval-v2-seeds101-105 \
  --output-dir /tmp/jira-derived-metrics
colosseum/.venv/bin/python scripts/analysis/plot_subset_dispersion.py \
  --metrics-dir /tmp/jira-derived-metrics --output-dir /tmp/jira-dispersion

# Paired D/E extension
colosseum/.venv/bin/python scripts/analysis/plot_de_paired.py \
  --batch /tmp/collusion-review/results/ae-batches/shared-board-eval-v2-seeds101-105 \
  --comparison DE --output-dir /tmp/jira-de
```

Other supported programs are `plot_fixed_pair_ranges.py` and `plot_subset_kde.py`;
use `--help` for options. KDE is descriptive smoothing, not a fitted normal model.
Error bars are sample standard deviations across matched seeds, not confidence
intervals. Reference identities in C/D/E have no coalition assignment. Selecting
the highest subset gap alone is not evidence of collusive intent.

```sh
colosseum/.venv/bin/python -m unittest discover -s scripts/analysis -p 'test_*.py'
```
