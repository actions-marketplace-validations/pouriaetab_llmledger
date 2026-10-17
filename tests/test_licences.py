import json

from llmledger import licences

MIT_TEXT = ('Portions ... resides under the "enterprise/" directory of this repository ...\n'
            "MIT License\n\nPermission is hereby granted, free of charge, to any person")


def fake(arena="cc-by-4.0", litellm=MIT_TEXT, pytest="MIT", down=()):
    def get(url):
        if any(part in url for part in down):
            raise OSError("down")
        if "litellm" in url:
            return litellm
        if "huggingface" in url:
            return json.dumps({"cardData": {"license": arena}})
        return json.dumps({"info": {"license_expression": pytest}})
    return get


def pins():
    return [("pytest", "9.1.1")]


def test_req_s26_open_licences():
    assert licences.is_open("MIT") and licences.is_open("cc-by-4.0")
    assert licences.is_open("Apache-2.0 OR BSD-2-Clause")
    assert not licences.is_open("cc-by-nc-4.0")
    assert not licences.is_open("other") and not licences.is_open("")
    assert not licences.is_open("MIT AND cc-by-nc-4.0")


def test_req_s26_litellm_file_must_stay_in_the_mit_part():
    assert licences.litellm_licence(MIT_TEXT) == "mit"
    assert licences.litellm_licence(MIT_TEXT, "enterprise/prices.json") == "restricted folder"
    assert licences.litellm_licence("Business Source License 1.1") == "not MIT any more"


def test_req_s26_all_open_means_everything_is_used():
    report, allowed = licences.check(fake(), pins, plugin=lambda: [("fastmcp", "4.1.0")])
    assert [r["status"] for r in report] == ["open", "open", "open", "open", "open"]
    assert allowed == {"data": True, "ratings": True}
    assert licences.problems(report) == []


def test_req_s26_a_closed_ratings_licence_drops_the_ratings_and_is_reported():
    report, allowed = licences.check(fake(arena="cc-by-nc-4.0"), pins)
    assert allowed == {"data": True, "ratings": False}
    assert "Arena leaderboard" in licences.problems(report)[0]


def test_req_s26_a_closed_data_licence_stops_publishing():
    report, allowed = licences.check(fake(litellm="Business Source License 1.1"), pins)
    assert allowed["data"] is False
    assert "Nothing was published" in licences.problems(report)[0]


def test_req_s26_unreachable_ratings_are_left_out_not_failed():
    report, allowed = licences.check(fake(down=("huggingface",)), pins)
    assert allowed == {"data": True, "ratings": False}
    assert report[1]["status"] == "unchecked"


def test_req_s26_the_plugin_packages_are_checked_and_a_closed_one_is_reported():
    def get(url):
        if "fastmcp" in url:
            return json.dumps({"info": {"license_expression": "LicenseRef-Proprietary"}})
        return fake()(url)
    report, allowed = licences.check(get, pins, plugin=lambda: [("fastmcp", "4.1.0")])
    row = next(r for r in report if r["source"] == "fastmcp 4.1.0")
    assert row["role"] == "plug-in" and row["status"] == "not open"
    assert allowed == {"data": True, "ratings": True}            # the page is not affected
    assert any("plug-in (mcp/)" in line for line in licences.problems(report))


def test_req_s26_plugin_pins_are_read_from_its_pyproject(tmp_path):
    file = tmp_path / "pyproject.toml"
    file.write_text('[build-system]\nrequires = ["hatchling==1.32.4"]\n[project]\ndependencies = ["fastmcp==4.1.0"]\n')
    assert licences._plugin_requirements(file) == [("hatchling", "1.32.4"), ("fastmcp", "4.1.0")]
    assert licences._plugin_requirements(tmp_path / "missing.toml") == []
