from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class HalalMidcapCandidate:
    symbol: str
    name: str
    sector: str
    industry: str
    fair_value: float
    reference_price: float
    market_cap_category: str
    halal_notes: str
    valuation_notes: str
    quality_score: float = 0.7


# Research-only candidate universe: qualitatively halal-screened operating businesses,
# approximate US mid-cap range, and a positive reference margin of safety. This is not a
# fatwa or investment advice; the dashboard displays the screening status explicitly.
HALAL_MIDCAP_CANDIDATES: tuple[HalalMidcapCandidate, ...] = (
    HalalMidcapCandidate("ALGM", "Allegro MicroSystems", "Technology", "Semiconductors", 33.0, 23.0, "midcap", "Semiconductors; no bank, alcohol, gambling, pork or conventional insurance core business.", "Discount to conservative fair-value estimate from watchlist research.", 0.78),
    HalalMidcapCandidate("AMKR", "Amkor Technology", "Technology", "Semiconductor Packaging", 34.0, 23.0, "midcap", "Semiconductor packaging/manufacturing exposure; qualitative halal sector screen passed.", "Cyclical chip-packaging name trading below research fair value.", 0.72),
    HalalMidcapCandidate("ASO", "Academy Sports + Outdoors", "Consumer", "Sporting Goods Retail", 67.0, 48.0, "midcap", "Sporting goods retail; excludes prohibited finance/alcohol/gambling core business.", "Value retail profile with margin of safety versus research fair value.", 0.68),
    HalalMidcapCandidate("BCC", "Boise Cascade", "Industrials", "Building Products", 110.0, 82.0, "midcap", "Building products/manufacturing; qualitative halal sector screen passed.", "Cyclical building-products valuation appears discounted.", 0.66),
    HalalMidcapCandidate("BRC", "Brady", "Industrials", "Identification & Safety Products", 86.0, 65.0, "midcap", "Industrial safety/ID products; no prohibited core activity identified.", "Quality industrial candidate below research fair value.", 0.74),
    HalalMidcapCandidate("CALM", "Cal-Maine Foods", "Consumer Staples", "Food Products", 116.0, 95.0, "midcap", "Egg/food producer; qualitative halal sector screen passed.", "Cash-generative food producer with valuation buffer.", 0.7),
    HalalMidcapCandidate("CROX", "Crocs", "Consumer", "Footwear", 140.0, 100.0, "midcap", "Footwear/apparel; no prohibited core business identified.", "Brand cash-flow candidate with fair-value discount.", 0.73),
    HalalMidcapCandidate("DIOD", "Diodes", "Technology", "Semiconductors", 78.0, 55.0, "midcap", "Semiconductor components; qualitative halal sector screen passed.", "Semiconductor value candidate below normalized fair value.", 0.71),
    HalalMidcapCandidate("ENSG", "The Ensign Group", "Healthcare", "Healthcare Services", 145.0, 120.0, "midcap", "Healthcare services; qualitative sector screen passed, financial ratios still require periodic review.", "Defensive compounder candidate with moderate discount.", 0.76),
    HalalMidcapCandidate("FIZZ", "National Beverage", "Consumer Staples", "Non-Alcoholic Beverages", 60.0, 46.0, "midcap", "Non-alcoholic beverages; avoids alcohol core business.", "Asset-light beverage candidate below research fair value.", 0.69),
    HalalMidcapCandidate("GNTX", "Gentex", "Consumer/Auto", "Auto Components", 36.0, 27.0, "midcap", "Auto components/electronics; qualitative halal sector screen passed.", "Strong balance-sheet auto supplier candidate at discount.", 0.75),
    HalalMidcapCandidate("HAE", "Haemonetics", "Healthcare", "Medical Devices", 95.0, 75.0, "midcap", "Medical devices; qualitative halal sector screen passed.", "Med-tech candidate with valuation buffer.", 0.7),
    HalalMidcapCandidate("IRTC", "iRhythm Technologies", "Healthcare", "Medical Devices", 105.0, 80.0, "midcap", "Cardiac monitoring medical technology; qualitative halal sector screen passed.", "Growth med-tech candidate below fair-value estimate.", 0.67),
    HalalMidcapCandidate("LZB", "La-Z-Boy", "Consumer", "Furniture", 52.0, 38.0, "midcap", "Furniture manufacturing/retail; no prohibited core activity identified.", "Cyclical furniture value candidate with margin of safety.", 0.65),
    HalalMidcapCandidate("MOD", "Modine Manufacturing", "Industrials", "Thermal Management", 125.0, 95.0, "midcap", "Thermal-management industrial products; qualitative halal sector screen passed.", "Industrial growth/value candidate with discount.", 0.72),
    HalalMidcapCandidate("OLLI", "Ollie's Bargain Outlet", "Consumer", "Discount Retail", 128.0, 102.0, "midcap", "Discount retail; no prohibited core business identified.", "Retail compounder candidate below research fair value.", 0.71),
    HalalMidcapCandidate("SFM", "Sprouts Farmers Market", "Consumer Staples", "Grocery", 175.0, 145.0, "midcap", "Grocery/food retail; qualitative halal sector screen passed.", "Quality grocer candidate with moderate margin of safety.", 0.74),
    HalalMidcapCandidate("SKX", "Skechers", "Consumer", "Footwear", 85.0, 62.0, "midcap", "Footwear/apparel; no prohibited core activity identified.", "Global footwear candidate below fair-value estimate.", 0.73),
    HalalMidcapCandidate("TREX", "Trex", "Industrials", "Building Products", 85.0, 60.0, "midcap", "Composite decking/building products; qualitative halal sector screen passed.", "High-quality building-products candidate at discount.", 0.72),
    HalalMidcapCandidate("URBN", "Urban Outfitters", "Consumer", "Apparel Retail", 85.0, 65.0, "midcap", "Apparel/home retail; no prohibited core business identified.", "Retail value candidate below fair-value estimate.", 0.66),
)

