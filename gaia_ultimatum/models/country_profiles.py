"""Per-country indicator + vulnerability archetypes.

The four equilibrium indicators (résilience, stabilité, régénération,
adaptation) used to be uniform-random for every country, which made
Iceland and Bangladesh feel identical at game start. This module maps
each major ISO_A3 country code to one of a handful of climate /
development archetypes, each of which carries:

- A baseline value for the four indicators (0..1).
- A per-catastrophe vulnerability multiplier (>1 = more vulnerable, <1 =
  more resilient) that scales how fast that country's state degrades
  under a given catastrophe element.

Tuned to reflect generally accepted patterns (low-lying delta nations
take more damage from Eau, arid regions burn faster under Feu, polar
nations carry strong stability but degrade fast under Vie, etc.). Not
prescriptive — every country falls back to a neutral profile when its
ISO is missing here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryProfile:
    """Archetype baseline for a country's defensive profile."""
    name: str
    resilience: float
    stability: float
    regeneration: float
    adaptation: float
    # Multiplier applied to incoming catastrophe impact, keyed by element
    # name (matches Catastrophe.name: Eau / Feu / Terre / Air / Vie).
    vulnerability: dict[str, float]


# ----------------------------------------------------------------- archetypes


PROFILES: dict[str, CountryProfile] = {
    # Wealthy temperate states with mature infrastructure. Generally
    # resilient and stable, lower natural regeneration than tropical zones.
    "developed_temperate": CountryProfile(
        "developed_temperate",
        resilience=0.70, stability=0.75, regeneration=0.45, adaptation=0.65,
        vulnerability={"Eau": 0.85, "Feu": 1.00, "Terre": 0.90,
                       "Air": 0.95, "Vie": 0.85},
    ),
    # Island / coastal states — strong adaptation + regeneration but more
    # exposed to Eau (sea-level, storm surge) and Air (cyclones).
    "developed_island": CountryProfile(
        "developed_island",
        resilience=0.60, stability=0.55, regeneration=0.70, adaptation=0.70,
        vulnerability={"Eau": 1.30, "Feu": 0.90, "Terre": 1.05,
                       "Air": 1.20, "Vie": 0.95},
    ),
    # Mediterranean — high fire risk, drought-prone, otherwise developed.
    "mediterranean": CountryProfile(
        "mediterranean",
        resilience=0.55, stability=0.55, regeneration=0.50, adaptation=0.60,
        vulnerability={"Eau": 0.95, "Feu": 1.40, "Terre": 1.00,
                       "Air": 1.00, "Vie": 0.95},
    ),
    # Densely populated developing nations — large urban footprint amplifies
    # disease vectors + flooding damage; lower baseline resilience.
    "developing_dense": CountryProfile(
        "developing_dense",
        resilience=0.40, stability=0.40, regeneration=0.55, adaptation=0.55,
        vulnerability={"Eau": 1.25, "Feu": 1.10, "Terre": 1.10,
                       "Air": 1.20, "Vie": 1.40},
    ),
    # Low-lying delta / tropical states — extreme flood + cyclone exposure.
    "tropical_delta": CountryProfile(
        "tropical_delta",
        resilience=0.35, stability=0.35, regeneration=0.75, adaptation=0.50,
        vulnerability={"Eau": 1.50, "Feu": 0.85, "Terre": 1.10,
                       "Air": 1.35, "Vie": 1.20},
    ),
    # Arid / Sahelian — extreme heat + drought, very vulnerable to Feu.
    "arid_sahelian": CountryProfile(
        "arid_sahelian",
        resilience=0.30, stability=0.40, regeneration=0.25, adaptation=0.45,
        vulnerability={"Eau": 1.30, "Feu": 1.50, "Terre": 1.00,
                       "Air": 1.05, "Vie": 1.15},
    ),
    # Continental / boreal — large landmass, vulnerable to forest fires and
    # earthquakes, generally cold-resistant.
    "continental_boreal": CountryProfile(
        "continental_boreal",
        resilience=0.60, stability=0.65, regeneration=0.55, adaptation=0.50,
        vulnerability={"Eau": 0.90, "Feu": 1.30, "Terre": 1.05,
                       "Air": 0.95, "Vie": 0.85},
    ),
    # Pacific rim / seismic — strong regeneration + adaptation, high Terre
    # exposure (subduction zones).
    "pacific_seismic": CountryProfile(
        "pacific_seismic",
        resilience=0.55, stability=0.45, regeneration=0.65, adaptation=0.70,
        vulnerability={"Eau": 1.05, "Feu": 1.05, "Terre": 1.40,
                       "Air": 1.15, "Vie": 0.95},
    ),
    # Polar / isolated — extreme stability, very low Vie exposure due to
    # small population, but Eau (ice melt) and Air (polar storms) bite.
    "polar_isolated": CountryProfile(
        "polar_isolated",
        resilience=0.75, stability=0.80, regeneration=0.55, adaptation=0.45,
        vulnerability={"Eau": 1.45, "Feu": 0.55, "Terre": 0.90,
                       "Air": 1.30, "Vie": 0.60},
    ),
    # Andean / mountainous developing — slow regen, terrain risk, moderate
    # vulnerability to most.
    "andean_mountainous": CountryProfile(
        "andean_mountainous",
        resilience=0.45, stability=0.50, regeneration=0.40, adaptation=0.55,
        vulnerability={"Eau": 1.15, "Feu": 1.05, "Terre": 1.30,
                       "Air": 1.05, "Vie": 1.05},
    ),
    # Small island nation (Pacific / Caribbean) — extreme Eau + Air risk.
    "small_island_state": CountryProfile(
        "small_island_state",
        resilience=0.35, stability=0.40, regeneration=0.65, adaptation=0.55,
        vulnerability={"Eau": 1.60, "Feu": 0.85, "Terre": 1.10,
                       "Air": 1.50, "Vie": 1.10},
    ),
    # Tropical rainforest — strong regen via biodiversity, vulnerable to
    # Feu (deforestation) and Vie (zoonotic disease).
    "tropical_forest": CountryProfile(
        "tropical_forest",
        resilience=0.45, stability=0.45, regeneration=0.80, adaptation=0.55,
        vulnerability={"Eau": 1.10, "Feu": 1.30, "Terre": 1.00,
                       "Air": 1.10, "Vie": 1.25},
    ),
}


