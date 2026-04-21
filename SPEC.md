# HDAG JSON Specification

This document formally specifies the JSON format for defining a Hierarchical DAG (HDAG).

---

## Top-level structure

```json
{
  "types": { ... },
  "root":  "<TypeName>"
}
```

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `types` | object | ✓        | Map of type name → type definition |
| `root`  | string | ✓        | Name of the root type to expand into the global DAG |

---

## Type definition

Every entry in `types` is either a **leaf** or a **composite** type.

### Leaf type

A leaf has no children and no local DAG. It is a primitive node in the global DAG.

```json
"TypeName": {
  "ports": {
    "in":  ["port_a", "port_b"],
    "out": ["port_x", "port_y"]
  }
}
```

| Field        | Type            | Required | Description |
|--------------|-----------------|----------|-------------|
| `ports.in`   | array of string | ✓        | Named input ports |
| `ports.out`  | array of string | ✓        | Named output ports |

### Composite type

A composite type defines a set of named children and a local DAG over them.

```json
"TypeName": {
  "ports": {
    "in":  ["port_a"],
    "out": ["port_x", "port_y"]
  },
  "children": {
    "child_name": "ChildTypeName",
    ...
  },
  "dag": {
    "edges": [
      ["SOURCE.port_a",       "child1.in_port"],
      ["child1.out_port",     "child2.in_port"],
      ["child2.out_port",     "SINK.port_x"]
    ]
  }
}
```

| Field             | Type            | Required | Description |
|-------------------|-----------------|----------|-------------|
| `ports`           | object          | ✓        | Same as leaf — the **interface** this composite exposes to its parent |
| `children`        | object          | ✓        | Map of child instance name → type name |
| `dag.edges`       | array of pairs  | ✓        | Directed edges in the local DAG (see below) |

---

## Edges

Each edge is a two-element array:

```json
["<source_ref>", "<dest_ref>"]
```

A reference has the form `"<node>.<port>"` where `<node>` is one of:

| Node value  | Meaning |
|-------------|---------|
| `SOURCE`    | The composite's own **input** boundary (sentinel) |
| `SINK`      | The composite's own **output** boundary (sentinel) |
| `child_name`| A named child declared in `children` |

### Edge categories

| Edge form | Meaning |
|-----------|---------|
| `SOURCE.p → child.q` | The composite's input port `p` is delivered to child's input port `q`. Defines which leaf nodes receive external input. |
| `child.p → SINK.q`   | Child's output port `p` becomes the composite's output port `q`. Defines which leaf nodes provide external output. |
| `childA.p → childB.q`| Internal connection. During welding, the exit points of `childA` via port `p` are directly wired to the entry points of `childB` via port `q`. |

### Fan-out and fan-in

Multiple edges may share the same source reference (fan-out) or the same destination reference (fan-in):

```json
["child1.result", "child2.data"],
["child1.result", "child3.data"],   // fan-out from child1.result

["child2.done",   "SINK.finished"],
["child3.done",   "SINK.finished"]  // fan-in into SINK.finished
```

Both are valid. Fan-in at `SINK.port` means multiple leaf nodes contribute to the same output port of the composite.

---

## SOURCE and SINK sentinels

`SOURCE` and `SINK` are **reserved names** that must not be used as child instance names. They represent the input and output boundary of every composite node.

- All ports listed in `ports.in` of a composite **must** appear as the left-hand side of at least one `SOURCE.port → ...` edge.
- All ports listed in `ports.out` of a composite **must** appear as the right-hand side of at least one `... → SINK.port` edge.

At the **global level**, after full expansion, `SOURCE` and `SINK` become real nodes in the DAG wired to the root type's in_map and out_map respectively.

---

## Welding semantics (summary)

Given a fully expanded composite with child instances A and B, and a local edge `A.p → B.q`:

```
exits(A, p)   = { (leaf_id, leaf_port) | leaf is in A's expansion
                                       and leads to A's SINK via port p }

entries(B, q) = { (leaf_id, leaf_port) | leaf is in B's expansion
                                       and is reachable from B's SOURCE via port q }

weld: for every s in exits(A, p), for every d in entries(B, q):
          add global edge  s → d
```

Leaf nodes are their own exits and entries: `exits(L, p) = {(L, p)}`, `entries(L, q) = {(L, q)}`.

---

## Constraints

1. The `root` type must be defined in `types`.
2. Every type referenced in `children` must be defined in `types`.
3. The local DAG of every composite must be acyclic.
4. `SOURCE` and `SINK` are reserved and may not appear as child names.
5. Ports referenced in edges must exist on the corresponding type definition.

---

## Minimal example

```json
{
  "types": {
    "Double": {
      "ports": { "in": ["x"], "out": ["y"] }
    },
    "Pipeline": {
      "ports": { "in": ["input"], "out": ["output"] },
      "children": {
        "first":  "Double",
        "second": "Double"
      },
      "dag": {
        "edges": [
          ["SOURCE.input",  "first.x"],
          ["first.y",       "second.x"],
          ["second.y",      "SINK.output"]
        ]
      }
    }
  },
  "root": "Pipeline"
}
```

Global DAG: `SOURCE → first → second → SINK`
