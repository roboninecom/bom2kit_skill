"""Explicit packing-state evidence; unknown envelopes never become real cartons."""
from collections import Counter
from copy import deepcopy


def declared_state(item):
    """Classify existing source declarations without inventing measurements."""
    if 'selected_packing_state' in item:
        return deepcopy(item['selected_packing_state'])
    text = item.get("packing_state", "")
    if "factory carton" in text.lower():
        kind = "factory_carton"
    elif item.get("packet_grid"):
        kind = "protective_packet"
    elif "envelope" in text.lower():
        kind = "declared_envelope"
    else:
        kind = "source_part"
    return {
        "id": "source", "kind": kind,
        "dimension_evidence": item.get("dimension_basis", "Original source CAD"),
        "measurement_status": "declared_estimate" if kind != "source_part" else "source_cad",
        "mesh": deepcopy(item["mesh"]),
        "contents_per_unit": deepcopy(item.get("contents", {item["id"]: 1})),
        "protection": "Source packing declaration retained" if text else "Protection specified by carton policy",
        "eligible_for_primary_comparison": True,
        "eligibility_basis": "Unchanged accepted source, not a claim of measured dimensions",
    }


def audit_states(library):
    items = []
    counts = Counter()
    for item in library["items"]:
        state = declared_state(item)
        counts[state["kind"]] += item["quantity"]
        items.append({"item_id": item["id"], "quantity": item["quantity"],
                      "selected_state": state['id'], "states": [state]})
    return {"items": items, "packing_unit_counts": dict(counts),
            "scope": "Evidence classification; no alternative geometry is inferred"}


def select_state(item, state, *, research=False):
    """Require complete component coverage and evidence for a substituted state."""
    required = {"id", "kind", "mesh", "contents_per_unit", "dimension_evidence",
                "measurement_status", "protection"}
    if not required <= state.keys():
        raise ValueError("Incomplete packing state")
    if state["kind"] not in {"factory_carton", "protective_packet", "declared_envelope", "source_part"}:
        raise ValueError("Unknown packing state")
    if state["contents_per_unit"] != item.get("contents", {item["id"]: 1}):
        raise ValueError("Packing state changes component quantities")
    if not state["dimension_evidence"] or not state["protection"]:
        raise ValueError("Packing state needs dimensions and protection evidence")
    original=declared_state(item)
    if state['id']=='source' and any(state[k]!=original[k] for k in ('kind','mesh','contents_per_unit','protection')):
        raise ValueError('Source state cannot relabel or replace the accepted source')
    eligible=state['id']=='source' or state['measurement_status'] in {'measured','supplier_verified'}
    if not eligible and not research:
        raise ValueError("Unmeasured alternative is research-only")
    selected=deepcopy(state)
    selected['eligible_for_primary_comparison']=eligible
    selected['eligibility_basis']=('Unchanged accepted source' if state['id']=='source' else
                                   'Declared measurement/supplier evidence; protection equivalence still requires review' if eligible else
                                   'Research-only alternative; dimensions/protection not verified')
    return {**deepcopy(item), "mesh": deepcopy(state["mesh"]),"selected_packing_state":selected}
