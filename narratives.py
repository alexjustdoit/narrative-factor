"""
The 14 macro narratives tracked in the paper, with their Google Trends search terms.
Each narrative is a dict with:
  - id:    short machine-friendly key
  - label: human-readable name
  - terms: list of search terms to pass to Google Trends
"""

NARRATIVES = [
    {
        "id": "global_pandemic",
        "label": "Global Pandemic",
        "terms": ["pandemic"],
    },
    {
        "id": "ai_generative",
        "label": "AI / Generative AI",
        "terms": ["AI"],
    },
    {
        "id": "ukraine_russia",
        "label": "Ukraine-Russia Conflict",
        "terms": ["Ukraine"],
    },
    {
        "id": "middle_east",
        "label": "Middle Eastern Conflict",
        "terms": ["gaza", "israel", "hamas"],
    },
    {
        "id": "iran_conflict",
        "label": "Iran Military Conflict",
        "terms": ["iran"],
    },
    {
        "id": "inflation",
        "label": "Inflation",
        "terms": ["inflation"],
    },
    {
        "id": "bitcoin",
        "label": "Bitcoin / Cryptocurrency",
        "terms": ["bitcoin"],
    },
    {
        "id": "immigration",
        "label": "US Immigration Rhetoric",
        "terms": ["immigration"],
    },
    {
        "id": "us_tariffs",
        "label": "US Tariffs",
        "terms": ["tariffs", "tariff"],
    },
    {
        "id": "recession",
        "label": "Economic Recession",
        "terms": ["recession"],
    },
    {
        "id": "unemployment",
        "label": "Rise in Unemployment",
        "terms": ["unemployment"],
    },
    {
        "id": "venezuela",
        "label": "US-Venezuela Tensions",
        "terms": ["venezuela"],
    },
    {
        "id": "gpu_demand",
        "label": "GPU Demand for AI",
        "terms": ["nvidia", "gpus", "gpu"],
    },
    {
        "id": "greenland",
        "label": "US-Greenland Tensions",
        "terms": ["greenland"],
    },
]

NARRATIVE_IDS = [n["id"] for n in NARRATIVES]
