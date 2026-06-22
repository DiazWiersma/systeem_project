# UNGC Explorer - Poster Statistics

This document contains concise statistics suitable for a poster about the
UNGC Explorer. All figures are calculated from `backend/ungdc.db`.

## Dataset at a glance

| Statistic | Value |
|---|---:|
| UN General Debate speeches | **11,127** |
| Words | **31.2 million** |
| Countries represented | **199** |
| Years covered | **80** |
| Coverage period | **1946-2025** |
| Topics | **97** |

## Topic analysis

| Statistic | Value |
|---|---:|
| Speech-topic connections | **33,932** |
| Average topics per speech | **3.05** |
| Median topics per speech | **3** |
| Speeches covering multiple topics | **8,640 (77.7%)** |
| Speeches covering one topic | **2,487 (22.3%)** |
| Maximum topics assigned to one speech | **6** |
| Labelled text chunks | **93,609** |
| Chunk-topic connections | **142,063** |

## Top five most-used topics

Topic counts are measured at **speech level**. A speech is counted once for a
topic, even when several chunks from that speech match the same topic.

| Rank | Topic | Speeches | Share of all speeches |
|---:|---|---:|---:|
| 1 | Climate Change & Sustainability | **2,416** | **21.7%** |
| 2 | Democratic Reform & Human Rights | **1,881** | **16.9%** |
| 3 | Lebanon & Arab-Israeli Relations | **1,603** | **14.4%** |
| 4 | Southern Africa - Decolonization & Apartheid | **1,572** | **14.1%** |
| 5 | New Zealand & Pacific Nuclear Issues | **1,316** | **11.8%** |

The percentages overlap because a speech can cover several topics. They should
therefore not be added together.

## Suggested poster visualisations

- A horizontal bar chart showing the five most-used topics.
- A timeline showing how topic prominence changes between 1946 and 2025.
- A world map showing matching speeches by country.
- A comparison of single-topic and multi-topic speeches.
- The most prominent topic in each decade.

## Methodological note

Speeches were divided into chunks of 150 words with an overlap of 30 words.
Topics were assigned to these chunks and then aggregated to speech level. This
allows one speech to cover multiple topics without counting repeated matching
chunks as separate speeches.
