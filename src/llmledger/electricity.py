"""What electricity costs at home, by US state, from the U.S. Energy Information Administration (EIA).

The plug-in's local_or_cloud tool prices the power a computer uses to run a model at home. The default is
the average residential price in EIA's Electric Power Monthly, Table 5.6.A, for the latest month it has, in
the whole country and in each state. EIA's data is a U.S. government work in the public domain; EIA asks for
a credit line with the publication date, which the data carries.

If EIA cannot be read, the prices on the live page are kept (previous), so a bad day never drops them.
"""
import html
import json
import re
import urllib.request

TABLE = "https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a"
REUSE = "https://www.eia.gov/about/copyrights_reuse.php"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
# rows of the table that are regions, not states
REGIONS = {"New England", "Middle Atlantic", "East North Central", "West North Central", "South Atlantic",
           "East South Central", "West South Central", "Mountain", "Pacific Contiguous", "Pacific Noncontiguous"}


def _get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def plain(page):
    """The words of an HTML page, tags and runs of spaces removed."""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))).strip()


def licence(page):
    """'public-domain' when EIA's reuse page still says its data is a U.S. government work in the public domain."""
    text = plain(page).lower()
    if "public domain" in text and "not subject to copyright protection" in text:
        return "public-domain"
    return "not public domain any more"


def parse(page):
    """{"month": "YYYY-MM", "label", "us", "states": {state: dollars per kWh}} from Table 5.6.A, residential, or None."""
    title = re.search(r"Table 5\.6\.A\..*?by State, (\w+) (\d{4}) and \d{4}", plain(page))
    if not title or title.group(1) not in MONTHS:
        return None
    month = f"{title.group(2)}-{MONTHS.index(title.group(1)) + 1:02d}"
    prices = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 3 or not cells[0] or cells[0] in REGIONS:
            continue
        try:
            cents = float(cells[1])
        except ValueError:
            continue                                   # "--" for no data, or a header row
        prices[cells[0]] = round(cents / 100, 4)
    us = prices.pop("U.S. Total", None)
    if us is None or len(prices) < 40:                 # 50 states and DC: anything far short is a changed table
        return None
    label = f"{title.group(1)} {title.group(2)}"
    return {"month": month, "label": label, "us": us, "states": dict(sorted(prices.items())),
            "unit": "dollars per kWh, residential, average", "source": TABLE,
            "credit": f"Source: U.S. Energy Information Administration, Electric Power Monthly, Table 5.6.A ({label})"}


def fetch(get=_get_text):
    try:
        return parse(get(TABLE))
    except Exception as error:
        print("EIA electricity prices could not be read:", error)
        return None


def previous(url, get=_get_text):
    """The prices on the page that is live now, if EIA cannot be read today."""
    try:
        text = get(url).replace("<\\/", "</")
        return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1]).get("electricity")
    except Exception as error:
        print("No earlier electricity prices either:", error)
        return None
