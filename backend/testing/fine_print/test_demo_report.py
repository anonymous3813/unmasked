"""The seeded demo report, recommendation answer, and policy monitor."""

from backend.app.demo.report import demo_answer, demo_report, reset_monitors, watch_policy


def test_demo_report_has_the_scripted_findings():
    report = demo_report()

    assert report["simulated"] is True
    assert len(report["concerns"]) == 2
    assert report["claim"]["verdict"] == "insufficient evidence"
    assert report["review"]["reports"] == 4
    assert report["environment"]["evidenceLevel"] == "unknown"
    assert len(report["alternatives"]) == 3
    assert "fixture" in report["label"].lower() or "Demo data" in report["label"]


def test_return_history_recommends_the_repairable_pair():
    answer = demo_answer("Which one would you recommend based on what I've returned before?")

    assert "North Loop Headphones" in answer
    assert "cushions" in answer
    assert "Lumen Repairable Headphones" in answer
    assert "problem-free" in answer
    assert "demo" in answer.lower()


def test_policy_monitor_is_opted_in_once():
    reset_monitors()

    first = watch_policy("Harbor Headphones")
    second = watch_policy("Harbor Headphones")

    assert first["status"] == "opted_in"
    assert first["id"] == second["id"]
    assert "Photon" in first["message"]
    assert first["simulated"] is True
