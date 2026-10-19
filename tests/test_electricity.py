import json

from llmledger import electricity

STATES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
          "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
          "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
          "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
          "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
          "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
          "West Virginia", "Wisconsin", "Wyoming"]


def row(name, *cents):
    cells = "".join(f'<td class="r t data" format:0.00>           {c}</td>\n' for c in cents)
    return f'<tr>\n<td class="l t data">{name}</td>\n{cells}</tr>\n'


def page(month="July 2026", states=STATES):
    """Table 5.6.A as EIA's Electric Power Monthly page lays it out (cents per kWh, ten columns)."""
    rows = [row("New England", "28.00", "27.89", "22.60", "22.48", "17.97", "18.10", "11.07", "12.99", "24.50", "24.47")]
    rows += [row(s, f"{10 + i * 0.5:.2f}", "9.99", "8.00", "8.00", "7.00", "7.00", "--", "--", "9.00", "9.00")
             for i, s in enumerate(states)]
    rows.append(row("U.S. Total", "18.31", "17.45", "14.53", "14.05", "9.77", "9.33", "14.97", "14.27", "14.99", "14.36"))
    return (f"<html><title>Electric Power Monthly</title><div class='title'>Table 5.6.A. Average Price of Electricity "
            f"to Ultimate Customers by End-Use Sector,\n by State, {month} and 2025 (Cents per Kilowatthour)</div>"
            "<table><tr><th>Census Division and State</th><th>Residential</th></tr>" + "".join(rows) + "</table></html>")


def test_req_s48_residential_prices_by_state_from_eia():
    out = electricity.parse(page())
    assert out["month"] == "2026-07" and out["label"] == "July 2026" and out["us"] == 0.1831
    assert len(out["states"]) == 51 and "New England" not in out["states"]           # regions left out
    assert out["states"]["Alabama"] == 0.10 and out["states"]["Texas"] == round((10 + 43 * 0.5) / 100, 4)
    assert out["credit"].endswith("Table 5.6.A (July 2026)") and out["source"] == electricity.TABLE


def test_req_s48_a_changed_table_gives_nothing_rather_than_wrong_prices():
    assert electricity.parse(page(month="Julember 2026")) is None
    assert electricity.parse(page(states=STATES[:10])) is None                 # far fewer states than 51
    assert electricity.parse("<html>Service unavailable</html>") is None
    assert electricity.fetch(get=lambda url: (_ for _ in ()).throw(OSError("down"))) is None


def test_req_s48_the_live_pages_prices_are_kept_when_eia_cannot_be_read():
    live = "window.LLMLEDGER = " + json.dumps({"models": [], "electricity": {"month": "2026-06", "us": 0.18}}) + ";\n"
    assert electricity.previous("https://example.org/data.js", get=lambda url: live) == {"month": "2026-06", "us": 0.18}
    assert electricity.previous("https://example.org/data.js", get=lambda url: "not a page") is None


def test_req_s48_the_reuse_page_must_still_say_public_domain():
    assert electricity.licence("<p>U.S. government publications are in the public domain and are\n"
                               "not subject to copyright protection.</p>") == "public-domain"
    assert electricity.licence("<p>All rights reserved.</p>") == "not public domain any more"
