from bom2kit.group_portfolio import group_configurations


def test_neighbors_replace_conflicting_groups_and_skip_equivalent_greedy_pools():
    library = {"items":[{"id":iid,"quantity":2} for iid in "abc"]}
    alternatives = [{"members":list(members),"layout":{"variant":members},
                     "separate_box_volume_mm3":10,"group_box_volume_mm3":volume}
                    for members,volume in (("aa",4),("ab",5),("bb",6),("cc",7))]
    configurations = group_configurations(library,alternatives,4)
    names = [["".join(a["members"]) for a in configuration] for configuration in configurations]
    assert names == [["aa","bb","cc"],["ab","cc"],["aa","cc"],["aa","bb"]]
    assert group_configurations(library,[],4) == []
