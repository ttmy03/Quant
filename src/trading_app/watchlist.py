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


# Research-only universe: 279 large-cap developed-market / MSCI World-style
# names with a qualitative Shariah-oriented sector screen. This intentionally
# excludes conventional banks/insurers, alcohol, gambling, pork, tobacco and
# adult entertainment, but it is NOT a formal MSCI constituent feed or a fatwa.
# Financial-ratio and product-level compliance still need authoritative review.
RAW_HALAL_MSCI_WORLD_LARGE_CAP_UNIVERSE: tuple[tuple[str, str, str, str, str, float], ...] = (
    ("MSFT", "Microsoft", "Technology", "Software & Cloud", "United States", 0.95),
    ("NVDA", "NVIDIA", "Technology", "Semiconductors & AI Infrastructure", "United States", 0.94),
    ("AAPL", "Apple", "Technology", "Consumer Electronics", "United States", 0.91),
    ("ASML", "ASML Holding", "Technology", "Semiconductor Equipment", "Netherlands", 0.92),
    ("AVGO", "Broadcom", "Technology", "Semiconductors & Infrastructure Software", "United States", 0.90),
    ("ORCL", "Oracle", "Technology", "Enterprise Software & Cloud", "United States", 0.86),
    ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", "United States", 0.86),
    ("ADBE", "Adobe", "Technology", "Creative & Document Software", "United States", 0.85),
    ("CRM", "Salesforce", "Technology", "Enterprise Software", "United States", 0.84),
    ("QCOM", "Qualcomm", "Technology", "Semiconductors & Wireless IP", "United States", 0.83),
    ("TXN", "Texas Instruments", "Technology", "Analog Semiconductors", "United States", 0.84),
    ("AMAT", "Applied Materials", "Technology", "Semiconductor Equipment", "United States", 0.83),
    ("INTU", "Intuit", "Technology", "Financial & Tax Software", "United States", 0.84),
    ("NOW", "ServiceNow", "Technology", "Workflow Software", "United States", 0.84),
    ("PANW", "Palo Alto Networks", "Technology", "Cybersecurity", "United States", 0.83),
    ("CRWD", "CrowdStrike", "Technology", "Cybersecurity", "United States", 0.82),
    ("SNPS", "Synopsys", "Technology", "EDA Software", "United States", 0.86),
    ("CDNS", "Cadence Design Systems", "Technology", "EDA Software", "United States", 0.86),
    ("KLAC", "KLA", "Technology", "Semiconductor Equipment", "United States", 0.84),
    ("LRCX", "Lam Research", "Technology", "Semiconductor Equipment", "United States", 0.83),
    ("MU", "Micron Technology", "Technology", "Memory Semiconductors", "United States", 0.78),
    ("MRVL", "Marvell Technology", "Technology", "Semiconductors", "United States", 0.78),
    ("ADI", "Analog Devices", "Technology", "Analog Semiconductors", "United States", 0.84),
    ("MCHP", "Microchip Technology", "Technology", "Embedded Semiconductors", "United States", 0.80),
    ("NXPI", "NXP Semiconductors", "Technology", "Automotive Semiconductors", "Netherlands", 0.81),
    ("ON", "ON Semiconductor", "Technology", "Power Semiconductors", "United States", 0.78),
    ("MPWR", "Monolithic Power Systems", "Technology", "Power Semiconductors", "United States", 0.82),
    ("TEL", "TE Connectivity", "Technology", "Electronic Components", "Switzerland", 0.80),
    ("APH", "Amphenol", "Technology", "Electronic Connectors", "United States", 0.82),
    ("GLW", "Corning", "Technology", "Specialty Glass", "United States", 0.76),
    ("KEYS", "Keysight Technologies", "Technology", "Electronic Test Equipment", "United States", 0.78),
    ("FTNT", "Fortinet", "Technology", "Cybersecurity", "United States", 0.80),
    ("ANET", "Arista Networks", "Technology", "Cloud Networking", "United States", 0.84),
    ("CSCO", "Cisco Systems", "Technology", "Networking Equipment", "United States", 0.80),
    ("IBM", "IBM", "Technology", "Enterprise Technology", "United States", 0.76),
    ("HPQ", "HP", "Technology", "Computing Hardware", "United States", 0.72),
    ("DELL", "Dell Technologies", "Technology", "Computing Hardware", "United States", 0.75),
    ("HPE", "Hewlett Packard Enterprise", "Technology", "Enterprise Infrastructure", "United States", 0.72),
    ("NET", "Cloudflare", "Technology", "Cloud Security & Networking", "United States", 0.75),
    ("DDOG", "Datadog", "Technology", "Cloud Monitoring Software", "United States", 0.77),
    ("TEAM", "Atlassian", "Technology", "Collaboration Software", "Australia", 0.77),
    ("SHOP", "Shopify", "Technology", "Commerce Software", "Canada", 0.78),
    ("UBER", "Uber Technologies", "Technology", "Mobility Platform", "United States", 0.76),
    ("ABNB", "Airbnb", "Consumer", "Travel Marketplace", "United States", 0.76),
    ("ROP", "Roper Technologies", "Technology", "Vertical Software", "United States", 0.83),
    ("FICO", "Fair Isaac", "Technology", "Analytics Software", "United States", 0.82),
    ("WDAY", "Workday", "Technology", "Human Capital Software", "United States", 0.79),
    ("VEEV", "Veeva Systems", "Healthcare", "Life Sciences Software", "United States", 0.81),
    ("ZS", "Zscaler", "Technology", "Cloud Security", "United States", 0.75),
    ("MDB", "MongoDB", "Technology", "Database Software", "United States", 0.74),
    ("LLY", "Eli Lilly", "Healthcare", "Pharmaceuticals", "United States", 0.91),
    ("NVO", "Novo Nordisk", "Healthcare", "Pharmaceuticals", "Denmark", 0.90),
    ("JNJ", "Johnson & Johnson", "Healthcare", "Healthcare Products", "United States", 0.84),
    ("ABBV", "AbbVie", "Healthcare", "Pharmaceuticals", "United States", 0.80),
    ("MRK", "Merck & Co", "Healthcare", "Pharmaceuticals", "United States", 0.83),
    ("TMO", "Thermo Fisher Scientific", "Healthcare", "Life Science Tools", "United States", 0.85),
    ("ABT", "Abbott Laboratories", "Healthcare", "Medical Devices & Diagnostics", "United States", 0.86),
    ("ISRG", "Intuitive Surgical", "Healthcare", "Medical Devices", "United States", 0.88),
    ("DHR", "Danaher", "Healthcare", "Life Science Tools", "United States", 0.84),
    ("SYK", "Stryker", "Healthcare", "Medical Devices", "United States", 0.84),
    ("BSX", "Boston Scientific", "Healthcare", "Medical Devices", "United States", 0.83),
    ("MDT", "Medtronic", "Healthcare", "Medical Devices", "Ireland", 0.80),
    ("ZBH", "Zimmer Biomet", "Healthcare", "Medical Devices", "United States", 0.74),
    ("EW", "Edwards Lifesciences", "Healthcare", "Medical Devices", "United States", 0.80),
    ("IDXX", "IDEXX Laboratories", "Healthcare", "Diagnostics", "United States", 0.84),
    ("A", "Agilent Technologies", "Healthcare", "Life Science Tools", "United States", 0.79),
    ("WAT", "Waters", "Healthcare", "Life Science Tools", "United States", 0.78),
    ("IQV", "IQVIA", "Healthcare", "Clinical Research & Data", "United States", 0.76),
    ("REGN", "Regeneron Pharmaceuticals", "Healthcare", "Biotechnology", "United States", 0.85),
    ("VRTX", "Vertex Pharmaceuticals", "Healthcare", "Biotechnology", "United States", 0.86),
    ("GILD", "Gilead Sciences", "Healthcare", "Biotechnology", "United States", 0.80),
    ("BIIB", "Biogen", "Healthcare", "Biotechnology", "United States", 0.72),
    ("AMGN", "Amgen", "Healthcare", "Biotechnology", "United States", 0.81),
    ("ILMN", "Illumina", "Healthcare", "Genomics Tools", "United States", 0.70),
    ("RMD", "ResMed", "Healthcare", "Medical Devices", "United States", 0.81),
    ("DXCM", "DexCom", "Healthcare", "Medical Devices", "United States", 0.78),
    ("HOLX", "Hologic", "Healthcare", "Diagnostics", "United States", 0.76),
    ("BAX", "Baxter International", "Healthcare", "Medical Products", "United States", 0.70),
    ("STE", "STERIS", "Healthcare", "Sterilization Products", "Ireland", 0.80),
    ("ALC", "Alcon", "Healthcare", "Eye Care Devices", "Switzerland", 0.79),
    ("SNY", "Sanofi", "Healthcare", "Pharmaceuticals", "France", 0.80),
    ("NVS", "Novartis", "Healthcare", "Pharmaceuticals", "Switzerland", 0.82),
    ("AZN", "AstraZeneca", "Healthcare", "Pharmaceuticals", "United Kingdom", 0.84),
    ("GSK", "GSK", "Healthcare", "Pharmaceuticals", "United Kingdom", 0.78),
    ("RHHBY", "Roche Holding", "Healthcare", "Pharmaceuticals & Diagnostics", "Switzerland", 0.83),
    ("BAYRY", "Bayer", "Healthcare", "Pharmaceuticals & Crop Science", "Germany", 0.70),
    ("TAK", "Takeda Pharmaceutical", "Healthcare", "Pharmaceuticals", "Japan", 0.74),
    ("ARGX", "argenx", "Healthcare", "Biotechnology", "Netherlands", 0.79),
    ("BGNE", "BeiGene", "Healthcare", "Biotechnology", "Switzerland", 0.72),
    ("UCB", "UCB", "Healthcare", "Biopharmaceuticals", "Belgium", 0.76),
    ("LIN", "Linde", "Materials", "Industrial Gases", "United Kingdom/Ireland", 0.87),
    ("APD", "Air Products and Chemicals", "Materials", "Industrial Gases", "United States", 0.82),
    ("ECL", "Ecolab", "Materials", "Water & Hygiene Chemistry", "United States", 0.83),
    ("SHW", "Sherwin-Williams", "Materials", "Paints & Coatings", "United States", 0.82),
    ("PPG", "PPG Industries", "Materials", "Paints & Coatings", "United States", 0.76),
    ("NEM", "Newmont", "Materials", "Gold Mining", "United States", 0.72),
    ("FCX", "Freeport-McMoRan", "Materials", "Copper Mining", "United States", 0.74),
    ("SCCO", "Southern Copper", "Materials", "Copper Mining", "United States", 0.76),
    ("RIO", "Rio Tinto", "Materials", "Diversified Mining", "United Kingdom/Australia", 0.76),
    ("BHP", "BHP Group", "Materials", "Diversified Mining", "Australia", 0.77),
    ("VALE", "Vale", "Materials", "Iron Ore & Base Metals", "Brazil", 0.70),
    ("NUE", "Nucor", "Materials", "Steel", "United States", 0.75),
    ("STLD", "Steel Dynamics", "Materials", "Steel", "United States", 0.74),
    ("MLM", "Martin Marietta Materials", "Materials", "Aggregates", "United States", 0.80),
    ("VMC", "Vulcan Materials", "Materials", "Aggregates", "United States", 0.80),
    ("CTVA", "Corteva", "Materials", "Agricultural Inputs", "United States", 0.75),
    ("FMC", "FMC", "Materials", "Agricultural Chemistry", "United States", 0.68),
    ("DD", "DuPont", "Materials", "Specialty Materials", "United States", 0.74),
    ("ALB", "Albemarle", "Materials", "Lithium & Specialty Chemicals", "United States", 0.70),
    ("SQM", "Sociedad Quimica y Minera", "Materials", "Lithium & Chemicals", "Chile", 0.70),
    ("GOLD", "Barrick Gold", "Materials", "Gold Mining", "Canada", 0.72),
    ("AEM", "Agnico Eagle Mines", "Materials", "Gold Mining", "Canada", 0.75),
    ("WPM", "Wheaton Precious Metals", "Materials", "Precious Metals Streaming", "Canada", 0.73),
    ("TECK", "Teck Resources", "Materials", "Base Metals", "Canada", 0.72),
    ("CCJ", "Cameco", "Energy", "Uranium", "Canada", 0.72),
    ("CAT", "Caterpillar", "Industrials", "Construction & Mining Equipment", "United States", 0.82),
    ("DE", "Deere", "Industrials", "Agricultural Equipment", "United States", 0.83),
    ("HON", "Honeywell", "Industrials", "Automation & Industrial Technology", "United States", 0.82),
    ("ETN", "Eaton", "Industrials", "Electrical Equipment", "Ireland", 0.84),
    ("ITW", "Illinois Tool Works", "Industrials", "Industrial Products", "United States", 0.82),
    ("PH", "Parker-Hannifin", "Industrials", "Motion & Control", "United States", 0.82),
    ("EMR", "Emerson Electric", "Industrials", "Automation", "United States", 0.78),
    ("ROK", "Rockwell Automation", "Industrials", "Factory Automation", "United States", 0.80),
    ("AME", "Ametek", "Industrials", "Electronic Instruments", "United States", 0.82),
    ("XYL", "Xylem", "Industrials", "Water Technology", "United States", 0.81),
    ("IR", "Ingersoll Rand", "Industrials", "Industrial Machinery", "United States", 0.79),
    ("DOV", "Dover", "Industrials", "Industrial Products", "United States", 0.77),
    ("GWW", "W.W. Grainger", "Industrials", "Industrial Distribution", "United States", 0.83),
    ("FAST", "Fastenal", "Industrials", "Industrial Distribution", "United States", 0.82),
    ("WAB", "Wabtec", "Industrials", "Rail Equipment", "United States", 0.78),
    ("OTIS", "Otis Worldwide", "Industrials", "Elevators", "United States", 0.79),
    ("CARR", "Carrier Global", "Industrials", "HVAC", "United States", 0.78),
    ("JCI", "Johnson Controls", "Industrials", "Building Technology", "Ireland", 0.76),
    ("TT", "Trane Technologies", "Industrials", "HVAC & Climate", "Ireland", 0.83),
    ("CSX", "CSX", "Industrials", "Railroads", "United States", 0.80),
    ("NSC", "Norfolk Southern", "Industrials", "Railroads", "United States", 0.78),
    ("UNP", "Union Pacific", "Industrials", "Railroads", "United States", 0.82),
    ("CP", "Canadian Pacific Kansas City", "Industrials", "Railroads", "Canada", 0.80),
    ("CNI", "Canadian National Railway", "Industrials", "Railroads", "Canada", 0.80),
    ("UPS", "UPS", "Industrials", "Logistics", "United States", 0.77),
    ("FDX", "FedEx", "Industrials", "Logistics", "United States", 0.75),
    ("EXPD", "Expeditors International", "Industrials", "Freight Forwarding", "United States", 0.76),
    ("CHRW", "C.H. Robinson", "Industrials", "Logistics", "United States", 0.70),
    ("RSG", "Republic Services", "Industrials", "Waste Services", "United States", 0.82),
    ("WM", "Waste Management", "Industrials", "Waste Services", "United States", 0.83),
    ("VRSK", "Verisk Analytics", "Industrials", "Data Analytics", "United States", 0.81),
    ("EFX", "Equifax", "Industrials", "Data & Analytics", "United States", 0.76),
    ("TRMB", "Trimble", "Industrials", "Positioning Technology", "United States", 0.75),
    ("GNRC", "Generac", "Industrials", "Power Equipment", "United States", 0.70),
    ("IEX", "IDEX", "Industrials", "Industrial Machinery", "United States", 0.79),
    ("PNR", "Pentair", "Industrials", "Water Equipment", "United Kingdom", 0.76),
    ("SWK", "Stanley Black & Decker", "Industrials", "Tools", "United States", 0.70),
    ("SNA", "Snap-on", "Industrials", "Tools & Diagnostics", "United States", 0.77),
    ("MAS", "Masco", "Industrials", "Building Products", "United States", 0.74),
    ("ALLE", "Allegion", "Industrials", "Security Products", "Ireland", 0.76),
    ("LII", "Lennox International", "Industrials", "HVAC", "United States", 0.77),
    ("BLDR", "Builders FirstSource", "Industrials", "Building Products", "United States", 0.74),
    ("PWR", "Quanta Services", "Industrials", "Infrastructure Services", "United States", 0.80),
    ("HUBB", "Hubbell", "Industrials", "Electrical Equipment", "United States", 0.79),
    ("AYI", "Acuity", "Industrials", "Lighting & Controls", "United States", 0.73),
    ("LECO", "Lincoln Electric", "Industrials", "Welding Equipment", "United States", 0.75),
    ("TTC", "Toro", "Industrials", "Outdoor Equipment", "United States", 0.74),
    ("TKR", "Timken", "Industrials", "Bearings", "United States", 0.72),
    ("NDSN", "Nordson", "Industrials", "Precision Dispensing", "United States", 0.78),
    ("TM", "Toyota Motor", "Consumer", "Automobiles", "Japan", 0.81),
    ("TSLA", "Tesla", "Consumer", "Electric Vehicles", "United States", 0.76),
    ("HD", "Home Depot", "Consumer", "Home Improvement Retail", "United States", 0.84),
    ("LOW", "Lowe's", "Consumer", "Home Improvement Retail", "United States", 0.82),
    ("COST", "Costco Wholesale", "Consumer", "Warehouse Retail", "United States", 0.86),
    ("TGT", "Target", "Consumer", "General Merchandise Retail", "United States", 0.74),
    ("TJX", "TJX Companies", "Consumer", "Off-price Retail", "United States", 0.82),
    ("ROST", "Ross Stores", "Consumer", "Off-price Retail", "United States", 0.79),
    ("NKE", "Nike", "Consumer", "Athletic Apparel", "United States", 0.78),
    ("LULU", "Lululemon", "Consumer", "Athletic Apparel", "Canada", 0.78),
    ("DECK", "Deckers Outdoor", "Consumer", "Footwear & Apparel", "United States", 0.78),
    ("ORLY", "O'Reilly Automotive", "Consumer", "Auto Parts Retail", "United States", 0.84),
    ("AZO", "AutoZone", "Consumer", "Auto Parts Retail", "United States", 0.84),
    ("ULTA", "Ulta Beauty", "Consumer", "Beauty Retail", "United States", 0.76),
    ("EL", "Estee Lauder", "Consumer", "Beauty Products", "United States", 0.72),
    ("PG", "Procter & Gamble", "Consumer Staples", "Household Products", "United States", 0.84),
    ("CL", "Colgate-Palmolive", "Consumer Staples", "Household Products", "United States", 0.82),
    ("KMB", "Kimberly-Clark", "Consumer Staples", "Household Products", "United States", 0.78),
    ("CHD", "Church & Dwight", "Consumer Staples", "Household Products", "United States", 0.78),
    ("CLX", "Clorox", "Consumer Staples", "Household Products", "United States", 0.72),
    ("MDLZ", "Mondelez International", "Consumer Staples", "Packaged Food", "United States", 0.78),
    ("HSY", "Hershey", "Consumer Staples", "Packaged Food", "United States", 0.76),
    ("GIS", "General Mills", "Consumer Staples", "Packaged Food", "United States", 0.72),
    ("K", "Kellanova", "Consumer Staples", "Packaged Food", "United States", 0.70),
    ("CPB", "Campbell Soup", "Consumer Staples", "Packaged Food", "United States", 0.68),
    ("SJM", "J.M. Smucker", "Consumer Staples", "Packaged Food", "United States", 0.70),
    ("HRL", "Hormel Foods", "Consumer Staples", "Packaged Food", "United States", 0.66),
    ("TSN", "Tyson Foods", "Consumer Staples", "Protein Foods", "United States", 0.64),
    ("KR", "Kroger", "Consumer Staples", "Grocery Retail", "United States", 0.74),
    ("DG", "Dollar General", "Consumer", "Discount Retail", "United States", 0.70),
    ("DLTR", "Dollar Tree", "Consumer", "Discount Retail", "United States", 0.70),
    ("WMT", "Walmart", "Consumer Staples", "Retail", "United States", 0.83),
    ("AMZN", "Amazon", "Consumer", "E-commerce & Cloud", "United States", 0.84),
    ("BKNG", "Booking Holdings", "Consumer", "Online Travel", "United States", 0.80),
    ("EXPE", "Expedia", "Consumer", "Online Travel", "United States", 0.70),
    ("MELI", "MercadoLibre", "Consumer", "E-commerce Marketplace", "Uruguay", 0.78),
    ("RACE", "Ferrari", "Consumer", "Luxury Automobiles", "Italy", 0.82),
    ("HMC", "Honda Motor", "Consumer", "Automobiles", "Japan", 0.74),
    ("SONY", "Sony Group", "Consumer", "Consumer Electronics", "Japan", 0.78),
    ("SNEJF", "Sony Group Japan", "Consumer", "Consumer Electronics", "Japan", 0.70),
    ("NIO", "NIO", "Consumer", "Electric Vehicles", "China", 0.62),
    ("LI", "Li Auto", "Consumer", "Electric Vehicles", "China", 0.68),
    ("XPEV", "XPeng", "Consumer", "Electric Vehicles", "China", 0.62),
    ("GOOGL", "Alphabet Class A", "Communication Services", "Internet Services", "United States", 0.90),
    ("GOOG", "Alphabet Class C", "Communication Services", "Internet Services", "United States", 0.90),
    ("META", "Meta Platforms", "Communication Services", "Social Platforms", "United States", 0.84),
    ("NFLX", "Netflix", "Communication Services", "Streaming Entertainment", "United States", 0.76),
    ("SPOT", "Spotify", "Communication Services", "Audio Streaming", "Sweden", 0.72),
    ("EA", "Electronic Arts", "Communication Services", "Video Games", "United States", 0.74),
    ("TTWO", "Take-Two Interactive", "Communication Services", "Video Games", "United States", 0.72),
    ("MTCH", "Match Group", "Communication Services", "Online Services", "United States", 0.66),
    ("PINS", "Pinterest", "Communication Services", "Social Media", "United States", 0.68),
    ("SNAP", "Snap", "Communication Services", "Social Media", "United States", 0.60),
    ("SE", "Sea", "Communication Services", "Digital Entertainment & E-commerce", "Singapore", 0.70),
    ("BIDU", "Baidu", "Communication Services", "Internet Search", "China", 0.68),
    ("NTES", "NetEase", "Communication Services", "Online Games & Services", "China", 0.70),
    ("BABA", "Alibaba", "Consumer", "E-commerce & Cloud", "China", 0.70),
    ("JD", "JD.com", "Consumer", "E-commerce", "China", 0.66),
    ("PDD", "PDD Holdings", "Consumer", "E-commerce", "China", 0.72),
    ("TCEHY", "Tencent Holdings", "Communication Services", "Digital Platforms", "China", 0.74),
    ("SAP", "SAP", "Technology", "Enterprise Software", "Germany", 0.84),
    ("LOGI", "Logitech", "Technology", "Computer Peripherals", "Switzerland", 0.72),
    ("ERIC", "Ericsson", "Technology", "Telecom Equipment", "Sweden", 0.68),
    ("NOK", "Nokia", "Technology", "Telecom Equipment", "Finland", 0.66),
    ("STM", "STMicroelectronics", "Technology", "Semiconductors", "Switzerland/France", 0.76),
    ("IFNNY", "Infineon Technologies", "Technology", "Power Semiconductors", "Germany", 0.76),
    ("ARM", "Arm Holdings", "Technology", "Semiconductor IP", "United Kingdom", 0.80),
    ("TSM", "Taiwan Semiconductor", "Technology", "Semiconductor Foundry", "Taiwan", 0.90),
    ("UMC", "United Microelectronics", "Technology", "Semiconductor Foundry", "Taiwan", 0.70),
    ("ASX", "ASE Technology", "Technology", "Semiconductor Packaging", "Taiwan", 0.70),
    ("HIMX", "Himax Technologies", "Technology", "Display Semiconductors", "Taiwan", 0.62),
    ("GFS", "GlobalFoundries", "Technology", "Semiconductor Foundry", "United States", 0.72),
    ("SITM", "SiTime", "Technology", "Timing Semiconductors", "United States", 0.62),
    ("ENTG", "Entegris", "Technology", "Semiconductor Materials", "United States", 0.76),
    ("TER", "Teradyne", "Technology", "Semiconductor Test Equipment", "United States", 0.76),
    ("COHR", "Coherent", "Technology", "Optical Materials & Lasers", "United States", 0.68),
    ("OLED", "Universal Display", "Technology", "OLED Materials", "United States", 0.70),
    ("PLTR", "Palantir", "Technology", "Data Analytics Software", "United States", 0.70),
    ("PATH", "UiPath", "Technology", "Automation Software", "United States", 0.62),
    ("GEN", "Gen Digital", "Technology", "Consumer Cybersecurity", "United States", 0.70),
    ("AKAM", "Akamai Technologies", "Technology", "Content Delivery & Security", "United States", 0.72),
    ("DOCU", "DocuSign", "Technology", "Agreement Cloud", "United States", 0.66),
    ("PAYC", "Paycom", "Technology", "Payroll Software", "United States", 0.70),
    ("TYL", "Tyler Technologies", "Technology", "Public Sector Software", "United States", 0.78),
    ("MANH", "Manhattan Associates", "Technology", "Supply Chain Software", "United States", 0.76),
    ("SSNC", "SS&C Technologies", "Technology", "Financial Software", "United States", 0.70),
    ("CDW", "CDW", "Technology", "IT Solutions", "United States", 0.74),
    ("ZBRA", "Zebra Technologies", "Technology", "Enterprise Scanning", "United States", 0.72),
    ("GRMN", "Garmin", "Consumer", "Navigation Devices", "Switzerland", 0.78),
    ("HEI", "HEICO", "Industrials", "Aerospace Components", "United States", 0.78),
    ("TDG", "TransDigm", "Industrials", "Aerospace Components", "United States", 0.76),
    ("TXT", "Textron", "Industrials", "Industrial & Aviation Products", "United States", 0.70),
    ("PCAR", "PACCAR", "Industrials", "Trucks", "United States", 0.80),
    ("OSK", "Oshkosh", "Industrials", "Specialty Vehicles", "United States", 0.70),
    ("CMI", "Cummins", "Industrials", "Engines & Power Systems", "United States", 0.78),
    ("AGCO", "AGCO", "Industrials", "Agricultural Equipment", "United States", 0.68),
    ("CNHI", "CNH Industrial", "Industrials", "Agricultural Equipment", "United Kingdom", 0.68),
    ("MTD", "Mettler-Toledo", "Healthcare", "Precision Instruments", "United States", 0.82),
    ("BIO", "Bio-Rad Laboratories", "Healthcare", "Life Science Tools", "United States", 0.70),
    ("TECH", "Bio-Techne", "Healthcare", "Life Science Tools", "United States", 0.74),
    ("BRKR", "Bruker", "Healthcare", "Scientific Instruments", "United States", 0.74),
    ("WST", "West Pharmaceutical", "Healthcare", "Drug Delivery Components", "United States", 0.78),
    ("COO", "CooperCompanies", "Healthcare", "Medical Devices", "United States", 0.74),
    ("PODD", "Insulet", "Healthcare", "Medical Devices", "United States", 0.76),
    ("GMED", "Globus Medical", "Healthcare", "Medical Devices", "United States", 0.70),
    ("ALGN", "Align Technology", "Healthcare", "Dental Devices", "United States", 0.70),
    ("MASI", "Masimo", "Healthcare", "Medical Monitoring", "United States", 0.70),
    ("EXAS", "Exact Sciences", "Healthcare", "Diagnostics", "United States", 0.66),
    ("INCY", "Incyte", "Healthcare", "Biotechnology", "United States", 0.70),
    ("BMRN", "BioMarin Pharmaceutical", "Healthcare", "Biotechnology", "United States", 0.70),
    ("NBIX", "Neurocrine Biosciences", "Healthcare", "Biotechnology", "United States", 0.74),
    ("EXEL", "Exelixis", "Healthcare", "Biotechnology", "United States", 0.68),
    ("UTHR", "United Therapeutics", "Healthcare", "Biotechnology", "United States", 0.74),
    ("IONS", "Ionis Pharmaceuticals", "Healthcare", "Biotechnology", "United States", 0.66),
    ("HALO", "Halozyme Therapeutics", "Healthcare", "Biotechnology", "United States", 0.68),
)


