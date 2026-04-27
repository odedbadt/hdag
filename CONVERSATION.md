# Design Conversation

This document captures the full design discussion that shaped the HDAG definition language and renderer.

---

## 1 — Core concept

**Idea:** A tree structure where every non-leaf node, alongside its list of named children, defines a DAG over those children. Each local DAG has a universal **SOURCE** (every node reachable from it) and **SINK** (every node can reach it).

**Welding rule:** All local DAGs are composed into a single global DAG. Given an edge A → B in a parent's local DAG:
- The nodes inside A's expansion that are connected to A's SINK become connected to every node inside B's expansion that is connected from B's SOURCE.
- Where fan-in or fan-out would be implicit, anonymous **welding junction nodes** can be inserted.

---

## 2 — Adding named ports

Each node exposes named **input ports** and **output ports**. Edges in a local DAG are port-to-port. The welding rule becomes port-aware:

- `exits(A, out_p)` = leaf nodes inside A's expansion that deliver output via port `out_p`
- `entries(B, in_q)` = leaf nodes inside B's expansion that receive input via port `in_q`
- For an edge `A.out_p → B.in_q`, connect every member of `exits(A, out_p)` to every member of `entries(B, in_q)`

---

## 3 — Self-referential sentinels (replacing SOURCE / SINK)

**Original design:** `SOURCE` and `SINK` were reserved global names appearing in every local DAG's edge list:
- `SOURCE.port → Child.port`
- `Child.port → SINK.port`

**Revised design:** Each composite node uses its **own name** as the sentinel. This removes reserved keywords and makes the boundary reference self-documenting:
- `validator->inputs->data → type_check->inputs->data`  *(old: `SOURCE.data → type_check.data`)*
- `rule_engine->outputs->valid → validator->outputs->valid`  *(old: `rule_engine.valid → SINK.valid`)*

The root node's implied name is `"root"`.

---

## 4 — Identity over types

**Original design:** Nodes referenced named *types* from a flat `types` dictionary. Two children of the same type shared a definition.

**Revised design:** Nodes are *identities*, not types. Each node in the JSON tree is a unique instance — the JSON structure itself is the hierarchy. No separate `types` dict, no `root` field.

Key consequences:
- `node T` at tree position X is distinct from `node T` at position Y even if they have the same name
- Ports are **inferred** from edge references; no explicit `ports.in` / `ports.out` declarations needed
- The JSON nesting directly mirrors the parent–child containment

---

## 5 — Replicas

A child can be declared as a set of replicas with optional per-replica variations:

```json
"worker": {
  "replicas": [
    {"params": {"mode": "fast"}},
    {"params": {"mode": "slow"}}
  ],
  "children": { "proc": {} },
  "dag": [
    ["worker->inputs->data", "proc->inputs->data"],
    ["proc->outputs->result", "worker->outputs->result"]
  ]
}
```

- Each variation object **deep-merges** onto the base definition (variation wins on conflicts).
- Expanded instances are named `worker[0]`, `worker[1]`, etc.
- `"worker->outputs->result"` in the parent DAG **broadcasts** to all replicas.
- `"worker[0]->outputs->result"` targets a specific replica.
- In the Graphviz output, structurally equivalent nodes across replicas are placed at the **same horizontal rank** via `{ rank=same; ... }` subgraphs.

---

## 6 — Global DAG construction

Starting from the root, expansion is recursive:

1. **Leaf nodes** return themselves; their ports are inferred from how the parent wires them.
2. **Composite nodes** expand each child, then process the local edge list:
   - `self->inputs->p → child->inputs->q` edges build the composite's **in_map**
   - `child->outputs->p → self->outputs->q` edges build the composite's **out_map**
   - All other edges are **welded**: exits of the source child connect directly to entries of the dest child
3. After full expansion, global `SOURCE` and `SINK` nodes are added and wired to the root's in_map / out_map.

Key properties of the resulting global DAG:
- **Acyclic** — guaranteed by the tree structure
- **Single SOURCE and SINK** — inherited from the root's boundary
- **Flat** — all composite boundaries dissolved; only leaf nodes remain as vertices

---

## 7 — Python renderer (`render_hdag.py`)

Implements:

- `expand(node_def, node_name, path, sentinel_name)` — recursive, identity-based; infers ports from DAG edges; handles replicas via deep-merge
- `collect_rank_groups(cluster)` — walks cluster tree to collect replica peer groups for `rank=same` enforcement
- `build_global_dag(hdag)` — calls expand on root, attaches global SOURCE/SINK, returns `(nodes, edges, cluster, rank_groups)`
- `render(nodes, edges, cluster, rank_groups, output_path)` — emits a Graphviz SVG with nested cluster subgraphs, spline edges, and `rank=same` for replica groups

The **cluster tree** mirrors the original hierarchy, allowing Graphviz `cluster_` subgraphs to be drawn nested — visually preserving the hierarchical structure even though the underlying graph is flat.

### CLI

```bash
python render_hdag.py                          # hdag.json → hdag.svg
python render_hdag.py my_pipeline.json         # → my_pipeline.svg
python render_hdag.py my_pipeline.json -o out  # → out.svg
```

---

## 8 — Example: Document Processing Pipeline (`hdag.json`)

```
root  (7 children)
├── reader
├── deduper
├── validator           ← composite (4 children)
│   ├── type_check
│   ├── range_check
│   ├── null_check
│   └── rule_engine
├── translate           ← composite (3 children)
│   ├── detector
│   ├── translator
│   └── quality
├── nlp                 ← composite (5 children)
│   ├── tokenizer
│   ├── embedder
│   ├── classifier
│   ├── extractor
│   └── summarizer
├── output              ← composite (4 children)
│   ├── formatter
│   ├── db
│   ├── cache
│   └── indexer
└── logger
```

Global DAG: **19 leaf nodes**, SOURCE and SINK, 31 welded edges.  
Notable weld: `validator.rule_engine` fans out to 6 leaf nodes across `translate` and `nlp` simultaneously.

