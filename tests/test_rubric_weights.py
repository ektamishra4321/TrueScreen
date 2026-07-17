from agents.rubric_agent import renormalize_weights


def test_weights_sum_to_100():
    crits = [{"weight": 30}, {"weight": 30}, {"weight": 30}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100


def test_uneven_weights_sum_to_100():
    crits = [{"weight": 7}, {"weight": 13}, {"weight": 1}, {"weight": 5}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100


def test_zero_and_missing_weights_survive():
    crits = [{"weight": 0}, {}, {"weight": 50}]
    out = renormalize_weights(crits)
    assert sum(c["weight"] for c in out) == 100
    assert all(c["weight"] >= 1 for c in out[:2])