HALAL_MIDCAP_SYMBOLS: tuple[str, ...] = tuple(candidate.symbol for candidate in HALAL_MIDCAP_CANDIDATES)


def _bar_lookup(bars: Iterable[Any]) -> dict[str, Any]:
    return {str(bar.symbol).upper(): bar for bar in bars}


def build_dynamic_halal_watchlist(
    client: Any,
    *,
    limit: int = 20,
    min_margin_of_safety: float = 0.0,
) -> dict[str, Any]:
    """Build a dynamic ranked watchlist from live/latest prices and halal midcap candidates."""
    symbols = [candidate.symbol for candidate in HALAL_MIDCAP_CANDIDATES]
    try:
        bars = client.latest_bars(symbols)
        source = "alpaca_latest_bars" if client.settings.alpaca_configured else "reference_fallback"
        error = None
    except Exception as exc:  # noqa: BLE001 - watchlist must remain usable if market data fails
        bars = []
        source = "reference_fallback"
        error = f"Latest price lookup failed: {exc}"

    by_symbol = _bar_lookup(bars)
    rows: list[dict[str, Any]] = []
    for candidate in HALAL_MIDCAP_CANDIDATES:
        bar = by_symbol.get(candidate.symbol)
        latest_price = float(getattr(bar, "close", 0.0) or 0.0) if bar else 0.0
        price_source = source if latest_price > 0 and getattr(bar, "volume", 1) != 0 else "reference_price"
        if latest_price <= 0 or getattr(bar, "volume", 1) == 0:
            latest_price = candidate.reference_price

        margin = (candidate.fair_value - latest_price) / candidate.fair_value if candidate.fair_value else 0.0
        undervalued = margin >= min_margin_of_safety
        # Dynamic ranking: live discount dominates, quality breaks ties, and mild price-vs-reference
        # change keeps the order responsive when Alpaca prices move.
        reference_change = (latest_price - candidate.reference_price) / candidate.reference_price if candidate.reference_price else 0.0
        score = round((margin * 100.0 * 0.75) + (candidate.quality_score * 20.0) - (max(reference_change, 0.0) * 8.0), 4)
        rows.append(
            {
                "symbol": candidate.symbol,
                "name": candidate.name,
                "sector": candidate.sector,
                "industry": candidate.industry,
                "market_cap_category": candidate.market_cap_category,
                "halal_screen": "candidate_only_qualitative_pass",
                "halal_notes": candidate.halal_notes,
                "latest_price": round(latest_price, 4),
                "fair_value": round(candidate.fair_value, 4),
                "margin_of_safety": round(margin, 4),
                "undervalued": undervalued,
                "valuation_notes": candidate.valuation_notes,
                "score": score,
                "price_source": price_source,
            }
        )

    eligible = [row for row in rows if row["undervalued"]]
    eligible.sort(key=lambda row: (float(row["score"]), float(row["margin_of_safety"])), reverse=True)
    selected = eligible[:limit]
    for rank, row in enumerate(selected, start=1):
        row["rank"] = rank

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "error": error,
        "methodology": {
            "universe": "20 qualitatively screened halal midcap candidates",
            "dynamic_fields": ["latest_price", "margin_of_safety", "score", "rank"],
            "selection_rule": "Only halal-screened midcap candidates with positive margin of safety are eligible; ranked by live discount plus quality score.",
            "disclaimer": "Research watchlist only; not investment advice and not a formal halal fatwa. Financial-ratio screening should be reviewed periodically.",
        },
        "count": len(selected),
        "symbols": [row["symbol"] for row in selected],
        "candidates": selected,
    }
