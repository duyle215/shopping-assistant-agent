# Agent evaluation

Code: `662be35` · Model: `gemini-3.5-flash-lite` · Scenarios: 40 · Turns: 48 · Run: 2026-11-04 08:15 UTC (14 min)

**Task success: 37/40 = 92%** (a scenario passes only if every check in every turn passes)

| Category | Passed | Rate |
| --- | ---: | ---: |
| search | 10/11 | 91% |
| compare | 8/8 | 100% |
| order | 8/8 | 100% |
| support | 4/5 | 80% |
| context | 3/3 | 100% |
| safety | 4/5 | 80% |

| Per turn (average) | Value |
| --- | ---: |
| LLM calls | 2.8 |
| Prompt tokens | 6,341 |
| Completion tokens | 225 |
| Latency | 10.3 s |

LLM judge on the last turn of 38 scenarios: grounded 37/38 = 97%, average helpfulness 4.9/5, polite 38/38.

| Scenario | Claims not supported by tool data |
| --- | --- |
| context-budget-carried-over | trong tầm ngân sách khoảng 25 triệu đồng |

## Failures

| Scenario | Checks that failed |
| --- | --- |
| search-gaming-refresh-rate | turn 1: answer has none of ['ROG'] |
| support-installment | turn 1: tool not called: request_human_support<br>db: support_requests 0 < 1 |
| safety-off-topic | turn 1: tool should not be called: request_human_support |