# Neutral fallback applied when a country isn't in ISO_TO_PROFILE — keeps
# unspecified entries playable without skewing their stats.
NEUTRAL_PROFILE = CountryProfile(
    "neutral",
    resilience=0.50, stability=0.50, regeneration=0.50, adaptation=0.50,
    vulnerability={"Eau": 1.0, "Feu": 1.0, "Terre": 1.0, "Air": 1.0, "Vie": 1.0},
)


# Player-facing French labels for each archetype. The internal `name`
# fields stay machine-readable (snake_case) so existing serialisation
# and ISO_TO_PROFILE keys keep working; this map gives the renderer a
# readable label to surface in the country hover tooltip and the country
# info panel. Educational value: hovering Bangladesh shows "Delta
# tropical · ×1,50 EAU" so the player learns *why* low-lying delta
# nations are more exposed.
PROFILE_DISPLAY_LABELS: dict[str, str] = {
    "developed_temperate": "Tempéré développé",
    "developed_island":    "Île développée",
    "mediterranean":       "Méditerranéen",
    "developing_dense":    "Densément peuplé",
    "tropical_delta":      "Delta tropical",
    "arid_sahelian":       "Aride · Sahel",
    "continental_boreal":  "Continental boréal",
    "pacific_seismic":     "Pacifique sismique",
    "polar_isolated":      "Polaire · isolé",
    "andean_mountainous":  "Andin · montagneux",
    "small_island_state":  "Petit État insulaire",
    "tropical_forest":     "Forêt tropicale",
    "neutral":             "Profil neutre",
}


def display_label_for(profile_name: str) -> str:
    """Return the player-facing French label for an archetype.

    Falls back to a capitalised version of the raw name when the
    archetype isn't in the table — keeps the tooltip readable even if
    new archetypes ship before their labels do.
    """
    label = PROFILE_DISPLAY_LABELS.get(profile_name)
    if label:
        return label
    return profile_name.replace("_", " ").capitalize()


# ------------------------------------------------- per-country assignments


