from collections import Counter

from bom2kit.kitting_partition import reunite_accessory_sets


def test_reunites_split_accessory_copies_without_moving_unrelated_parts():
    def part(iid, units):
        return {'id': iid, 'quantity': len(units), 'packing_unit_ids': units, 'mesh': {'sha256': iid}}
    groups = [[part('face', ['face#1']), part('arm', ['arm#1'])],
              [part('face', ['face#2']), part('core', ['core#1']), part('arm', ['arm#2'])]]
    cards = {iid: {'assembly': {'value': 'fiducial_object' if iid != 'arm' else 'arm_structure'},
                   'family': {'value': 'printed'}} for iid in ('face', 'core', 'arm')}
    repaired = reunite_accessory_sets(groups, cards, lambda g: sum(i['quantity'] for i in g)**2)
    locations = {uid: n for n, group in enumerate(repaired) for i in group for uid in i['packing_unit_ids']}
    assert len({locations[u] for u in ('face#1', 'face#2', 'core#1')}) == 1
    assert locations['arm#1'] != locations['arm#2']
    assert Counter(i['id'] for g in repaired for i in g for _ in i['packing_unit_ids']) == {'face': 2, 'core': 1, 'arm': 2}
    assert groups[0][0]['packing_unit_ids'] == ['face#1']  # Input remains unchanged.
