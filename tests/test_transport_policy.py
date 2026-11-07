import pytest
from scripts.prepare_transport_policy import classify


def test_combining_protected_electronics_keeps_bare_mechanics_separate():
    library={"items":[{"id":"frame","name":"Printed frame"},
                      {"id":"metal","name":"Metal clamp"},
                      {"id":"servo","name":"STS3215","dimension_basis":"Estimated individual factory carton"},
                      {"id":"supply","name":"Power adapter","dimension_basis":"Protected envelope"}]}
    families,_=classify(library,{"frame"},combine_printed=True,combine_electronics=True)
    assert families=={"frame":"printed-parts","metal":"mechanics-fasteners",
                      "servo":"electronics-cables","supply":"electronics-cables"}


def test_unprotected_servo_cannot_silently_join_protected_electronics():
    library={"items":[{"id":"servo","name":"STS3215","dimension_basis":"Bare servo dimensions"}]}
    with pytest.raises(ValueError,match="protective packing needs evidence"):
        classify(library,set(),combine_electronics=True)
