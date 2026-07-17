from eval.eval_harness import evaluate


def _result(source, scores):
    return {
        "source": source,
        "per_criterion": [
            {"criterion_id": cid, "score": s} for cid, s in scores.items()
        ],
    }


def test_perfect_agreement():
    results = [_result("a.pdf", {"c1": 4, "c2": 2})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["exact_agreement"] == 1.0
    assert rep["mae"] == 0.0
    assert rep["biggest_disagreements"] == []


def test_within_one_and_mae():
    results = [_result("a.pdf", {"c1": 3, "c2": 5})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["exact_agreement"] == 0.0
    assert rep["within_1_agreement"] == 0.5
    assert rep["mae"] == 2.0


def test_abstention_counted():
    results = [_result("a.pdf", {"c1": None, "c2": 2})]
    golden = [{"source": "a.pdf", "human_scores": {"c1": 4, "c2": 2}}]
    rep = evaluate(results, golden)
    assert rep["abstention_rate"] == 0.5
    assert rep["n_compared"] == 1
