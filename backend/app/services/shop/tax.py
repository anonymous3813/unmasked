"""Sales tax totals from a shopper's ZIP and published state averages."""

import json
from decimal import Decimal, ROUND_HALF_UP
from urllib.request import urlopen

# Population-weighted combined state and average local rates, January 1, 2025.
# Source: Tax Foundation, "State and Local Sales Tax Rates, 2025".
# City and county rates can differ from the state average.
_COMBINED_RATES = {
    "AL": Decimal("0.09427"),
    "AK": Decimal("0.01821"),
    "AZ": Decimal("0.08414"),
    "AR": Decimal("0.09460"),
    "CA": Decimal("0.08802"),
    "CO": Decimal("0.07857"),
    "CT": Decimal("0.06350"),
    "DE": Decimal("0"),
    "FL": Decimal("0.06948"),
    "GA": Decimal("0.07418"),
    "HI": Decimal("0.04500"),
    "ID": Decimal("0.06027"),
    "IL": Decimal("0.08890"),
    "IN": Decimal("0.07000"),
    "IA": Decimal("0.06942"),
    "KS": Decimal("0.08773"),
    "KY": Decimal("0.06000"),
    "LA": Decimal("0.10116"),
    "ME": Decimal("0.05500"),
    "MD": Decimal("0.06000"),
    "MA": Decimal("0.06250"),
    "MI": Decimal("0.06000"),
    "MN": Decimal("0.08125"),
    "MS": Decimal("0.07062"),
    "MO": Decimal("0.08410"),
    "MT": Decimal("0"),
    "NE": Decimal("0.06972"),
    "NV": Decimal("0.08236"),
    "NH": Decimal("0"),
    "NJ": Decimal("0.06601"),
    "NM": Decimal("0.07627"),
    "NY": Decimal("0.08532"),
    "NC": Decimal("0.06996"),
    "ND": Decimal("0.07050"),
    "OH": Decimal("0.07233"),
    "OK": Decimal("0.09005"),
    "OR": Decimal("0"),
    "PA": Decimal("0.06341"),
    "RI": Decimal("0.07000"),
    "SC": Decimal("0.07499"),
    "SD": Decimal("0.06114"),
    "TN": Decimal("0.09556"),
    "TX": Decimal("0.08201"),
    "UT": Decimal("0.07319"),
    "VT": Decimal("0.06366"),
    "VA": Decimal("0.05771"),
    "WA": Decimal("0.09429"),
    "WV": Decimal("0.06569"),
    "WI": Decimal("0.05702"),
    "WY": Decimal("0.05441"),
    "DC": Decimal("0.06000"),
}
_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "the District of Columbia",
}


def tax_note(amount: str, postal_code: str, fetch=None) -> dict | None:
    """Return a price mark for one ZIP, or nothing if the place is unknown."""
    place = _place(postal_code, fetch)
    if place is None:
        return None
    city, state = place
    rate = _COMBINED_RATES.get(state)
    if rate is None:
        return None
    listed = Decimal(amount).quantize(Decimal("0.01"))
    tax = (listed * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = listed + tax
    percent = (rate * Decimal("100")).quantize(Decimal("0.01"))
    state_name = _NAMES.get(state, state)
    if rate == 0:
        return {
            "kind": "price",
            "title": "Price with tax",
            "symbol": "0%",
            "label": f"${listed:.2f} · no sales tax",
            "message": f"{state_name} does not charge a general sales tax, so ${listed:.2f} is the price in {city}.",
            "listedPrice": f"{listed:.2f}",
            "priceWithTax": f"{listed:.2f}",
        }
    return {
        "kind": "price",
        "title": "Price with tax",
        "symbol": "+",
        "label": f"${total:.2f} in {city}",
        "message": (
            f"{state_name}'s average combined sales tax is {percent}%, "
            f"about ${tax:.2f} on ${listed:.2f}. "
            f"The city or county rate in {city} can differ from that average."
        ),
        "listedPrice": f"{listed:.2f}",
        "priceWithTax": f"{total:.2f}",
    }


def _place(postal_code: str, fetch) -> tuple[str, str] | None:
    code = "".join(character for character in postal_code if character.isdigit())[:5]
    if len(code) != 5:
        return None
    fetch = fetch or _fetch_zip
    try:
        payload = fetch(code)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    places = payload.get("places") or []
    if not places:
        return None
    city = str(places[0].get("place name") or "").strip()
    state = str(places[0].get("state abbreviation") or "").strip().upper()
    if not city or state not in _COMBINED_RATES:
        return None
    return city, state


def _fetch_zip(postal_code: str) -> dict:
    with urlopen(f"https://api.zippopotam.us/us/{postal_code}", timeout=8) as response:
        return json.load(response)
