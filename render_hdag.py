import json
import re
import graphviz

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_ref(ref):
    """Parse 'A->outputs->x' → ('A', 'outputs', 'x')."""
    parts = ref.split('->')
    if len(parts) != 3:
        raise ValueError(f"Invalid port reference: {ref!r}. Expected 'node->inputs/outputs->port'")
    node, direction, port = parts
    if direction not in ('inputs', 'outputs'):
        raise ValueError(f"Invalid direction {direction!r} in {ref!r}")
    return node, direction, port


def replica_index(name):
    """'A[0]' → ('A', 0)   or   'A' → ('A', None)."""
    m = re.match(r'^(.+)\[(\d+)\]$', name)
    return (m.group(1), int(m.group(2))) if m else (name, None)


def deep_merge(base, override):
    """Deep-merge override onto a copy of base; override wins on conflicts."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ── Expansion ──────────────────────────────────────────────────────────────────

def expand(node_def, node_name, path, sentinel_name=None):
    """
    Recursively expand a node.

    Parameters
    ----------
    node_def      : dict  — the JSON definition for this node
    node_name     : str   — instance name (may be 'A[0]' for replicas)
    path          : str   — fully-qualified dot-path id, e.g. 'root.validator.type_check'
    sentinel_name : str   — name to match for self-reference in dag edges;
                            defaults to node_name (replica base names pass the
                            original child_name so 'worker->inputs->x' still
                            matches inside 'worker[0]')

    Returns
    -------
    nodes   : {node_id: display_name}
    edges   : [(src_id, src_port, dst_id, dst_port)]
    in_map  : {port: [(node_id, port)]}  — entry points for this node
    out_map : {port: [(node_id, port)]}  — exit points for this node
    cluster : cluster dict or None for leaves
    """
    if sentinel_name is None:
        sentinel_name = node_name

    # ── Leaf ──────────────────────────────────────────────────────────────────
    if 'children' not in node_def:
        return {path: node_name}, [], None, None, None

    # ── Composite ─────────────────────────────────────────────────────────────
    children_def = node_def.get('children', {})
    dag_edges    = node_def.get('dag', [])

    # First pass: infer ports for each direct child from dag_edges
    child_inferred_ports = {}
    for src_ref, dst_ref in dag_edges:
        for ref in (src_ref, dst_ref):
            ref_node, direction, port = parse_ref(ref)
            base_ref, _ = replica_index(ref_node)
            if base_ref == sentinel_name:
                continue  # self-reference — skip
            cp = child_inferred_ports.setdefault(base_ref, {'in': [], 'out': []})
            key = 'in' if direction == 'inputs' else 'out'
            if port not in cp[key]:
                cp[key].append(port)

    nodes, edges = {}, []
    child_data   = {}  # child_name → list of (rname, in_map, out_map)
    cluster      = {
        'node_name': node_name,
        'node_id':   path,
        'leaves':    [],
        'subclusters': [],
    }

    def _expand_one(c_name, c_def, r_name, r_sentinel):
        child_id = f"{path}.{r_name}"
        cn, ce, cim, com, child_cluster = expand(c_def, r_name, child_id, sentinel_name=r_sentinel)
        nodes.update(cn)
        edges.extend(ce)
        if cim is None:  # leaf — build maps from inferred ports
            ports_info = child_inferred_ports.get(c_name, {'in': [], 'out': []})
            cim = {p: [(child_id, p)] for p in ports_info['in']}
            com = {p: [(child_id, p)] for p in ports_info['out']}
        if child_cluster is None:
            cluster['leaves'].append(child_id)
        else:
            cluster['subclusters'].append(child_cluster)
        return cim, com

    for child_name, child_node in children_def.items():
        if 'replicas' in child_node:
            base         = {k: v for k, v in child_node.items() if k != 'replicas'}
            replica_list = []
            for i, variation in enumerate(child_node['replicas']):
                merged = deep_merge(base, variation)
                rname  = f"{child_name}[{i}]"
                cim, com = _expand_one(child_name, merged, rname, child_name)
                replica_list.append((rname, cim, com))
            child_data[child_name] = replica_list
        else:
            cim, com = _expand_one(child_name, child_node, child_name, child_name)
            child_data[child_name] = [(child_name, cim, com)]

    # Helper: collect endpoints from one or all replicas of a child
    def get_replicas(base_name, idx):
        replicas = child_data.get(base_name, [])
        if idx is not None:
            return [replicas[idx]] if idx < len(replicas) else []
        return replicas

    # Second pass: process dag edges → build in_map / out_map / weld edges
    my_in_map, my_out_map = {}, {}

    for src_ref, dst_ref in dag_edges:
        src_node, src_dir, src_port = parse_ref(src_ref)
        dst_node, dst_dir, dst_port = parse_ref(dst_ref)
        src_base, src_idx = replica_index(src_node)
        dst_base, dst_idx = replica_index(dst_node)

        is_source = (src_base == sentinel_name and src_dir == 'inputs')
        is_sink   = (dst_base == sentinel_name and dst_dir == 'outputs')

        if not is_source:
            src_eps = [ep
                       for (_, cim, com) in get_replicas(src_base, src_idx)
                       for ep in com.get(src_port, [])]
        if not is_sink:
            dst_eps = [ep
                       for (_, cim, com) in get_replicas(dst_base, dst_idx)
                       for ep in cim.get(dst_port, [])]

        if is_source:
            for ep in dst_eps:
                my_in_map.setdefault(src_port, []).append(ep)
        elif is_sink:
            for ep in src_eps:
                my_out_map.setdefault(dst_port, []).append(ep)
        else:
            for s in src_eps:
                for d in dst_eps:
                    edges.append((s[0], s[1], d[0], d[1]))

    return nodes, edges, my_in_map, my_out_map, cluster


def build_global_dag(hdag):
    nodes, edges, in_map, out_map, cluster = expand(hdag, 'root', 'root')

    nodes['SOURCE'] = 'SOURCE'
    nodes['SINK']   = 'SINK'

    for port, targets in in_map.items():
        for (t_id, t_port) in targets:
            edges.append(('SOURCE', port, t_id, t_port))

    for port, sources in out_map.items():
        for (s_id, s_port) in sources:
            edges.append((s_id, s_port, 'SINK', port))

    return nodes, edges, cluster


# ── Compass assignment ─────────────────────────────────────────────────────────

IN_COMPASS  = ["nw", "w", "sw"]
OUT_COMPASS = ["ne", "e", "se"]


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


def build_compass_maps(nodes, edges):
    """
    For every node return {port_name: compass_point}.
    Ports are inferred from edge usage.
    SOURCE: all ports → east side.  SINK: all ports → west side.
    """
    # Collect ordered, deduplicated port lists from edge usage
    in_ports  = {nid: list(dict.fromkeys(dp for _, _, did, dp in edges if did == nid))
                 for nid in nodes}
    out_ports = {nid: list(dict.fromkeys(sp for sid, sp, _, _ in edges if sid == nid))
                 for nid in nodes}

    compass = {}
    for node_id in nodes:
        if node_id == 'SOURCE':
            compass['SOURCE'] = spread(out_ports['SOURCE'], OUT_COMPASS)
        elif node_id == 'SINK':
            compass['SINK'] = spread(in_ports['SINK'], IN_COMPASS)
        else:
            compass[node_id] = {
                **spread(in_ports[node_id],  IN_COMPASS),
                **spread(out_ports[node_id], OUT_COMPASS),
            }

    return compass


# ── Rendering ──────────────────────────────────────────────────────────────────

def short(node_id):
    parts = node_id.split(".")
    return ".".join(parts[1:]) if parts[0] == "root" else node_id


CLUSTER_FILLS  = ["#e8f0fe", "#fff3e0", "#e8f5e9", "#fce4ec"]
CLUSTER_COLORS = ["#3a7ebf", "#e65100", "#2e7d32", "#880e4f"]


def add_cluster(parent, cluster, depth=0):
    fill  = CLUSTER_FILLS[depth  % len(CLUSTER_FILLS)]
    color = CLUSTER_COLORS[depth % len(CLUSTER_COLORS)]

    with parent.subgraph(name=f"cluster_{cluster['node_id']}") as c:
        c.attr(label=short(cluster['node_id']),
               style="rounded,filled", fillcolor=fill, color=color,
               penwidth="2", fontname="Helvetica Bold", fontsize="11",
               fontcolor=color)

        for leaf_id in cluster["leaves"]:
            c.node(leaf_id,
                   short(leaf_id),
                   shape="box", style="filled,rounded",
                   fillcolor="white", color=color,
                   fontname="Helvetica", fontsize="11")

        for sub in cluster["subclusters"]:
            add_cluster(c, sub, depth + 1)


def render(nodes, edges, cluster, output_path="my_graph"):
    compass = build_compass_maps(nodes, edges)

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

    add_cluster(dot, cluster)

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

    # Inject metadata into SVG for the viewer
    # ports: {node_id: {in: [...], out: [...]}} inferred from edges
    ports_meta = {}
    for node_id in nodes:
        if node_id in ('SOURCE', 'SINK'):
            continue
        in_p  = list(dict.fromkeys(dp for _, _, did, dp in edges if did == node_id))
        out_p = list(dict.fromkeys(sp for sid, sp, _, _ in edges if sid == node_id))
        ports_meta[node_id] = {'in': in_p, 'out': out_p}

    svg_path = f"{output_path}.svg"
    with open(svg_path) as f:
        svg_src = f.read()
    meta = json.dumps({"nodes": nodes, "ports": ports_meta}, separators=(",", ":"))
    script_tag = f'\n<script type="application/json" id="hdag-data">{meta}</script>'
    svg_src = svg_src.replace("</svg>", script_tag + "\n</svg>")
    with open(svg_path, "w") as f:
        f.write(svg_src)
    print(f"Embedded metadata → {svg_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, pathlib

    parser = argparse.ArgumentParser(description="Render an HDAG JSON file to SVG.")
    parser.add_argument("hdag_file", nargs="?", default="hdag.json",
                        help="Path to the HDAG JSON file (default: hdag.json)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output path without extension (default: stem of input file)")
    args = parser.parse_args()

    input_path  = pathlib.Path(args.hdag_file)
    output_path = args.output or input_path.stem

    with open(input_path) as f:
        hdag = json.load(f)

    nodes, edges, cluster = build_global_dag(hdag)
    render(nodes, edges, cluster, output_path)
