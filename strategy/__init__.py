"""lab-bittensor strategy package: outside-in tooling for validator strategy & ops.

Modules:
- data:               read-only fetch from Bittensor (mainnet/testnet) — `fetch_all_subnets`
- scoring:            pure metric computation — `score_subnet`, `rank_subnets`
- output:             render SubnetMetrics as CLI table or JSON
- subnet_evaluator:   CLI entry — `python -m strategy.subnet_evaluator`

Roadmap (.specs/project/ROADMAP.md):
- M2 ✓ subnet_evaluator (this module)
- M3 alpha-tao economics modeler (planned)
- M4 child-hotkey delegation manager (planned)
- M5 monitoring dashboard (planned)
- M6 automation orchestrator (planned)
"""
