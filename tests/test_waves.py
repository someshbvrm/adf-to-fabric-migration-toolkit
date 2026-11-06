from adf2fabric.waves import pipeline_dependencies, plan_waves


def test_children_always_land_before_parents(factory):
    deps = pipeline_dependencies(factory)
    waves, cycles, missing = plan_waves(deps)
    assert cycles == [] and missing == []
    wave_of = {p: i for i, w in enumerate(waves) for p in w}
    for parent, children in deps.items():
        for child in children:
            assert wave_of[child] < wave_of[parent]
    assert waves[-1] == ["pl_master_daily"]
    assert len(waves) == 3


def test_cycles_and_missing_references_are_reported():
    deps = {"a": {"b"}, "b": {"a"}, "c": {"ghost"}, "d": set()}
    waves, cycles, missing = plan_waves(deps)
    assert waves == [["c", "d"]]
    assert cycles == ["a", "b"]
    assert missing == [("c", "ghost")]
