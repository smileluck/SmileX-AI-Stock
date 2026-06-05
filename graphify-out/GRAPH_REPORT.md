# Graph Report - akshare-docs  (2026-06-05)

## Corpus Check
- Corpus is ~32,257 words - fits in a single context window. You may not need a graph.

## Summary
- 37 nodes · 42 edges · 6 communities (3 shown, 3 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 6 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_AKShare Core Platform|AKShare Core Platform]]
- [[_COMMUNITY_Deployment and Infrastructure|Deployment and Infrastructure]]
- [[_COMMUNITY_Backtesting and Visualization|Backtesting and Visualization]]
- [[_COMMUNITY_Build Configuration|Build Configuration]]
- [[_COMMUNITY_Heritage Data Libraries|Heritage Data Libraries]]
- [[_COMMUNITY_Core Dependencies|Core Dependencies]]

## God Nodes (most connected - your core abstractions)
1. `AKShare` - 27 edges
2. `AKTools` - 5 edges
3. `Backtrader` - 4 edges
4. `Docker` - 4 edges
5. `AKQuant` - 3 edges
6. `PyBroker` - 3 edges
7. `get_version_string()` - 2 edges
8. `Anaconda` - 2 edges
9. `pandas` - 2 edges
10. `NumPy` - 2 edges

## Surprising Connections (you probably didn't know these)
- `AKShare` --references--> `pandas`  [EXTRACTED]
  akshare-docs/introduction.md → akshare-docs/dependency.md
- `AKShare` --references--> `NumPy`  [EXTRACTED]
  akshare-docs/introduction.md → akshare-docs/dependency.md
- `AKShare` --references--> `Anaconda`  [EXTRACTED]
  akshare-docs/introduction.md → akshare-docs/anaconda.md
- `AKTools` --semantically_similar_to--> `Docker`  [INFERRED] [semantically similar]
  akshare-docs/deploy_http.md → akshare-docs/akdocker/akdocker.md
- `AKShare` --references--> `AKTools`  [EXTRACTED]
  akshare-docs/introduction.md → akshare-docs/deploy_http.md

## Hyperedges (group relationships)
- **AKShare-Compatible Backtesting Frameworks** — akshare, akquant, pybroker, backtrader [EXTRACTED 0.95]
- **AKShare Deployment Options** — akshare, aktools, docker [EXTRACTED 0.85]
- **Python Finance Data Libraries (Heritage)** — akshare, fushare, tushare, opendata [EXTRACTED 0.85]

## Communities (6 total, 3 thin omitted)

### Community 0 - "AKShare Core Platform"
Cohesion: 0.11
Nodes (18): AKShare, Apple M Series Chip Support, DataFrame Return Format, East Money (东方财富), AKShare Interface Naming Convention, mini-racer, mini-racer Dependency Selection, OpenData (+10 more)

### Community 1 - "Deployment and Infrastructure"
Cohesion: 0.29
Nodes (7): AKTools, Anaconda, Docker, FastAPI, JupyterLab, Typer, Uvicorn

### Community 2 - "Backtesting and Visualization"
Cohesion: 0.67
Nodes (4): AKQuant, Backtrader, matplotlib, PyBroker

## Knowledge Gaps
- **18 isolated node(s):** `mini-racer`, `FastAPI`, `Uvicorn`, `Typer`, `Sphinx` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AKShare` connect `AKShare Core Platform` to `Deployment and Infrastructure`, `Backtesting and Visualization`, `Heritage Data Libraries`, `Core Dependencies`?**
  _High betweenness centrality (0.744) - this node is a cross-community bridge._
- **Why does `AKTools` connect `Deployment and Infrastructure` to `AKShare Core Platform`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `Docker` connect `Deployment and Infrastructure` to `AKShare Core Platform`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Backtrader` (e.g. with `AKQuant` and `PyBroker`) actually correct?**
  _`Backtrader` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Docker` (e.g. with `AKTools` and `Anaconda`) actually correct?**
  _`Docker` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `AKQuant` (e.g. with `PyBroker` and `Backtrader`) actually correct?**
  _`AKQuant` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `get the version of akshare     :return: version number     :rtype: str, e.g. '`, `mini-racer`, `FastAPI` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._