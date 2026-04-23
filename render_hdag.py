import json
import graphviz

# ── Expansion (unchanged) ──────────────────────────────────────────────────────

def expand(type_name, types, node_id):
    defn = types[type_name]

    if "children" not in defn:
        return (
            {node_id: type_name},
            [],
            {p: [(node_id, p)] for p in defn["ports"]["in"]},
            {p: [(node_id, p)] for p in defn["ports"]["out"]},
            None,
        )

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


# ── Compass assignment ─────────────────────────────────────────────────────────

IN_COMPASS  = ["nw", "w", "sw"]   # west side for arriving edges
OUT_COMPASS = ["ne", "e", "se"]   # east side for departing edges


def spread(ports, candidates):
    """Distribute port names across compass candidates as evenly as possible."""
    n = len(ports)
    if n == 0:
        return {}
    if n == 1:
        return {ports[0]: candidates[len(candidates) // 2]}
    result = {}
    for i, port in enumerate(ports):
        if n <= len(candidates):
            idx = round(i * (len(candidates) - 1) / (n - 1))
        else:
            idx = i % len(candidates)
        result[port] = candidates[idx]
    return result


def build_compass_maps(nodes, edges, types):
    """
    For every node return {port_name: compass_point}.
    Regular nodes: in-ports → west side, out-ports → east side.
    SOURCE:        all ports → east side (edges leave from it).
    SINK:          all ports → west side (edges arrive at it).
    """
    compass = {}

    for node_id, type_name in nodes.items():
        if node_id == "SOURCE":
            src_ports = list(dict.fromkeys(
                sp for sid, sp, _, _ in edges if sid == "SOURCE"))
            compass["SOURCE"] = spread(src_ports, OUT_COMPASS)
        elif node_id == "SINK":
            snk_ports = list(dict.fromkeys(
                dp for _, _, did, dp in edges if did == "SINK"))
            compass["SINK"] = spread(snk_ports, IN_COMPASS)
        else:
            defn = types[type_name]
            compass[node_id] = {
                **spread(defn["ports"]["in"],  IN_COMPASS),
                **spread(defn["ports"]["out"], OUT_COMPASS),
            }

    return compass


# ── Rendering ──────────────────────────────────────────────────────────────────

def short(node_id):
    parts = node_id.split(".")
    return ".".join(parts[1:]) if parts[0] == "root" else node_id


CLUSTER_FILLS  = ["#e8f0fe", "#fff3e0", "#e8f5e9", "#fce4ec"]
CLUSTER_COLORS = ["#3a7ebf", "#e65100", "#2e7d32", "#880e4f"]


def add_cluster(parent, cluster, node_types, depth=0):
    fill  = CLUSTER_FILLS[depth  % len(CLUSTER_FILLS)]
    color = CLUSTER_COLORS[depth % len(CLUSTER_COLORS)]

    with parent.subgraph(name=f"cluster_{cluster['node_id']}") as c:
        c.attr(label=f"{short(cluster['node_id'])}  [{cluster['type']}]",
               style="rounded,filled", fillcolor=fill, color=color,
               penwidth="2", fontname="Helvetica Bold", fontsize="11",
               fontcolor=color)

        for leaf_id in cluster["leaves"]:
            type_name = node_types[leaf_id]
            c.node(leaf_id,
                   f"{short(leaf_id)}\n[{type_name}]",
                   shape="box", style="filled,rounded",
                   fillcolor="white", color=color,
                   fontname="Helvetica", fontsize="11")

        for sub in cluster["subclusters"]:
            add_cluster(c, sub, node_types, depth + 1)


def render(nodes, edges, cluster, types, output_path="my_graph"):
    compass = build_compass_maps(nodes, edges, types)

    dot = graphviz.Digraph("GlobalDAG", format="svg")
    dot.attr(rankdir="LR", fontname="Helvetica", splines="spline",
             nodesep="0.6", ranksep="1.4", bgcolor="white")
    dot.attr("edge", color="#555555", fontname="Helvetica",
             fontsize="9", arrowsize="0.7")

    dot.node("SOURCE", "SOURCE", shape="invhouse", style="filled",
             fillcolor="#4caf50", fontcolor="white",
             fontname="Helvetica Bold", color="#2e7d32")
    dot.node("SINK", "SINK", shape="house", style="filled",
             fillcolor="#e65100", fontcolor="white",
             fontname="Helvetica Bold", color="#bf360c")

    add_cluster(dot, cluster, nodes)

    seen = set()
    for src_id, src_port, dst_id, dst_port in edges:
        key = (src_id, src_port, dst_id, dst_port)
        if key in seen:
            continue
        seen.add(key)
        src_cp = compass[src_id].get(src_port, "e")
        dst_cp = compass[dst_id].get(dst_port, "w")
        dot.edge(f"{src_id}:{src_cp}", f"{dst_id}:{dst_cp}",
                 label=f"{src_port}→{dst_port}")

    dot.render(output_path, cleanup=True)
    print(f"Rendered → {output_path}.svg")

    with open("hdag.dot", "w") as f:
        f.write(dot.source)

    # Inject HDAG metadata into the SVG for the viewer
    svg_path = f"{output_path}.svg"
    with open(svg_path) as f:
        svg_src = f.read()
    meta = json.dumps({"nodes": nodes, "types": types}, separators=(",", ":"))
    script_tag = f'\n<script type="application/json" id="hdag-data">{meta}</script>'
    svg_src = svg_src.replace("</svg>", script_tag + "\n</svg>")
    with open(svg_path, "w") as f:
        f.write(svg_src)
    print(f"Embedded metadata → {svg_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with open("hdag.json") as f:
        hdag = json.load(f)

    nodes, edges, cluster = build_global_dag(hdag)
    render(nodes, edges, cluster, hdag["types"], "my_graph")
