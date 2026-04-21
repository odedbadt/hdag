# Design Conversation

This document captures the design discussion that led to the HDAG definition language and renderer.

---

## 1 — Core concept

**Idea:** A tree structure where every non-leaf node, alongside its list of named children, defines a DAG over those children. Each local DAG has a universal **SOURCE** (every node reachable from it) and **SINK** (every node can reach it).

**Welding rule:** All local DAGs are composed into a single global DAG. Given an edge A → B in a parent's local DAG:
- The nodes inside A's expansion that are connected to A's SINK become connected to every node inside B's expansion that is connected from B's SOURCE.
- Where fan-in or fan-out would be implicit, anonymous **welding junction nodes** can be inserted.

---

## 2 — Adding named ports

Each node exposes named **input ports** and **output ports**. Edges in a local DAG are port-to-port:

```
ChildA.out_port  →  ChildB.in_port
```

The welding rule becomes port-aware:

- `exits(A, out_p)` = leaf nodes inside A's expansion that deliver output via port `out_p` (i.e. connected to A's SINK through that port)
- `entries(B, in_q)` = leaf nodes inside B's expansion that receive input via port `in_q` (i.e. reachable from B's SOURCE through that port)
- For an edge `A.out_p → B.in_q`, connect every member of `exits(A, out_p)` to every member of `entries(B, in_q)`

---

## 3 — SOURCE and SINK as global sentinels

Rather than designating specific children as source/sink, **SOURCE** and **SINK** are global sentinel names that appear directly in every local DAG's edge list:

- `SOURCE.port → Child.port` — the composite node's input port `port` flows into `Child`
- `Child.port → SINK.port` — `Child`'s output port becomes the composite node's output port

This makes the "border" of every composite node explicit in the edge list, with no implicit name-matching.

---

## 4 — Global DAG construction

Starting from the root type, the expansion is recursive:

1. Leaf nodes return themselves as a single node; their ports map 1-to-1.
2. Composite nodes expand each child, then process the local edge list:
   - `SOURCE.p → Child.q` edges build the composite's **in_map** (which leaf nodes receive the composite's input port `p`)
   - `Child.p → SINK.q` edges build the composite's **out_map** (which leaf nodes provide the composite's output port `q`)
   - All other edges are **welded**: the out_map entries of the source child are directly connected to the in_map entries of the destination child
3. After full expansion, global SOURCE and SINK nodes are added and wired to the root's in_map / out_map.

Key properties of the resulting global DAG:
- **Acyclic** — guaranteed by the tree structure preventing cross-level back-edges
- **Single SOURCE and SINK** — inherited from the root's boundary
- **Flat** — all composite boundaries dissolved; only leaf nodes remain as vertices

---

## 5 — Python renderer

`render_hdag.py` implements:

- `expand(type_name, types, node_id)` — recursive expansion returning nodes, edges, in_map, out_map, and a cluster tree
- `build_global_dag(hdag)` — calls expand on the root, then attaches global SOURCE/SINK
- `render(nodes, edges, cluster, path)` — emits a Graphviz PNG with nested cluster subgraphs (one per composite node) and spline edges

The **cluster tree** returned by `expand` mirrors the original hierarchy, allowing Graphviz `cluster_` subgraphs to be drawn nested — visually preserving the hierarchical structure even though the underlying graph is flat.

---

## 6 — Example: Document Processing Pipeline

```
DocumentPipeline  (7 children)
├── reader          [Reader]
├── deduper         [Deduper]
├── validator       [ValidationLayer]   ← composite
│   ├── type_check  [TypeCheck]
│   ├── range_check [RangeCheck]
│   ├── null_check  [NullCheck]
│   └── rule_engine [RuleEngine]
├── translate       [TranslationUnit]   ← composite
│   ├── detector    [LangDetector]
│   ├── translator  [Translator]
│   └── quality     [QualityCheck]
├── nlp             [NLPProcessor]      ← composite
│   ├── tokenizer   [Tokenizer]
│   ├── embedder    [Embedder]
│   ├── classifier  [Classifier]
│   ├── extractor   [Extractor]
│   └── summarizer  [Summarizer]
├── output          [OutputRouter]      ← composite
│   ├── formatter   [Formatter]
│   ├── db          [DBWriter]
│   ├── cache       [CacheWriter]
│   └── indexer     [SearchIndexer]
└── logger          [Logger]
```

Global DAG: **19 leaf nodes**, SOURCE and SINK, ~25 welded edges.
Notable weld: `validator.rule_engine.valid` fans out to 6 leaf nodes across two different composites (`TranslationUnit` and `NLPProcessor`) simultaneously.
