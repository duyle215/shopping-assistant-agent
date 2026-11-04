# Agent evaluation

Code: `a9c6f23 (12 scenarios), 662be35 (19 scenarios), da3a4a1 (9 scenarios), 0cb1aa6 (6 scenarios)` · Model: `gemini-3.5-flash-lite` · Scenarios: 46 · Turns: 54 · Run: 2026-11-04 08:58 UTC

**Task success: 46/46 = 100%** (a scenario passes only if every check in every turn passes)

Merged report: 6 scenarios were re-run after fixes and replace their results from the previous full run (en-search-filter, en-cheapest, en-compare, en-order-confirmed, en-warranty, en-injection).

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
| Prompt tokens | 6,142 |
| Completion tokens | 214 |
| Latency | 14.9 s |

LLM judge on the last turn of 43 scenarios: grounded 42/43 = 98%, average helpfulness 4.9/5, polite 43/43.

| Scenario | Claims not supported by tool data |
| --- | --- |
| context-budget-carried-over | trong tầm ngân sách khoảng 25 triệu đồng |

## Failures

None.
