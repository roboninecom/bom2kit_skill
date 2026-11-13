import pytest
import trimesh

from bom2kit.motif_evidence import used_motifs


def test_evidence_uses_actual_poses_and_only_selected_motif_members():
    first = trimesh.creation.box([20, 20, 10]); second = first.copy(); second.apply_translation([0, 0, 12.2])
    result = {'logistics': {'policy': {'item_padding_mm': 1., 'carton': {'gap_mm': .2}},
               'modules': [{'id': 'box', 'unit_ids': ['a', 'b'],
                            'source_motifs': [{'recipe_id': 'actual', 'unit_ids': ['a', 'b']}]}]}}
    evidence = used_motifs(result, {'a': first, 'b': second})
    assert len(evidence) == 1
    assert evidence[0]['dimensions_mm'] == pytest.approx([22, 22, 24.2])
    assert evidence[0]['recipe_id'] == 'actual'
    result['logistics']['modules'][0]['source_motifs'] = []
    assert used_motifs(result, {'a': first, 'b': second}) == []


def test_evidence_rejects_motif_claim_with_foreign_source_unit():
    result = {'logistics': {'policy': {'item_padding_mm': 1., 'carton': {'gap_mm': .2}},
               'modules': [{'id': 'box', 'unit_ids': ['a'],
                            'source_motifs': [{'unit_ids': ['a', 'missing']}]}]}}
    with pytest.raises(ValueError, match='not contained'):
        used_motifs(result, {})
