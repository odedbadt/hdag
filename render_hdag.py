import json
import graphviz

# ── Expansion ──────────────────────────────────────────────────────────────────

def expand(type_name, types, node_id):
    """
    Returns:
      nodes    : {node_id -> type_name}
      edges    : [(src_id, src_port, dst_id, dst_port)]
      in_map   : {port -> [(leaf_id, leaf_port)]}
      out_map  : {port -> [(leaf_id, leaf_port)]}
      cluster  : nested dict describing the subgraph hierarchy (None for leaves)
    """
    defn = types[type_name]

    if "children" not in defn:                        # ── leaf
        return (
            {node_id: type_name},
            [],
            {p: [(node_id, p)] for p in defn["ports"]["in"]},
            {p: [(node_id, p)] for p in defn["ports"]["out"]},
            None,
        )

    # ── composite
    nodes, edges = {}, []
    child_data   = {}
    cluster = {"type": type_name, "node_id": node_id, "leaves": [], "subclusters": []}

    for child_name, child_type in defn["children"].items():
        child_id = f"{node_id}.{child_name}"
        cn, ce, cim, com, child_cluster = expand(child_type, types, child_id)
        nodes.update(cn)
        edges.extend(ce)
        child_data[child_name] = (cim, com)
        if child_cluster is None:
            cluster["leaves"].append(child_id)
        else:
            cluster["subclusters"].append(child_cluster)

    my_in_map, my_out_map = {}, {}

    for src, dst in defn["dag"]["edges"]:
        src_node, src_port = src.split(".", 1)
        dst_node, dst_port = dst.split(".", 1)

        if src_node == "SOURCE":
            for ep in child_data[dst_node][0].get(dst_port, []):
                my_in_map.setdefault(src_port, []).append(ep)
        elif dst_node == "SINK":
            for ep in child_data[src_node][1].get(src_port, []):
                my_out_map.setdefault(dst_port, []).append(ep)
        else:
            for s in child_data[src_node][1].get(src_port, []):
                for d in child_data[dst_node][0].get(dst_port, []):
                    edges.append((s[0], s[1], d[0], d[1]))

    return nodes, edges, my_in_map, my_out_map, cluster


def build_global_dag(hdag):
    types     = hdag["types"]
    root_type = hdag["root"]
    nodes, edges, in_map, out_map, cluster = expand(root_type, types, "root")

    nodes["SOURCE"] = "SOURCE"
    nodes["SINK"]   = "SINK"

    for port, targets in in_map.items():
        for (t_id, t_port) in targets:
            edges.append(("SOURCE", port, t_id, t_port))

    for port, sources in out_map.items():
        for (s_id, s_port) in sources:
            edges.append((s_id, s_port, "SINK", port))

    return nodes, edges, cluster


# ── Rendering ──────────────────────────────────────────────────────────────────

def short(node_id):
    parts = node_id.split(".")
    return ".".join(parts[1:]) if parts[0] == "root" else node_id


# Alternating cluster fill colours by depth
CLUSTER_FILLS  = ["#e8f0fe", "#fff3e0", "#e8f5e9", "#fce4ec"]
CLUSTER_COLORS = ["#3a7ebf", "#e65100", "#2e7d32", "#880e4f"]

def add_cluster(parent, cluster, node_types, depth=0):
    fill  = CLUSTER_FILLS[depth  % len(CLUSTER_FILLS)]
    color = CLUSTER_COLORS[depth % len(CLUSTER_COLORS)]
    name  = f"cluster_{cluster['node_id']}"
    label = f"{short(cluster['node_id'])}  [{cluster['type']}]"

    with parent.subgraph(name=name) as c:
        c.attr(label=label, style="rounded,filled", fillcolor=fill,
               color=color, penwidth="2", fontname="Helvetica Bold",
               fontsize="11", fontcolor=color)

        for leaf_id in cluster["leaves"]:
            typ     = node_types[leaf_id]
            display = f"{short(leaf_id)}\n[{typ}]"
            c.node(leaf_id, display, shape="box", style="filled,rounded",
                   fillcolor="#ffffff", color=color)

        for sub in cluster["subclusters"]:
            add_cluster(c, sub, node_types, depth + 1)


def render(nodes, edges, cluster, output_path="my_graph"):
    dot = graphviz.Digraph("GlobalDAG", format="png")
    dot.attr(rankdir="LR", fontname="Helvetica", splines="spline",
             nodesep="0.7", ranksep="1.4", bgcolor="white")
    dot.attr("node", fontname="Helvetica", fontsize="12")
    dot.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

    # SOURCE / SINK outside any cluster
    dot.node("SOURCE", "SOURCE", shape="invhouse", style="filled",
             fillcolor="#4caf50", fontcolor="white", fontsize="13", penwidth="0")
    dot.node("SINK",   "SINK",   shape="house",    style="filled",
             fillcolor="#e65100", fontcolor="white", fontsize="13", penwidth="0")

    # Nested clusters for all composite nodes
    add_cluster(dot, cluster, nodes)

    # Edges (deduplicated)
    seen = set()
    for src_id, src_port, dst_id, dst_port in edges:
        key = (src_id, src_port, dst_id, dst_port)
        if key in seen:
            continue
        seen.add(key)
        dot.edge(src_id, dst_id, label=f"{src_port}→{dst_port}")

    dot.render(output_path, cleanup=True)
    print(f"Rendered → {output_path}.png")
    return dot.source


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with open("hdag.json") as f:
        hdag = json.load(f)

    nodes, edges, cluster = build_global_dag(hdag)
    dot_src = render(nodes, edges, cluster, "my_graph")

    with open("hdag.dot", "w") as f:
        f.write(dot_src)
