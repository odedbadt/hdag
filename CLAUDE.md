# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install graphviz                              # only Python dependency; also requires `dot` on PATH
python render_hdag.py                             # hdag.json → hdag.svg (+ hdag.dot)
python render_hdag.py my_pipeline.json            # → my_pipeline.svg
python render_hdag.py my_pipeline.json -o out     # → out.svg

# Viewer is static — open viewer.html directly, or serve the directory:
python -m http.server 8000                        # then http://localhost:8000/viewer.html
python -m http.server 8000                        # http://localhost:8000/viewer.html?svg=hdag.svg
```

There is no test suite, lint config, or build step. To validate a change to `render_hdag.py`, re-run it on `hdag.json` and inspect the output `.svg`/`.dot` (or open in `viewer.html`).

## Architecture

This is a two-component system: a **Python renderer** that flattens a hierarchical DAG into a Graphviz drawing, and a **static SVG viewer** that reads metadata embedded in that drawing.

### The HDAG model (read SPEC.md before editing render_hdag.py)

Every node is either a **leaf** `{}` or a **composite** `{children, dag}`. Edges are strings of the form `node->inputs|outputs->port`. Three things make this format unusual and constrain the renderer:

1. **Self-referential sentinel.** Inside a composite named `validator`, an edge `validator->inputs->data → type_check->inputs->data` means "external input flows in." The composite uses *its own name* as the boundary handle. The expander tracks this via a `sentinel_name` parameter — for replicas, `sentinel_name` stays as the base child name (`worker`) even though the instance name becomes `worker[0]`, so internal edges still resolve.
2. **Ports are inferred, not declared.** Port lists for each node come from scanning edge references. This happens in two places: `expand()` infers child leaf ports from the local DAG (first pass before expansion), and `build_compass_maps()` re-derives ports from the final flat edge list for layout.
3. **Welding.** Composite boundaries dissolve in the global DAG. An edge `A->outputs->p → B->inputs->q` becomes a Cartesian product of `exits(A, p) × entries(B, q)`, where exits/entries are the sets of leaf endpoints reaching A's `p` boundary or reachable from B's `q` boundary. This is implemented by `expand()` returning `(in_map, out_map)` to its parent, which the parent uses as the endpoint sets for cross-child edges.

### `render_hdag.py` flow

`build_global_dag` → `expand(hdag, 'root', 'root')` recursively → `(nodes, edges, in_map, out_map, cluster, rank_groups)` → `render(...)` → Graphviz SVG, then post-process to inject `<script id="hdag-data">` JSON metadata (`{nodes, ports}`) before `</svg>` so the viewer can show node/port info on click.

`expand()` does two passes per composite: (1) infer each child's ports from `dag_edges`, then expand children (recursing). Leaves get their `in_map`/`out_map` synthesized from inferred ports here. (2) Walk `dag_edges` again — classify each as source (sentinel→child), sink (child→sentinel), or weld (child→child) and emit edges or update the parent's `in_map`/`out_map` accordingly.

**Replicas:** `child_node['replicas']` is a list of variation dicts deep-merged onto the base; each becomes an instance `child[i]` with `child` as `sentinel_name`. The parent DAG's `child->...` references broadcast to all replicas; `child[i]->...` targets one. After expansion, `cluster['rank_groups']` collects sets of structurally-equivalent leaf IDs across replicas (matched by relative sub-path) so they render at the same Graphviz rank.

**Compass assignment** (`build_compass_maps`) distributes inferred ports across the three west-side compass points (`nw`, `w`, `sw`) for inputs and east-side (`ne`, `e`, `se`) for outputs. This is the layout glue that lets multi-port nodes render readably in `rankdir=LR`.

### Node ID convention

Internal node IDs are dot-paths from the root: `root.validator.type_check`, `root.worker[0].proc`. The `short()` helper strips the leading `root.` for display. The viewer relies on this convention to derive parent/breadcrumb info from the ID alone.

### Viewer ↔ renderer contract

The viewer (`viewer.js`) loads SVGs by setting `innerHTML` on a wrapper `<div>`. Two quirks the renderer must respect:

- The viewer strips `<?xml ... ?>` and `<!DOCTYPE ...>` preambles before injection (innerHTML can't parse them).
- Graphviz emits `width`/`height` in `pt` units; the viewer overrides them with px values from `viewBox.baseVal` for reliable sizing across browsers.

Click-to-inspect works by reading the `<title>` element inside each `g.node` (the node ID) and looking it up in the embedded `hdag-data` JSON. If you change the metadata schema in `render_hdag.py`, update `showModal()` in `viewer.js`.
