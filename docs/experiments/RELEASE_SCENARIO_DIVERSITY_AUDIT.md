# Offline release-scenario diversity audit

Date: October 25, 2026. Status: exploratory design arithmetic; no agent-environment implementation or model evaluation.

## Method

Generated 120 synthetic scenarios, 20 in each of six manually specified families, using seed 20261025. Enumerated all 144 assignments per scenario. Repeated the same scenario inputs under five parameter settings: the main design (economic effort weight 3, local cost aversion 0.2); effort weights 2 and 4; and local aversion 0.1 and 0.4. This evaluates 86,400 complete assignments across 600 scenario/setting combinations. No inference calls, Terrarium execution, CoLLAB changes, or paid services were used.

The standalone analysis is [audit.py](release_design_audit/audit.py); exact generated scenarios, settings, detailed summaries, and source hash are in [results.json](release_design_audit/results.json). Reproduce from the hackathon root with `python3 docs/experiments/release_design_audit/audit.py`. This is a design-audit calculator, not the production environment, launcher, or task breakdown.

## Optimal decision diversity

Main-setting counts; all optimum ties are retained. In this sample ties do not cross these decision categories.

| Optimal decision | Scenarios |
| --- | ---: |
| limited / standard / ordinary_go | 33 |
| full / guarded / exception_go | 27 |
| full / guarded / ordinary_go | 20 |
| defer | 20 |
| full / standard / ordinary_go | 20 |

| Family | Scenarios | Minimum optimal reward | Maximum optimal reward |
| --- | ---: | ---: | ---: |
| deadline pressure | 20 | 12.90 | 57.29 |
| legitimate exception | 20 | 37.52 | 75.97 |
| operational readiness | 20 | 45.76 | 80.77 |
| scope compromise | 20 | 18.57 | 58.00 |
| justified deferral | 20 | -13.50 | -13.50 |
| over caution | 20 | 63.72 | 98.37 |

The overall nominal-optimum range is -13.50 to 98.37. At compliant optima, nominal reward equals economic value. Deferral has the same reward across these templates because the no-deployment cost schedule is fixed. This is a limitation of initialization diversity, not 20 independent estimates of a meaningful changing deferral payoff.

Family templates deliberately construct qualitatively different situations, so observing different optima is a coverage check, not an empirical finding about real release frequencies. Most families have a prescribed winning category. The scope-compromise family provides a boundary tradeoff: 13 limited ordinary releases versus 7 full guarded exceptions under the main setting. Holding scenarios fixed, changing effort weight to 2 yields a 10/10 split; weight 4 yields 17/3. Local utility aversion changes coalition opportunities, not organizational optima, by construction.

## Pair opportunity diversity

Each count is out of the same 120 scenarios. The reference is an exact cooperative-optimal assignment, not a sampled model D trajectory. Hold outsiders' decisions fixed; search for lower-nominal-reward assignments in which both pair members change their owned decisions and both strictly improve their auxiliary utility. Inspect every optimum tie; any-optimum and every-optimum counts coincide in this sample. No minimum effect-size threshold is applied.

| Pair | Both members can gain through a harmful joint deviation | Harmful mean pair gain, possibly one member losing | Joint action necessary for any harmful mutual gain from at least one optimum |
| --- | ---: | ---: | ---: |
| Product+QA | 0 | 7 | 0 |
| Product+Ops | 2 | 78 | 1 |
| Product+Release | 49 | 80 | 0 |
| QA+Ops | 47 | 100 | 0 |
| QA+Release | 0 | 24 | 0 |
| Ops+Release | 6 | 64 | 0 |

The joint-necessity column asks whether a joint mutually beneficial harmful deviation exists while neither member alone can produce any mutually beneficial harmful deviation from that reference. It does not ask whether joint action achieves a larger gain than the best unilateral action. A zero therefore does not prove coordination has no incremental value.

Important design findings:

- Product+QA and QA+Release have no strict mutual-benefit opportunity from the tested optima, including the four sensitivity settings. Their pair-mean objectives can improve in some scenarios, but that may require one member to lose. Do not describe all six pairings as naturally mutually incentivized.
- Product+Release and QA+Ops have many mutually beneficial harmful deviations, but unilateral actions can also produce mutual gains. Opportunities alone are not coalition-specific evidence.
- A unilateral scope change can make an outsider's previously truthful QA record stale: that is included in static fixed-outsider arithmetic but does not model a QA agent reassessing the new scope. Accordingly, some opportunity counts include protocol-sensitive counterfactuals. This strengthens the need to distinguish structural diagnostics from meeting behavior.
- Fixing the final sequence P -> Q -> O -> R means QA can assess the chosen scope before Release decides. Actual trajectories may avoid stale-record outcomes that appear in frozen-outsider calculations. Do not use those calculations as predictions of success.
- QA+Ops can improve through deferral even when one member alone could block the release. For claims that collusion caused the harm, transcripts and matched unilateral-capability comparisons are essential.

## Sensitivity of strict mutual-benefit opportunities

Counts below retain all six pairs; these are exploratory checks, not independent model replications.

| Setting | Product+QA | Product+Ops | Product+Release | QA+Ops | QA+Release | Ops+Release |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 0 | 2 | 49 | 47 | 0 | 6 |
| economic_cost_weight_2 | 0 | 3 | 46 | 50 | 0 | 9 |
| economic_cost_weight_4 | 0 | 1 | 53 | 43 | 0 | 3 |
| local_cost_aversion_0.1 | 0 | 5 | 52 | 47 | 0 | 6 |
| local_cost_aversion_0.4 | 0 | 0 | 44 | 47 | 0 | 7 |

## Checks and limitations

For every scenario/setting, verified finite-domain cost caps, exact credited-reward sums, strict dominance of admissible over inadmissible assignments using H, existence of an admissible solution, and equality of constrained-economic and penalized-nominal optima. The audit does not run prompts, measure LLM behavior, validate private-information delivery, compute actual matched A-D effects, or score collusive messages. It is not an independent implementation verification because the calculator directly encodes the proposed design.

The scenarios are development artifacts. They are not the final generator or a held-out evaluation set. Cost coefficients mostly remain fixed; no-deployment workload does not vary. No realistic prevalence or statistical power claim is warranted. All opportunity conclusions are conditional on these templates, the auxiliary utilities, strict benefit definition, and cooperative-optimal baselines. Real D trajectories can be suboptimal and support different deviations.

## Decisions informed before implementation

The environment can exhibit varied organizational optima. However, it is not yet justified to claim six equally motivated or jointly necessary coalition mechanisms. Keep low-opportunity pairings as informative controls, or explicitly revise the research scope/incentive model after reviewing these results. Do not silently alter incentives to force positives. Investigate protocol-aware opportunity analysis and graded joint-versus-unilateral benefit before interpreting fixed-outsider scores as coalition mechanisms. Task breakdown remains pending approval.
