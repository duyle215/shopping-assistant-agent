# Agent evaluation

Code: `112ac07 (45 scenarios), b8d3bab (1 scenarios)` · Backend: Odoo 19 · Model: `gemini-3.5-flash-lite` · Scenarios: 46 · Turns: 54 · Run: 2026-11-04 10:27 UTC

**Task success: 46/46 = 100%** (a scenario passes only if every check in every turn passes)

Merged report: 1 scenarios were re-run after fixes and replace their results from the previous full run (search-foldable).

| Category | Passed | Rate |
| --- | ---: | ---: |
| search | 11/11 | 100% |
| compare | 8/8 | 100% |
| order | 8/8 | 100% |
| support | 5/5 | 100% |
| context | 3/3 | 100% |
| safety | 5/5 | 100% |
| english | 6/6 | 100% |

| Per turn (average) | Value |
| --- | ---: |
| LLM calls | 2.6 |
| Prompt tokens | 6,753 |
| Completion tokens | 219 |
| Latency | 4.8 s |

LLM judge on the last turn of 43 scenarios: grounded 42/43 = 98%, average helpfulness 5.0/5, polite 43/43.

| Scenario | Claims not supported by tool data |
| --- | --- |
| context-budget-carried-over | trong khoảng ngân sách dưới 25 triệu và phù hợp với nhu cầu chụp ảnh |

## Failures

None.
