"""
Macro narratives tracked by the pipeline.

Expanded from 14 to 28 narratives. The original 14 replicate the paper's methodology.
The 14 additions draw from Shiller's "Narrative Economics" (2019) perennial narrative
taxonomy, covering recurring themes that have proven ability to influence economic behavior:
financial panic, wage-price spiral, housing boom/bust, corporate greed, labor unrest,
government debt crisis, consumer pullback, China decoupling, energy transition,
interest rate shock, supply chain crisis, AI regulation, drug pricing, and cybersecurity.

Each narrative has:
  - id:          short machine-friendly key
  - label:       human-readable name
  - terms:       Google Trends search terms (list; Trends averages them)
  - description: market-relevant description used in LLM scoring prompts.
                 Explains what the narrative means economically and what kinds
                 of companies are typically affected.

The activation filter (activation.py) determines which narratives are currently
"live" based on Google Trends spike detection. With 28 candidates, typically
5–15 are active at any given time.
"""

NARRATIVES = [
    # -----------------------------------------------------------------------
    # ORIGINAL 14 — replicating the paper
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # NEW 14 — drawn from Shiller's perennial narrative taxonomy + 2020-2026
    # current-events extensions. Activation filter decides which are live.
    # -----------------------------------------------------------------------

    {
        "id": "banking_crisis",
        "label": "Banking Crisis / Financial Panic",
        "terms": ["bank collapse", "bank failure", "bank run"],
        "description": (
            "A Shiller perennial narrative: sudden loss of confidence in banks triggering "
            "deposit flight, credit contraction, and contagion fear. Banks and regional lenders "
            "face direct existential risk; insurance companies face mark-to-market losses. "
            "Flight to quality benefits large 'too-big-to-fail' banks, money-market funds, "
            "and Treasury-exposed assets. Companies reliant on credit markets for working "
            "capital or expansion face financing cost spikes. Gold and safe-haven assets benefit."
        ),
    },
    {
        "id": "wage_price_spiral",
        "label": "Wage-Price Spiral",
        "terms": ["wage inflation", "labor shortage", "worker shortage"],
        "description": (
            "A Shiller perennial narrative: wages and prices mutually reinforce each other "
            "upward, threatening persistent inflation. Labor-intensive industries (food service, "
            "hospitality, retail, logistics, manufacturing) face margin compression as wages "
            "outpace pricing power. Companies with high automation or strong pricing power "
            "are relatively insulated. Businesses able to pass through costs (luxury goods, "
            "software, healthcare) are less impacted. Central banks tighten aggressively, "
            "hurting rate-sensitive sectors."
        ),
    },
    {
        "id": "housing_bust",
        "label": "Housing Boom / Bust",
        "terms": ["housing bubble", "housing crash", "home prices"],
        "description": (
            "A Shiller perennial narrative (he literally wrote the Case-Shiller index): "
            "public obsession with housing prices creating boom-bust cycles. During booms, "
            "homebuilders, mortgage lenders, real estate brokers, and home improvement "
            "retailers benefit. During busts, these same sectors are devastated; banks face "
            "mortgage default losses; home equity-funded consumer spending collapses. "
            "Rental property operators may benefit from displaced would-be buyers."
        ),
    },
    {
        "id": "corporate_greed",
        "label": "Corporate Greed / Price Gouging",
        "terms": ["price gouging", "corporate greed", "corporate profits"],
        "description": (
            "A Shiller perennial narrative: public anger at companies accused of exploiting "
            "crises or market power to extract excess profits at consumers' expense. "
            "Companies with inelastic-demand products (food, fuel, pharma, utilities) face "
            "reputational and regulatory risk. Consumer boycotts and government price controls "
            "are the narrative's primary economic mechanism. Companies seen as fairly priced "
            "or consumer-aligned benefit from contrast. Commoditized or competitive sectors "
            "face less individual targeting than branded oligopolists."
        ),
    },
    {
        "id": "labor_strikes",
        "label": "Labor Strike Wave",
        "terms": ["labor strike", "strike", "union organizing"],
        "description": (
            "A Shiller perennial narrative: surges in labor organizing, strike activity, "
            "and worker power reshaping wage expectations and production capacity. "
            "Companies with highly unionized workforces (auto, airlines, freight, ports, "
            "entertainment studios) face direct production disruption and wage cost increases. "
            "Non-union competitors gain relative advantage during rival strikes. "
            "Staffing agencies benefit from replacement labor demand. Companies in "
            "right-to-work sectors with low union exposure are relatively insulated."
        ),
    },
    {
        "id": "government_debt",
        "label": "Government Debt / Fiscal Crisis",
        "terms": ["debt ceiling", "national debt", "fiscal crisis"],
        "description": (
            "Public alarm about government debt levels, deficit spending, and debt ceiling "
            "standoffs threatening US creditworthiness. Financial companies holding large "
            "Treasury portfolios face mark-to-market risk if yields spike. Defense and "
            "government contractors face spending cut risk during fiscal austerity debates. "
            "Companies reliant on government contracts are directly exposed. Higher sovereign "
            "risk premiums raise the cost of capital broadly, with the greatest impact on "
            "long-duration assets and highly leveraged businesses."
        ),
    },
    {
        "id": "consumer_pullback",
        "label": "Consumer Spending Pullback",
        "terms": ["consumer spending", "consumer pullback", "spending cuts"],
        "description": (
            "A Shiller perennial narrative: public shift toward frugality and restraint, "
            "reducing discretionary spending across the economy. Consumer discretionary "
            "retailers, restaurants, travel companies, and luxury goods face volume declines. "
            "Dollar stores, discount chains, and essential services benefit as consumers "
            "trade down. Home entertainment substitutes for out-of-home spending. "
            "Consumer credit companies face increased delinquency risk as households "
            "struggle to maintain prior spending levels on reduced real income."
        ),
    },
    {
        "id": "china_decoupling",
        "label": "US-China Decoupling",
        "terms": ["China decoupling", "China trade war", "made in China"],
        "description": (
            "Growing narrative that the US and China are economically separating across "
            "supply chains, technology, and capital markets. Companies manufacturing in "
            "China or dependent on Chinese components face relocation pressure and cost "
            "increases. Reshoring beneficiaries (US-based manufacturers, Mexico-based "
            "nearshore manufacturers) benefit. Chinese-market-exposed companies (luxury, "
            "semiconductors, software) face access risk. Defense and semiconductor companies "
            "with technology export restrictions face compliance costs."
        ),
    },
    {
        "id": "energy_transition",
        "label": "Energy Transition / Clean Energy",
        "terms": ["clean energy", "renewable energy", "net zero"],
        "description": (
            "The multi-year shift away from fossil fuels toward renewable energy driven by "
            "policy, capital allocation, and public narrative pressure. Solar, wind, battery "
            "storage, EV manufacturers, and clean infrastructure companies benefit from "
            "policy tailwinds and capital flows. Fossil fuel producers face stranded asset "
            "risk and rising cost of capital. Utilities transitioning to renewables are "
            "positioned constructively; those dependent on coal and gas face regulatory "
            "and reputational headwinds. Critical minerals (lithium, copper, rare earths) "
            "benefit from EV and grid buildout demand."
        ),
    },
    {
        "id": "interest_rate_shock",
        "label": "Interest Rate Shock",
        "terms": ["rate hike", "interest rates", "Federal Reserve"],
        "description": (
            "Public focus on Federal Reserve rate decisions — either aggressive hikes or "
            "anticipated cuts — driving repricing across asset classes. Rising-rate narratives "
            "hurt long-duration growth stocks, REITs, utilities, and highly leveraged "
            "companies through higher discount rates and debt service costs. Banks benefit "
            "from wider net interest margins in hiking cycles but face credit risk. "
            "Falling-rate narratives benefit rate-sensitive sectors and refinancing activity. "
            "Mortgage lenders, homebuilders, and housing-adjacent companies are among "
            "the most rate-sensitive businesses in the S&P 500."
        ),
    },
    {
        "id": "supply_chain_crisis",
        "label": "Supply Chain Crisis",
        "terms": ["supply chain crisis", "supply shortage", "chip shortage"],
        "description": (
            "Widespread product shortages and logistics disruptions causing delivery delays, "
            "inventory build-or-bust cycles, and production shutdowns. Companies with "
            "diversified supplier bases or domestic manufacturing are relatively resilient. "
            "Industries dependent on single-source components (autos with semiconductors, "
            "electronics, medical devices) face production losses. Logistics and freight "
            "companies benefit from pricing power during acute shortages. Retailers "
            "with inventory mismatches face margin pressure as conditions normalize."
        ),
    },
    {
        "id": "ai_regulation",
        "label": "AI Regulation / AI Risk",
        "terms": ["AI regulation", "AI safety", "AI ban"],
        "description": (
            "Public and political attention to risks posed by artificial intelligence — "
            "job displacement, misinformation, autonomous weapons, privacy, and systemic risk — "
            "driving regulatory proposals. Large AI platform companies face compliance costs "
            "and potential product restrictions. Companies that use AI for consequential "
            "decisions (credit, hiring, healthcare) face increased liability risk. "
            "AI safety and governance companies benefit. Companies with strong human-review "
            "processes may benefit from regulatory contrast against automated-only competitors. "
            "The narrative is distinct from the 'AI adoption' narrative — this measures fear, "
            "not enthusiasm."
        ),
    },
    {
        "id": "drug_pricing",
        "label": "Drug Pricing / Pharma Regulation",
        "terms": ["drug prices", "drug pricing", "pharmaceutical prices"],
        "description": (
            "Public and legislative focus on high prescription drug prices driving regulatory "
            "reform risk for pharmaceutical companies. Brand-name drug manufacturers with "
            "pricing power face direct revenue risk from mandatory negotiation or price caps. "
            "Generic and biosimilar manufacturers benefit as alternatives. Pharmacy benefit "
            "managers face scrutiny of their role in pricing. Biotech companies in drug "
            "development face uncertainty about eventual pricing power for pipeline assets. "
            "Hospitals and health systems may benefit from reduced drug cost pressure."
        ),
    },
    {
        "id": "cybersecurity",
        "label": "Cybersecurity Threat",
        "terms": ["ransomware", "data breach", "cyberattack"],
        "description": (
            "High-profile ransomware attacks, data breaches, or state-sponsored cyber "
            "operations driving corporate and government cybersecurity spending. Cybersecurity "
            "software and services companies (endpoint protection, network security, identity "
            "management, SIEM) benefit directly from increased enterprise budgets. Companies "
            "victimized by attacks face remediation costs, regulatory fines, and reputational "
            "damage. Critical infrastructure operators (utilities, pipelines, hospitals) "
            "face operational risk. Cloud security providers benefit as companies accelerate "
            "zero-trust architecture adoption."
        ),
    },
]

NARRATIVE_IDS = [n["id"] for n in NARRATIVES]
NARRATIVE_MAP = {n["id"]: n for n in NARRATIVES}