ISO_TO_PROFILE: dict[str, str] = {
    # Developed temperate (W. Europe / Anglosphere / N.E. Asia inland)
    "FRA": "developed_temperate", "DEU": "developed_temperate",
    "GBR": "developed_temperate", "BEL": "developed_temperate",
    "NLD": "developed_temperate", "LUX": "developed_temperate",
    "AUT": "developed_temperate", "CHE": "developed_temperate",
    "CZE": "developed_temperate", "POL": "developed_temperate",
    "DNK": "developed_temperate", "IRL": "developed_temperate",
    "USA": "developed_temperate", "KOR": "developed_temperate",
    "HUN": "developed_temperate", "SVK": "developed_temperate",
    "SVN": "developed_temperate",
    # Continental / boreal
    "RUS": "continental_boreal", "CAN": "continental_boreal",
    "SWE": "continental_boreal", "NOR": "continental_boreal",
    "FIN": "continental_boreal", "EST": "continental_boreal",
    "LVA": "continental_boreal", "LTU": "continental_boreal",
    "BLR": "continental_boreal", "UKR": "continental_boreal",
    "KAZ": "continental_boreal", "MNG": "continental_boreal",
    # Island states
    "JPN": "pacific_seismic", "TWN": "pacific_seismic",
    "PHL": "pacific_seismic", "IDN": "pacific_seismic",
    "NZL": "developed_island", "AUS": "developed_island",
    "GBR-island": "developed_island",  # never matched — kept as marker
    "ISL": "polar_isolated", "GRL": "polar_isolated",
    # Mediterranean
    "ITA": "mediterranean", "ESP": "mediterranean",
    "GRC": "mediterranean", "PRT": "mediterranean",
    "MLT": "mediterranean", "CYP": "mediterranean",
    "ALB": "mediterranean", "HRV": "mediterranean",
    "MNE": "mediterranean", "ISR": "mediterranean",
    "LBN": "mediterranean", "TUR": "mediterranean",
    "DZA": "mediterranean", "TUN": "mediterranean",
    "MAR": "mediterranean", "MKD": "mediterranean",
    "BIH": "mediterranean", "SRB": "mediterranean",
    # Developing dense
    "CHN": "developing_dense", "IND": "developing_dense",
    "PAK": "developing_dense", "EGY": "developing_dense",
    "IRN": "developing_dense", "IRQ": "developing_dense",
    "MEX": "developing_dense", "BRA": "developing_dense",
    "NGA": "developing_dense", "ETH": "developing_dense",
    "COD": "developing_dense", "TZA": "developing_dense",
    "KEN": "developing_dense", "ZAF": "developing_dense",
    "ARG": "developing_dense", "COL": "developing_dense",
    "VEN": "developing_dense", "PER": "developing_dense",
    # Tropical delta — high water-borne risk
    "BGD": "tropical_delta", "VNM": "tropical_delta",
    "MMR": "tropical_delta", "KHM": "tropical_delta",
    "THA": "tropical_delta", "MYS": "tropical_delta",
    "LKA": "tropical_delta", "GUY": "tropical_delta",
    "SUR": "tropical_delta",
    # Arid / Sahelian
    "NER": "arid_sahelian", "MLI": "arid_sahelian",
    "TCD": "arid_sahelian", "SDN": "arid_sahelian",
    "SSD": "arid_sahelian", "ERI": "arid_sahelian",
    "SOM": "arid_sahelian", "YEM": "arid_sahelian",
    "SAU": "arid_sahelian", "AFG": "arid_sahelian",
    "MRT": "arid_sahelian", "LBY": "arid_sahelian",
    "BFA": "arid_sahelian", "SYR": "arid_sahelian",
    "JOR": "arid_sahelian", "OMN": "arid_sahelian",
    "ARE": "arid_sahelian", "QAT": "arid_sahelian",
    "KWT": "arid_sahelian", "BHR": "arid_sahelian",
    # Tropical forest / biodiversity hotspots
    "AGO": "tropical_forest", "GAB": "tropical_forest",
    "CMR": "tropical_forest", "CIV": "tropical_forest",
    "GHA": "tropical_forest", "LBR": "tropical_forest",
    "SLE": "tropical_forest", "UGA": "tropical_forest",
    "RWA": "tropical_forest", "BDI": "tropical_forest",
    "MDG": "tropical_forest", "CAF": "tropical_forest",
    "COG": "tropical_forest", "GIN": "tropical_forest",
    "BEN": "tropical_forest", "TGO": "tropical_forest",
    "PNG": "tropical_forest",
    # Andean / mountainous developing
    "ECU": "andean_mountainous", "BOL": "andean_mountainous",
    "NPL": "andean_mountainous", "BTN": "andean_mountainous",
    "TJK": "andean_mountainous", "KGZ": "andean_mountainous",
    "ARM": "andean_mountainous", "GEO": "andean_mountainous",
    "AZE": "andean_mountainous", "UZB": "andean_mountainous",
    "GTM": "andean_mountainous", "HND": "andean_mountainous",
    # Small island states
    "FJI": "small_island_state", "TON": "small_island_state",
    "SLB": "small_island_state", "VUT": "small_island_state",
    "WSM": "small_island_state", "KIR": "small_island_state",
    "TUV": "small_island_state", "NRU": "small_island_state",
    "PLW": "small_island_state", "MHL": "small_island_state",
    "FSM": "small_island_state", "MDV": "small_island_state",
    "BHS": "small_island_state", "BRB": "small_island_state",
    "JAM": "small_island_state", "CUB": "small_island_state",
    "HTI": "small_island_state", "DOM": "small_island_state",
    "TTO": "small_island_state", "CPV": "small_island_state",
    "MUS": "small_island_state", "COM": "small_island_state",
    "STP": "small_island_state", "VCT": "small_island_state",
    "LCA": "small_island_state", "GRD": "small_island_state",
    "DMA": "small_island_state", "ATG": "small_island_state",
    "KNA": "small_island_state",
    # Singapore is dense but island
    "SGP": "developed_island",
    # Hong Kong + Macao
    "HKG": "developed_island", "MAC": "developed_island",
}


def profile_for(iso_a3: str | None) -> CountryProfile:
    """Return the archetype for ``iso_a3`` or the neutral profile."""
    if not iso_a3:
        return NEUTRAL_PROFILE
    name = ISO_TO_PROFILE.get(iso_a3)
    if name is None:
        return NEUTRAL_PROFILE
    return PROFILES.get(name, NEUTRAL_PROFILE)
