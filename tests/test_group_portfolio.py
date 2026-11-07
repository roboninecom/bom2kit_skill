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


def test_integer_selection_beats_locally_best_overlapping_group():
    import pytest
    pytest.importorskip("scipy")
    from bom2kit.group_portfolio import optimized_group_pool
    library={"items":[{"id":iid,"quantity":1} for iid in "abcd"]}
    alternatives=[{"members":list(members),"layout":{"variant":members},
                   "separate_box_volume_mm3":20,"group_box_volume_mm3":20-saving}
                  for members,saving in (("ab",10),("ac",6),("bd",6))]
    pool=optimized_group_pool(library,alternatives)
    assert {"".join(a["members"]) for a in pool}=={"ac","bd"}
    assert all(a["selected_copies"]==1 for a in pool)
    configurations=group_configurations(library,alternatives,2,optimize=True)
    assert sum(a["separate_box_volume_mm3"]-a["group_box_volume_mm3"] for a in configurations[0])==12
    assert [a["members"] for a in configurations[1]]==[["a","b"]]


def test_integer_selection_retains_partial_available_copies():
    import pytest
    pytest.importorskip("scipy")
    from bom2kit.group_portfolio import optimized_group_pool
    library={"items":[{"id":"a","quantity":3},{"id":"b","quantity":1}]}
    alternatives=[{"members":list(m),"layout":{"variant":m},"separate_box_volume_mm3":20,"group_box_volume_mm3":20-s}
                  for m,s in (("aa",9),("ab",8))]
    pool=optimized_group_pool(library,alternatives)
    assert {"".join(a["members"]):a["selected_copies"] for a in pool}=={"aa":1,"ab":1}
