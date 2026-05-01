# HDAG JSON Specification

This document formally specifies the JSON format for defining a Hierarchical DAG (HDAG).

---

## Design principles

- **Identity over type**: every node in the JSON tree is a unique instance. Two nodes with the same name at different tree positions are distinct entities.
- **Structure mirrors hierarchy**: the JSON nesting directly reflects the parent–child containment, with no separate type dictionary.
- **Ports inferred**: input and output ports are not declared explicitly; they are derived from edge references.
- **Self-referential sentinels**: a composite node uses its own name to reference its external boundary in its local DAG.

---

## Top-level structure

The root of the HDAG is a node whose instance name is always `"root"`. The top-level JSON object **is** the root node definition.

```json
{
  "children": { ... },
  "dag":      [ ... ]
}
```

---

## Node definition

Every node in the hierarchy is either a **leaf** or a **composite**.

### Leaf node

A leaf has no children. Its ports are inferred from how it is wired in its parent's `dag`.

```json
"node_name": {}
```

### Composite node

A composite node declares named children and a local DAG over them.

```json
"node_name": {
  "children": {
    "child_a": { ... },
    "child_b": { ... }
  },
  "dag": [
    ["node_name->inputs->port_a",  "child_a->inputs->p"],
    ["child_a->outputs->q",        "child_b->inputs->r"],
    ["child_b->outputs->s",        "node_name->outputs->port_x"]
  ]
}
```

| Field      | Required | Description |
|------------|----------|-------------|
| `children` | ✓        | Map of child instance name → node definition |
| `dag`      | ✓        | Array of directed edges `[source_ref, dest_ref]` |

---

## Edge syntax

Each edge is a two-element array `["<source_ref>", "<dest_ref>"]`.

Every reference has the form:

```
"<node_name>->inputs-><port>"    // feed data into node_name's input port
"<node_name>->outputs-><port>"   // read data from node_name's output port
```

| Reference form | Meaning |
|----------------|---------|
| `self->inputs->p` | The composite's own **input** boundary (self = the composite's name) |
| `self->outputs->p`| The composite's own **output** boundary |
| `child->inputs->q` | Feed into a child's input port |
| `child->outputs->q`| Read from a child's output port |

### Edge categories

| Pattern | Semantics |
|---------|-----------|
| `self->inputs->p → child->inputs->q` | External input port `p` flows into child's input port `q` |
| `child->outputs->p → self->outputs->q` | Child's output port `p` becomes the composite's output port `q` |
| `childA->outputs->p → childB->inputs->q` | Internal weld: childA's exits via port `p` connect directly to childB's entries via port `q` |

### Fan-out and fan-in

Multiple edges may share the same source (fan-out) or the same destination (fan-in):

```json
["child1->outputs->result", "child2->inputs->data"],
["child1->outputs->result", "child3->inputs->data"],

["child2->outputs->done", "self->outputs->finished"],
["child3->outputs->done", "self->outputs->finished"]
```

---

## Replicas

A child can be replicated multiple times with optional variations:

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

- Each object in `"replicas"` is **deep-merged** on top of the base node definition (the replica variation wins on conflicts).
- The resulting expanded instances are named `worker[0]`, `worker[1]`, etc.
- In the parent's DAG, `"worker->outputs->result"` **broadcasts** to all replicas.
- A specific replica is addressed as `"worker[0]->outputs->result"`.

---

## Welding semantics

Given a composite with children A and B, and a local edge `A->outputs->p → B->inputs->q`:

```
exits(A, p)   = { (leaf_id, port) | leaf is in A's expansion
                                  and leads to A's boundary via output port p }

entries(B, q) = { (leaf_id, port) | leaf is in B's expansion
                                  and is reachable from B's boundary via input port q }

weld: for every s in exits(A, p), for every d in entries(B, q):
          add global edge  s → d
```

Leaf nodes are their own exits and entries: `exits(L, p) = {(L, p)}`, `entries(L, q) = {(L, q)}`.

---

## Global DAG

After full recursive expansion:
- All composite boundaries dissolve; only leaf nodes remain as vertices.
- Global `SOURCE` and `SINK` nodes are added, wired to the root node's in_map and out_map.
- The result is a flat, acyclic graph with a single SOURCE and SINK.

---

## Sentinel override

By default the self-reference sentinel is the composite node's own name. A composite may override this by declaring a `sentinel` field, which is required when a child shares the parent's name (otherwise edges referencing that name would resolve as boundary references rather than as child references).

```json
"validator": {
  "sentinel": "_self",
  "children": {
    "validator": {},
    "logger":    {}
  },
  "dag": [
    ["_self->inputs->data",       "validator->inputs->data"],
    ["validator->outputs->valid", "logger->inputs->event"],
    ["logger->outputs->ack",      "_self->outputs->done"]
  ]
}
```

The override only changes which token denotes the boundary inside this composite's local dag. The instance's own name (`validator`, used for path/display) is unchanged.

---

## Constraints

1. Every type referenced in `children` must be defined inline.
2. The local DAG of every composite must be acyclic.
3. The self-reference sentinel must not collide with any direct child name. If a child reuses the parent's name, the parent must declare a distinct `sentinel`.
4. Replica indices in `child[i]->...` must be within range.

---

## Minimal example

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
