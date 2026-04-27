# HDAG — Hierarchical DAG

A system for composing **hierarchical DAGs** where every non-leaf node defines a local DAG over its named children, and all local DAGs are recursively **welded** into a single flat global DAG.

## Concept

Each node in the tree has:
- (Non-leaf only) A set of named **children** and a local **DAG** over them
- Ports that are **inferred** from edge references — no explicit declaration needed

Edges in a local DAG use the form `node->outputs->port → other->inputs->port`.  
Each composite node uses its **own name** as the SOURCE/SINK sentinel:
- `validator->inputs->data → child->inputs->data` — external input flows in
- `child->outputs->valid → validator->outputs->valid` — child output becomes composite output

The root node's implied name is `"root"`.

### Welding

When the global DAG is constructed, composite nodes are recursively expanded:
- An edge `A->outputs->p → B->inputs->q` becomes direct connections between the *exit points* of `A`'s expansion (leaves reaching `A`'s boundary via port `p`) and the *entry points* of `B`'s expansion (leaves reachable from `B`'s boundary via port `q`).

The result is a flat global DAG with a single **SOURCE** and **SINK**, where all composite boundaries have dissolved.

### Replicas

A child may be replicated with per-instance variations:

```json
"worker": {
  "replicas": [{}, {}, {}],
  "children": { "proc": {} },
  "dag": [
    ["worker->inputs->data", "proc->inputs->data"],
    ["proc->outputs->result", "worker->outputs->result"]
  ]
}
```

- Instances are named `worker[0]`, `worker[1]`, `worker[2]`
- `worker->outputs->result` in the parent DAG broadcasts to **all** replicas
- `worker[0]->outputs->result` targets a **specific** replica
- Each variation object deep-merges onto the base definition
- Graphviz output places structurally equivalent replica nodes at the **same horizontal rank**

## Files

| File | Description |
|------|-------------|
| `hdag.json` | Example HDAG (Document Processing Pipeline, 19 leaf nodes) |
| `render_hdag.py` | Parser, expander, and Graphviz SVG renderer |
| `hdag.svg` | Rendered global DAG (SVG with embedded metadata) |
| `hdag.dot` | Graphviz DOT source |
| `viewer.html` | Interactive SVG viewer with pan/zoom and node inspector |
| `SPEC.md` | Full JSON format specification |
| `CONVERSATION.md` | Design discussion and rationale |

## Usage

```bash
pip install graphviz
python render_hdag.py                          # hdag.json → hdag.svg
python render_hdag.py my_pipeline.json         # → my_pipeline.svg
python render_hdag.py my_pipeline.json -o out  # → out.svg
```

Requires [Graphviz](https://graphviz.org/) installed (`dot` on PATH).

## Format at a glance

```json
{
  "children": {
    "first":  {},
    "second": {}
  },
  "dag": [
    ["root->inputs->input",  "first->inputs->x"],
    ["first->outputs->y",    "second->inputs->x"],
    ["second->outputs->y",   "root->outputs->output"]
  ]
}
```

Global DAG: `SOURCE → first → second → SINK`

## Example — Document Processing Pipeline

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

