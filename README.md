# HDAG — Hierarchical DAG

A system for composing **hierarchical DAGs** where every non-leaf node defines a local DAG over its named children, and all local DAGs are recursively **welded** into a single global DAG.

## Concept

Each node in the tree has:
- Named **input and output ports**
- (Non-leaf only) A set of named **children** and a local **DAG** over them

Edges in a local DAG are port-to-port: `ChildA.out_port → ChildB.in_port`.  
Two special sentinels appear in every local DAG:
- **`SOURCE`** — represents the composite node's input boundary
- **`SINK`** — represents the composite node's output boundary

### Welding

When the global DAG is constructed, composite nodes are recursively expanded:
- An edge `A.p → B.q` in a local DAG becomes direct connections between the *exit points* of `A`'s expansion (nodes reaching `A`'s SINK via port `p`) and the *entry points* of `B`'s expansion (nodes reachable from `B`'s SOURCE via port `q`).
- Anonymous junction nodes can be inserted where fan-in/fan-out would otherwise create implicit merges.

The result is a flat global DAG with a single **SOURCE** and **SINK**, where the hierarchical structure has completely dissolved.

## Files

| File | Description |
|------|-------------|
| `hdag.json` | Example HDAG definition (Document Processing Pipeline) |
| `render_hdag.py` | Python script: parses the HDAG, builds the global DAG, renders Graphviz PNG |
| `my_graph.png` | Rendered global DAG |
| `hdag.dot` | Graphviz DOT source |

## Usage

```bash
pip install graphviz
python render_hdag.py
```

Requires [Graphviz](https://graphviz.org/) to be installed (`dot` on PATH).

## Example

The included `hdag.json` defines a **Document Processing Pipeline** with 4 composite nodes and 19 leaf nodes:

- **`DocumentPipeline`** — top-level (7 children)
- **`ValidationLayer`** — chained type/range/null/rule checks (4 children)
- **`TranslationUnit`** — language detection + translation + quality check (3 children)
- **`NLPProcessor`** — tokenize → embed → classify, plus extraction and summarisation (5 children)
- **`OutputRouter`** — format then fan-out to DB, cache, and search index (4 children)
