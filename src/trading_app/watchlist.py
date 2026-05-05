from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class HalalLargeCapCandidate:
    symbol: str
    name: str
    sector: str
    industry: str
    fair_value: float
    reference_price: float
    market_cap_category: str
    halal_notes: str
    valuation_notes: str
    country: str
    quality_score: float = 0.8


# Research-only candidate universe: large-cap, developed-market names that are
# broadly consistent with an MSCI World-style universe and pass a qualitative
# Shariah-oriented sector screen. This is not a fatwa, investment advice, or a
# formal financial-ratio compliance certification; the dashboard displays this
# screening status explicitly.
HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES: tuple[HalalLargeCapCandidate, ...] = (
    HalalLargeCapCandidate("MSFT", "Microsoft", "Technology", "Software & Cloud", 560.0, 485.0, "largecap", "Software/cloud infrastructure; no bank, alcohol, gambling, pork or conventional insurance core business.", "Large-cap quality compounder; reference fair-value buffer used for ranking.", "United States", 0.95),
    HalalLargeCapCandidate("NVDA", "NVIDIA", "Technology", "Semiconductors & AI Infrastructure", 190.0, 145.0, "largecap", "Semiconductor/AI hardware platform; qualitative halal sector screen passed.", "AI semiconductor leader with strong quality score and valuation buffer.", "United States", 0.94),
    HalalLargeCapCandidate("AAPL", "Apple", "Technology", "Consumer Electronics", 245.0, 210.0, "largecap", "Consumer electronics and services; qualitative sector screen passed, financial ratios still require periodic review.", "Global hardware/services franchise with moderate research discount.", "United States", 0.91),
    HalalLargeCapCandidate("ASML", "ASML Holding", "Technology", "Semiconductor Equipment", 980.0, 760.0, "largecap", "Semiconductor equipment; qualitative halal sector screen passed.", "Critical chip-equipment supplier with long-term moat and reference discount.", "Netherlands", 0.92),
    HalalLargeCapCandidate("AVGO", "Broadcom", "Technology", "Semiconductors & Infrastructure Software", 310.0, 255.0, "largecap", "Semiconductors/infrastructure software; qualitative halal sector screen passed.", "High-quality large-cap chip/software candidate below research fair value.", "United States", 0.9),
    HalalLargeCapCandidate("ORCL", "Oracle", "Technology", "Enterprise Software & Cloud", 250.0, 205.0, "largecap", "Enterprise software/cloud; no prohibited core activity identified.", "Cloud/software large-cap with valuation buffer.", "United States", 0.86),
    HalalLargeCapCandidate("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", 220.0, 165.0, "largecap", "Semiconductors; qualitative halal sector screen passed.", "Large-cap semiconductor candidate with AI/data-center optionality.", "United States", 0.86),
    HalalLargeCapCandidate("ADBE", "Adobe", "Technology", "Creative & Document Software", 560.0, 430.0, "largecap", "Software; qualitative halal sector screen passed.", "High-margin software candidate with reference fair-value discount.", "United States", 0.85),
    HalalLargeCapCandidate("CRM", "Salesforce", "Technology", "Enterprise Software", 360.0, 285.0, "largecap", "Enterprise software; qualitative halal sector screen passed.", "Large-cap software candidate with margin-of-safety ranking input.", "United States", 0.84),
    HalalLargeCapCandidate("QCOM", "Qualcomm", "Technology", "Semiconductors & Wireless IP", 220.0, 170.0, "largecap", "Semiconductors/wireless IP; qualitative halal sector screen passed.", "Chip/IP candidate with diversified device exposure and valuation buffer.", "United States", 0.83),
    HalalLargeCapCandidate("TXN", "Texas Instruments", "Technology", "Analog Semiconductors", 240.0, 190.0, "largecap", "Analog semiconductors; qualitative halal sector screen passed.", "Defensive semiconductor candidate below research fair value.", "United States", 0.84),
    HalalLargeCapCandidate("AMAT", "Applied Materials", "Technology", "Semiconductor Equipment", 245.0, 190.0, "largecap", "Semiconductor equipment; qualitative halal sector screen passed.", "Chip-equipment large-cap candidate with valuation buffer.", "United States", 0.83),
    HalalLargeCapCandidate("LLY", "Eli Lilly", "Healthcare", "Pharmaceuticals", 980.0, 820.0, "largecap", "Pharmaceutical medicines; qualitative halal sector screen passed, product-level review still required.", "Large-cap healthcare quality candidate with strong growth profile.", "United States", 0.91),
    HalalLargeCapCandidate("NVO", "Novo Nordisk", "Healthcare", "Pharmaceuticals", 120.0, 92.0, "largecap", "Diabetes/obesity medicines; qualitative halal sector screen passed, product-level review still required.", "Global healthcare leader with reference valuation buffer.", "Denmark", 0.9),
    HalalLargeCapCandidate("ABT", "Abbott Laboratories", "Healthcare", "Medical Devices & Diagnostics", 145.0, 118.0, "largecap", "Medical devices/diagnostics/nutrition; qualitative halal sector screen passed.", "Defensive healthcare candidate below research fair value.", "United States", 0.86),
    HalalLargeCapCandidate("TMO", "Thermo Fisher Scientific", "Healthcare", "Life Science Tools", 690.0, 545.0, "largecap", "Life-science tools; qualitative halal sector screen passed.", "Global life-science tools candidate with valuation buffer.", "United States", 0.85),
    HalalLargeCapCandidate("ISRG", "Intuitive Surgical", "Healthcare", "Medical Devices", 620.0, 500.0, "largecap", "Medical robotics/devices; qualitative halal sector screen passed.", "High-quality med-tech candidate below research fair value.", "United States", 0.88),
    HalalLargeCapCandidate("LIN", "Linde", "Materials", "Industrial Gases", 540.0, 455.0, "largecap", "Industrial gases/materials; no prohibited core activity identified.", "Defensive materials large-cap with quality and valuation buffer.", "United Kingdom/Ireland", 0.87),
    HalalLargeCapCandidate("CAT", "Caterpillar", "Industrials", "Construction & Mining Equipment", 460.0, 380.0, "largecap", "Industrial equipment; qualitative halal sector screen passed.", "Global industrial machinery candidate with cyclical valuation buffer.", "United States", 0.82),
    HalalLargeCapCandidate("TM", "Toyota Motor", "Consumer", "Automobiles", 230.0, 185.0, "largecap", "Automotive manufacturing; qualitative halal sector screen passed.", "Developed-market consumer/auto large-cap candidate with value buffer.", "Japan", 0.81),
)

HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS: tuple[str, ...] = tuple(candidate.symbol for candidate in HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES)
# Backwards-compatible aliases for existing imports/tests while the app wording moves
# from the old mid-cap universe to the new MSCI World-style large-cap universe.
HALAL_MIDCAP_CANDIDATES = HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES
HALAL_MIDCAP_SYMBOLS = HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS


def _bar_lookup(bars: Iterable[Any]) -> dict[str, Any]:
    return {str(bar.symbol).upper(): bar for bar in bars}


def build_dynamic_halal_watchlist(
    client: Any,
    *,
    limit: int = 20,
    min_margin_of_safety: float = 0.0,
) -> dict[str, Any]:
    """Build a dynamic ranked watchlist from live/latest prices and halal large-cap candidates."""
    symbols = [candidate.symbol for candidate in HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES]
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
    for candidate in HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES:
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
        sector_bonus = 1.5 if candidate.sector in {"Healthcare", "Industrials", "Materials", "Consumer"} else 0.0
        score = round((margin * 100.0 * 0.72) + (candidate.quality_score * 20.0) + sector_bonus - (max(reference_change, 0.0) * 8.0), 4)
        rows.append(
            {
                "symbol": candidate.symbol,
                "name": candidate.name,
                "sector": candidate.sector,
                "industry": candidate.industry,
                "country": candidate.country,
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
            "universe": "20 qualitatively screened halal MSCI World large-cap candidates",
            "index_reference": "MSCI World developed-market large caps",
            "dynamic_fields": ["latest_price", "margin_of_safety", "score", "rank"],
            "selection_rule": "Only qualitatively halal-screened developed-market large-cap candidates with positive margin of safety are eligible; ranked by live discount, quality score, and sector-diversification bonus.",
            "disclaimer": "Research watchlist only; not investment advice and not a formal halal fatwa. MSCI World membership and Shariah financial-ratio compliance should be reviewed with authoritative data before real trading.",
        },
        "count": len(selected),
        "universe_count": len(HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS),
        "universe_symbols": list(HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS),
        "eligible_symbols": [row["symbol"] for row in selected],
        "symbols": [row["symbol"] for row in selected],
        "candidates": selected,
    }
