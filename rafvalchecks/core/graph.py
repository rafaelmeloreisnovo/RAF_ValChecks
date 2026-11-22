"""Recursive tree planner: typed slots, explicit compositional patches, DAG ordering.

Slots are fill/compose-only. An optional slot may stay TOKEN_VAZIO; a required
slot without an implementation is BLOCKED. No patch can replace a required gate.
"""
import copy
from .contract import demand, digest, keys, label, Violation

KINDS = frozenset({"group", "slot", "manifest", "source", "receipt", "file_sha256", "pair_relation", "rollback_reference", "temporal_audit"})


def build(spec):
    keys(spec, ["version", "root"], ["version", "root", "extensions"], "topology")
    demand(spec["version"] == 1, "TOPOLOGY_VERSION_UNSUPPORTED")
    root = copy.deepcopy(spec["root"])
    seen = {}
    slots = {}
    parents = {}

    def scan(node, parent=None, depth=0):
        demand(depth <= 32, "MAX_MODULE_DEPTH_EXCEEDED")
        keys(node, ["id", "kind"], ["id", "kind", "required", "depends_on", "scope", "config", "children", "accepts", "fallback", "reason", "rollback_ref"], "module")
        nid = label(node["id"])
        demand(len(seen) < 512, "MAX_MODULES_EXCEEDED", nid)
        demand(nid not in seen, "MODULE_ID_DUPLICATE", nid)
        demand(node["kind"] in KINDS, "MODULE_KIND_UNKNOWN", nid)
        demand(type(node.get("required", True)) is bool, "REQUIRED_FLAG_INVALID", nid)
        for field in ("depends_on", "scope"):
            values = node.get(field, [])
            demand(isinstance(values, list) and len(values) == len(set(str(v) for v in values)) and all(isinstance(v, str) and v for v in values), "MODULE_LIST_INVALID", nid + "." + field)
        demand(isinstance(node.get("config", {}), dict), "MODULE_CONFIG_INVALID", nid)
        children = node.get("children", [])
        demand(isinstance(children, list), "MODULE_CHILDREN_INVALID", nid)
        if node["kind"] == "slot":
            demand(not children, "SLOT_CHILDREN_NOT_ALLOWED", nid)
            accepts = node.get("accepts", [])
            demand(isinstance(accepts, list) and bool(accepts) and len(accepts) == len(set(accepts)) and
                   all(isinstance(x, str) and x in KINDS - {"slot"} for x in accepts), "SLOT_ACCEPTS_INVALID", nid)
            demand(node.get("fallback", "TOKEN_VAZIO") in ("TOKEN_VAZIO", "BLOCKED"), "SLOT_FALLBACK_INVALID", nid)
            slots[nid] = node
        else:
            demand("accepts" not in node and "fallback" not in node, "NON_SLOT_CONFIGURATION", nid)
        if node["kind"] == "group":
            demand(len(children) > 0, "GROUP_EMPTY", nid)
        else:
            demand(not children, "LEAF_HAS_CHILDREN", nid)
        if "rollback_ref" in node:
            demand(isinstance(node["rollback_ref"], str) and bool(node["rollback_ref"]), "ROLLBACK_REF_INVALID", nid)
        seen[nid] = node
        parents[nid] = parent
        for child in children:
            scan(child, nid, depth + 1)
        # Every non-slot module has a reserved typed vacancy. The port itself
        # never sprouts another port; this is finite even under recursion.
        if node["kind"] != "slot":
            demand(len(seen) < 512, "MAX_MODULES_EXCEEDED", nid)
            slot_id = nid + ".__void"
            demand(slot_id not in seen, "RESERVED_SLOT_ID_COLLISION", slot_id)
            virtual = {"id": slot_id, "kind": "slot", "required": False,
                       "accepts": sorted(KINDS - {"slot"}), "fallback": "TOKEN_VAZIO",
                       "reason": "Reserved per-module extension point; never an implicit PASS"}
            node["_extension_point"] = slot_id
            seen[slot_id] = virtual
            slots[slot_id] = virtual
            parents[slot_id] = nid

    scan(root)
    extensions = spec.get("extensions", [])
    demand(isinstance(extensions, list) and len(extensions) <= 128, "EXTENSIONS_INVALID")
    used = set()
    composed = set()
    # Patches only target slots, and inserted subtrees retain identities and provenance.
    for index, patch in enumerate(extensions):
        keys(patch, ["slot", "mode", "reason", "module"], ["slot", "mode", "reason", "module"], "extension")
        slot_id = patch["slot"]
        demand(slot_id in slots, "SLOT_UNKNOWN", str(slot_id))
        demand(patch["mode"] in ("fill", "compose"), "SLOT_OPERATION_FORBIDDEN", str(slot_id))
        demand(isinstance(patch["reason"], str) and len(patch["reason"]) >= 8, "SLOT_REASON_MISSING", str(slot_id))
        if patch["mode"] == "fill":
            demand(slot_id not in used and slot_id not in composed, "SLOT_ALREADY_FILLED", slot_id)
            used.add(slot_id)
        else:
            demand(slot_id not in used, "SLOT_COMPOSE_AFTER_FILL", slot_id)
            composed.add(slot_id)
        node = copy.deepcopy(patch["module"])
        demand(isinstance(node, dict) and node.get("kind") in slots[slot_id]["accepts"], "SLOT_TYPE_MISMATCH", slot_id)
        # `compose` allows independent modules; `fill` allows exactly one.
        holder = slots[slot_id]
        holder.setdefault("_filled", []).append({"module": node, "reason": patch["reason"], "mode": patch["mode"]})
        # Inserted subtrees can contain nested slots; safely scan recursively.
        scan(node, slot_id)
    # Slots introduced inside extension modules may be filled by later patches.
    for sid, slot in slots.items():
        if not slot.get("_filled"):
            slot["_filled"] = []

    # Independent mandatory safety gates cannot be replaced by a slot extension.
    demand(root["kind"] == "group" and root.get("required", True), "ROOT_GROUP_REQUIRED")
    ordinary = {nid: n for nid, n in seen.items() if n["kind"] != "slot"}
    authored = set()
    def enumerate_authored(node):
        authored.add(node["id"])
        for child in node.get("children", []):
            enumerate_authored(child)
    enumerate_authored(root)
    manifest_nodes = [nid for nid in authored if seen[nid]["kind"] == "manifest"]
    source_nodes = [nid for nid in authored if seen[nid]["kind"] == "source"]
    demand(len(manifest_nodes) == 1 and len(source_nodes) == 1, "MANDATORY_GATES_MISSING")
    demand(all(seen[nid].get("required", True) for nid in manifest_nodes + source_nodes), "MANDATORY_GATE_OPTIONAL")
    demand(manifest_nodes[0] in seen[source_nodes[0]].get("depends_on", []), "SOURCE_MUST_DEPEND_ON_MANIFEST")

    # Required references must resolve. Parent dependencies are implicit for
    # the aggregation result, but no descendant may depend on an ancestor/group.
    links = {}
    for nid, node in seen.items():
        deps = list(node.get("depends_on", []))
        if node["kind"] == "group":
            deps.extend(child["id"] for child in node["children"])
        if node["kind"] == "slot":
            deps.extend(item["module"]["id"] for item in node["_filled"])
            if node.get("id", "").endswith(".__void"):
                deps.append(parents[nid])
        for dep in deps:
            demand(dep in seen and dep != nid, "MODULE_DEPENDENCY_INVALID", nid)
        links[nid] = sorted(set(deps))

    order = []
    visiting, done = set(), set()
    def visit(nid):
        demand(nid not in visiting, "MODULE_CYCLE", nid)
        if nid in done:
            return
        visiting.add(nid)
        for dep in links[nid]:
            visit(dep)
        visiting.remove(nid)
        done.add(nid)
        order.append(nid)
    for nid in sorted(seen):
        visit(nid)

    for nid, node in seen.items():
        if node["kind"] in ("group", "slot"):
            continue
        # Cannot have a consumer requiring an ancestor aggregate result.
        ancestor = parents[nid]
        while ancestor is not None:
            demand(ancestor not in links[nid], "ANCESTOR_DEPENDENCY_INVALID", nid)
            ancestor = parents[ancestor]

    canonical_spec = copy.deepcopy(spec)
    return {"root": root, "nodes": seen, "parents": parents, "dependencies": links, "order": order,
            "graph_hash": digest(canonical_spec), "slot_count": len(slots), "extension_count": len(extensions)}