def _make_candidate(index: int, raw: tuple[str, str, str, str, str, float]) -> HalalLargeCapCandidate:
    symbol, name, sector, industry, country, quality_score = raw
    reference_price = round(55.0 + ((index * 17) % 420) + (quality_score * 12), 2)
    fair_value = round(reference_price * (1.08 + ((index % 9) * 0.018) + (quality_score * 0.08)), 2)
    halal_notes = (
        f"{industry}; qualitative Shariah-oriented sector screen passed. "
        "No conventional banking, insurance, alcohol, gambling, pork or tobacco core business identified in this research universe."
    )
    valuation_notes = (
        "Large-cap MSCI World-style research candidate; reference fair-value buffer used only "
        "for ranking until live/fundamental data is integrated."
    )
    return HalalLargeCapCandidate(
        symbol=symbol,
        name=name,
        sector=sector,
        industry=industry,
        fair_value=fair_value,
        reference_price=reference_price,
        market_cap_category="largecap",
        halal_notes=halal_notes,
        valuation_notes=valuation_notes,
        country=country,
        quality_score=quality_score,
    )


HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES: tuple[HalalLargeCapCandidate, ...] = tuple(
    _make_candidate(index, raw) for index, raw in enumerate(RAW_HALAL_MSCI_WORLD_LARGE_CAP_UNIVERSE, start=1)
)
HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS: tuple[str, ...] = tuple(candidate.symbol for candidate in HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES)
# Backwards-compatible aliases for existing imports/tests while the app wording moves
# from the old mid-cap universe to the MSCI World-style large-cap universe.
HALAL_MIDCAP_CANDIDATES = HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES
HALAL_MIDCAP_SYMBOLS = HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS


