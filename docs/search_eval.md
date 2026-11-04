# Search evaluation

Embedding model: `gemini-embedding-001` · Catalog: 30 phones · Queries: 30 name, 10 need

- **name**: the user types a model name, often shortened or lowercase (`ip 16`, `A55`, `redmi 13c`).
- **need**: the user describes a feature mentioned in the product page (`camera Leica`, `màn hình gập`).

| Queries | Mode | Hit@1 | Hit@3 | MRR |
| --- | --- | ---: | ---: | ---: |
| name | dense | 100% | 100% | 1.00 |
| name | keyword | 100% | 100% | 1.00 |
| name | hybrid | 100% | 100% | 1.00 |
| need | dense | 90% | 90% | 0.93 |
| need | keyword | 0% | 0% | 0.00 |
| need | hybrid | 90% | 90% | 0.93 |

## Hybrid misses (expected product not ranked first)

| Queries | Query | Expected | Hybrid top 3 |
| --- | --- | --- | --- |
| need | khoanh tròn để tìm kiếm, phiên dịch trực tiếp | [6] | [19, 22, 13] |
