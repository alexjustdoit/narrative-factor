"""
The 14 macro narratives tracked in the paper.

Each narrative has:
  - id:          short machine-friendly key
  - label:       human-readable name
  - terms:       Google Trends search terms
  - description: market-relevant description used in LLM scoring prompts.
                 Explains what the narrative means economically and what kinds
                 of companies are typically affected.
"""

NARRATIVES = [
    {
        "id": "global_pandemic",
        "label": "Global Pandemic",
        "terms": ["pandemic"],
        "description": (
            "A global infectious disease outbreak disrupting economic activity, supply chains, "
            "and consumer behavior. Companies involved in vaccines, diagnostics, remote work "
            "infrastructure, e-commerce, and home delivery benefit. Airlines, hotels, restaurants, "
            "live entertainment, office real estate, and brick-and-mortar retail are hurt. "
            "Healthcare systems face surging demand while elective procedures collapse."
        ),
    },
    {
        "id": "ai_generative",
        "label": "AI / Generative AI",
        "terms": ["AI"],
        "description": (
            "The rapid mainstream adoption of generative AI models (large language models, "
            "image generators, coding assistants) driving enterprise software spending and "
            "infrastructure buildout. Cloud providers, GPU manufacturers, AI software platforms, "
            "and data center operators benefit strongly. Companies that sell AI-powered productivity "
            "tools or embed AI into existing products benefit moderately. Industries facing "
            "automation of white-collar tasks (legal research, customer support, content creation) "
            "face disruption risk."
        ),
    },
    {
        "id": "ukraine_russia",
        "label": "Ukraine-Russia Conflict",
        "terms": ["Ukraine"],
        "description": (
            "The armed conflict between Russia and Ukraine disrupting European energy markets, "
            "global commodity flows, and defense spending priorities. European natural gas and "
            "LNG suppliers, US defense contractors, and agricultural commodity producers benefit. "
            "Companies with significant Russian operations or European energy exposure are hurt. "
            "NATO member countries increased defense budgets substantially, benefiting aerospace "
            "and defense primes."
        ),
    },
    {
        "id": "middle_east",
        "label": "Middle Eastern Conflict",
        "terms": ["gaza", "israel", "hamas"],
        "description": (
            "Escalating military conflict in the Middle East raising geopolitical risk and "
            "threatening regional stability. Defense contractors and cybersecurity firms benefit "
            "from increased government spending. Oil and energy companies benefit from supply "
            "disruption risk premiums. Companies with significant operations, customers, or "
            "supply chains in the region face operational risk. Tourism and hospitality in "
            "affected areas are directly hurt."
        ),
    },
    {
        "id": "iran_conflict",
        "label": "Iran Military Conflict",
        "terms": ["iran"],
        "description": (
            "Heightened military tensions involving Iran threatening Strait of Hormuz shipping "
            "lanes and Middle East oil supply. Energy companies and tanker operators benefit "
            "from supply disruption risk. Defense and cybersecurity contractors benefit from "
            "government response spending. Companies dependent on stable Middle East oil supply "
            "or regional trade routes face cost and operational risk."
        ),
    },
    {
        "id": "inflation",
        "label": "Inflation",
        "terms": ["inflation"],
        "description": (
            "Sustained above-target consumer price inflation driving central bank rate hikes "
            "and compressing consumer purchasing power. Commodity producers, real assets owners, "
            "and companies with strong pricing power benefit. Rate-sensitive sectors (real estate, "
            "utilities, long-duration growth stocks) are hurt by higher discount rates. Consumer "
            "discretionary companies face demand compression as real incomes fall. Banks benefit "
            "from wider net interest margins in rate-hiking cycles."
        ),
    },
    {
        "id": "bitcoin",
        "label": "Bitcoin / Cryptocurrency",
        "terms": ["bitcoin"],
        "description": (
            "Rising mainstream adoption and price appreciation of Bitcoin and cryptocurrencies "
            "driving institutional investment and regulatory attention. Crypto exchanges, Bitcoin "
            "miners, blockchain infrastructure providers, and companies holding Bitcoin on their "
            "balance sheets benefit directly. Traditional financial institutions face disruption "
            "risk but also fee opportunities from crypto custody and trading. Companies building "
            "crypto payment rails or DeFi infrastructure benefit from increased activity."
        ),
    },
    {
        "id": "immigration",
        "label": "US Immigration Rhetoric",
        "terms": ["immigration"],
        "description": (
            "Heightened political focus on US immigration policy creating uncertainty around "
            "labor supply, deportation risk, and visa programs. Industries heavily dependent on "
            "immigrant labor (agriculture, construction, hospitality, meatpacking) face workforce "
            "cost and availability risk. Technology companies dependent on H-1B skilled worker "
            "visas face hiring constraints. Private prison and detention facility operators "
            "may benefit from enforcement spending."
        ),
    },
    {
        "id": "us_tariffs",
        "label": "US Tariffs",
        "terms": ["tariffs", "tariff"],
        "description": (
            "US imposition of broad import tariffs raising costs for companies with global "
            "supply chains and triggering retaliatory tariffs on US exports. Domestically "
            "manufactured goods producers benefit from reduced import competition. Companies "
            "with China-heavy supply chains (consumer electronics, apparel, furniture) face "
            "significant cost increases. US agricultural exporters are hurt by retaliatory "
            "tariffs. Logistics and trade finance companies face volume uncertainty."
        ),
    },
    {
        "id": "recession",
        "label": "Economic Recession",
        "terms": ["recession"],
        "description": (
            "Growing market expectations of a US or global economic contraction driving "
            "risk-off behavior and earnings estimate cuts. Defensive sectors (consumer staples, "
            "utilities, healthcare) outperform as investors seek stability. Cyclicals (industrials, "
            "materials, consumer discretionary) are hurt by anticipated demand declines. "
            "Discount retailers and value-oriented businesses benefit as consumers trade down. "
            "Financial companies face credit quality deterioration and loan loss provisions."
        ),
    },
    {
        "id": "unemployment",
        "label": "Rise in Unemployment",
        "terms": ["unemployment"],
        "description": (
            "Rising US unemployment weakening consumer spending and increasing credit default "
            "risk. Discount retailers, dollar stores, and essential service providers are "
            "relatively resilient. Consumer discretionary, luxury goods, and housing-related "
            "companies face demand compression. Banks and lenders face rising delinquencies. "
            "Staffing agencies and job platform companies see increased activity as displaced "
            "workers seek new employment."
        ),
    },
    {
        "id": "venezuela",
        "label": "US-Venezuela Tensions",
        "terms": ["venezuela"],
        "description": (
            "Heightened US-Venezuela geopolitical tensions affecting Latin American oil supply "
            "and regional trade. Oil companies with Venezuelan assets or exposure to Latin "
            "American supply chains are directly affected. Energy companies benefit from "
            "supply disruption risk premiums on Venezuelan crude. Companies with significant "
            "Latin American operations face political and currency risk."
        ),
    },
    {
        "id": "gpu_demand",
        "label": "GPU Demand for AI",
        "terms": ["nvidia", "gpus", "gpu"],
        "description": (
            "Surging demand for high-performance GPUs to train and run AI models creating "
            "a multi-year hardware supercycle. GPU manufacturers (primarily NVIDIA) and their "
            "supply chain partners (TSMC, HBM memory makers, substrate suppliers) benefit "
            "directly. Data center operators and cloud providers are expanding GPU capacity "
            "rapidly. Companies that can monetize GPU access or build on GPU infrastructure "
            "benefit. Traditional CPU-focused companies face relative displacement."
        ),
    },
    {
        "id": "greenland",
        "label": "US-Greenland Tensions",
        "terms": ["greenland", "denmark"],
        "description": (
            "US geopolitical interest in Greenland raising Arctic resource and strategic "
            "positioning concerns. Mining companies with Arctic or Greenland resource interests "
            "benefit from increased attention to rare earth and mineral deposits. Defense and "
            "Arctic logistics companies benefit from strategic interest. Danish and Nordic "
            "companies with Greenland operations face political uncertainty."
        ),
    },
]

NARRATIVE_IDS = [n["id"] for n in NARRATIVES]
NARRATIVE_MAP = {n["id"]: n for n in NARRATIVES}