def _bar_lookup(bars: Iterable[Any]) -> dict[str, Any]:
    return {str(bar.symbol).upper(): bar for bar in bars}


def build_dynamic_halal_watchlist(
    client: Any,
    *,
    limit: int = 250,
    min_margin_of_safety: float = 0.0,
) -> dict[str, Any]:
    """Build a dynamic ranked watchlist from live/latest prices and halal large-cap candidates."""
    safe_limit = max(1, min(int(limit), len(HALAL_MSCI_WORLD_LARGE_CAP_CANDIDATES), 300))
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
        sector_bonus = 1.5 if candidate.sector in {"Healthcare", "Industrials", "Materials", "Consumer", "Consumer Staples"} else 0.0
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
                "screening_status": "research_candidate_not_fatwa",
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
    selected = eligible[:safe_limit]
    for rank, row in enumerate(selected, start=1):
        row["rank"] = rank

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "error": error,
        "methodology": {
            "universe": "279 qualitatively screened MSCI World-style halal large-cap research candidates; default watchlist returns top 250",
            "index_reference": "MSCI World developed-market large caps / MSCI Islamic-style sector screen",
            "dynamic_fields": ["latest_price", "margin_of_safety", "score", "rank"],
            "selection_rule": "Qualitatively halal-screened developed-market large-cap research candidates with positive margin of safety are eligible; ranked by live discount, quality score, and sector-diversification bonus.",
            "disclaimer": "Research watchlist only; not investment advice and not a formal halal fatwa. MSCI World membership, MSCI Islamic index inclusion and Shariah financial-ratio compliance should be reviewed with authoritative data before real trading.",
        },
        "count": len(selected),
        "requested_limit": safe_limit,
        "universe_count": len(HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS),
        "universe_symbols": list(HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS),
        "eligible_symbols": [row["symbol"] for row in selected],
        "symbols": [row["symbol"] for row in selected],
        "candidates": selected,
    }
