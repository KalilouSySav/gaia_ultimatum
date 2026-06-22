"""Top-level game state + turn logic (no rendering or input)."""

from __future__ import annotations

import logging
import math
import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gaia_ultimatum.assets import SKILLS_JSON, ZONES_GEOJSON
from gaia_ultimatum.config import DEFAULT_CONFIG, Config
from gaia_ultimatum.models.catastrophe import Catastrophe, CatastrophePoint
from gaia_ultimatum.models.country import Country
from gaia_ultimatum.models.evolution import EvolutionTree
from gaia_ultimatum.models.gaia import Gaia
from gaia_ultimatum.models.humans import Humans
from gaia_ultimatum.models.skill_catalog import SkillCatalog, load_skill_catalog
from gaia_ultimatum.models.world import World

logger = logging.getLogger(__name__)

NEWS_CAPACITY = 24

# Spread tuning.
SPREAD_NEIGHBORS = 3            # candidates per infected country per turn
SPREAD_INFECTED_THRESHOLD = 0.05  # state above which a country can spread
SPREAD_DISTANCE_HALF = 25.0     # degrees of arc where chance halves (great-circle)
SPREAD_BASE_MULT = 0.55         # base scaling factor for spread chance
SPREAD_NATURAL_FRACTION = 0.4   # fraction of impact applied as natural progression
EDGE_LIFETIME_FRAMES = 50       # ≈0.83s @60fps (was 90)

# Cluster-cascade tuning. The pure-distance spread model misses a
# real-world dynamic: when a country is *surrounded* by critical
# neighbours, it takes damage even without a direct spread roll —
# refugee flows, supply-chain breakage, shared climate stress, and
# common environmental factors all degrade the surviving region.
# Without this, a player could focus defence on a handful of key
# countries while letting whole regions collapse around them, and the
# defended countries would be untouched by the collapse next door.
#
# Activation threshold: 3+ nearest neighbours at state ≥ 0.5 (the same
# threshold ``_global_critical_share`` uses for "critical population").
# Below 3 critical neighbours, the cluster signal is too sparse to
# read as a genuine surrounded-region cascade and we let pure spread
# do its job. At 3 / 4+ neighbours the country takes 0.20 / 0.40 of
# normal impact respectively — a soft pressure (less than the 0.4
# natural-progression rate so an infected country still loses more
# from being infected than from being surrounded) but enough that
# defended islands in collapsing regions can't sit safely forever.
CLUSTER_CRITICAL_NEIGHBOUR_STATE = 0.5
CLUSTER_NEIGHBOURS_LOOKED = 4
CLUSTER_CASCADE_PRESSURE_BY_COUNT: dict[int, float] = {
    3: 0.20,
    4: 0.40,
}


def _natural_progression_multiplier(element: str, state: float) -> float:
    """Per-element shape for natural progression of an infected country.

    Returns a multiplier on ``SPREAD_NATURAL_FRACTION`` whose integral
    over ``state ∈ [0, 1]`` equals 1.0 for every element — total
    progression magnitude across the run is preserved, only the *time
    signature* shifts. Each element gets the curve that matches its
    real-world dynamics:

      * **Vie** (pandemic): 0.4 → 1.6 — exponential growth, slow seed,
        fast collapse near saturation.
      * **Feu** (wildfire): 0.6 → 1.4 — ramps up as the fire matures,
        sustains in the late stage.
      * **Terre** (earthquake): 1.5 → 0.5 — initial shock hits hardest,
        aftershocks taper.
      * **Eau** (flood / tsunami): 1.4 → 0.6 — surge peak then recede.
      * **Air** (storm): 1.3 → 0.7 — hit-and-leave; the front passes.

    Catastrophes outside this map fall back to the historical flat 1.0
    so unknown elements behave like the pre-refinement uniform rate.
    """
    state = max(0.0, min(1.0, state))
    if element == "Vie":
        return 0.4 + 1.2 * state
    if element == "Feu":
        return 0.6 + 0.8 * state
    if element == "Terre":
        return 1.5 - 1.0 * state
    if element == "Eau":
        return 1.4 - 0.8 * state
    if element == "Air":
        return 1.3 - 0.6 * state
    return 1.0


def _great_circle_distance(
    p1: tuple[float, float], p2: tuple[float, float],
) -> float:
    """Great-circle distance in degrees of arc between two ``(lon, lat)`` points.

    Haversine formula. Replaces Euclidean ``hypot`` over (lon, lat) for
    spread-distance calculations — fixes the antimeridian wrap (RUS↔USA
    via the Pacific reads as 250° Euclidean, 80° great-circle) and the
    high-latitude longitude-compression error. For typical
    same-hemisphere mid-latitude pairs the two metrics agree within
    a few percent, so the change is balance-neutral on normal spread
    events.
    """
    lon1, lat1 = p1
    lon2, lat2 = p2
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat * 0.5) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon * 0.5) ** 2
    )
    # ``a`` can drift slightly above 1 from float rounding on antipodal
    # pairs — clamp before asin to avoid a ValueError there.
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(a))))

# Visual ring buffer for spread arcs.
EDGE_BUFFER = 14  # cap on simultaneous spread arcs on screen (was 32)

# Rolling window of per-turn global statistics shown in the right-panel chart.
STATS_HISTORY_LEN = 60

# Auto-advance: how many frames between turns at each non-paused speed (assumes 60fps).
# Tightened progressively — original {120, 60, 30} → {70, 35, 16} → {45, 22, 10}.
# Speed 1 is now ~0.75s/turn, speed 3 ~0.17s/turn so the simulation feels alive.
SPEED_FRAMES_PER_TURN: dict[int, int] = {1: 45, 2: 22, 3: 10}
DEFAULT_SPEED = 1
MAX_SPEED = 3


@dataclass
class SpreadEdge:
    source_id: str
    target_id: str
    age: int = 0
    lifetime: int = EDGE_LIFETIME_FRAMES


FLOATER_LIFETIME_FRAMES = 28  # was 40
FLOATER_BUFFER = 24

FLASH_LIFETIME_FRAMES = 1   # Effectively retired. The "FOYER INITIAL"
                            # banner over the just-picked country was dead
                            # time — the player already knew where they
                            # focused from the picker step. Keeping the
                            # field at 1 frame so existing code paths
                            # don't crash; the loading bridge below now
                            # carries the entire picker→playing transition.

# 180 frames = 3 s at 60 fps. The milestone banner is the only central
# notification surface (side event cards retired). 3 s is long enough
# to glance the wrapped title (≤ 2 lines) but short enough that stacks
# don't pile up during cascade events. Players who want to dismiss
# faster have the × close button; players who want longer can ignore
# the banner and read off the news ticker.
MILESTONE_LIFETIME_FRAMES = 180
# Minimum turns between two consecutive milestone banners — caps how
# often the central notification interrupts the player. Suppressed
# events are *not* lost: they still appear on the news ticker. Tuned
# so a cascade of 20 countries crossing critical in 30 turns shows
# ~10 banners instead of 20.
BANNER_COOLDOWN_TURNS = 2
MILESTONE_BUFFER = 4

IMPACT_CARD_LIFETIME_FRAMES = 120  # 2s @60fps (was 180)


@dataclass
class FloatingText:
    text: str
    world_position: tuple[float, float]
    color: tuple[int, int, int]
    age: int = 0
    lifetime: int = FLOATER_LIFETIME_FRAMES


@dataclass
class FlashMessage:
    text: str
    subtitle: str
    color: tuple[int, int, int]
    age: int = 0
    lifetime: int = FLASH_LIFETIME_FRAMES


@dataclass
class MilestoneBanner:
    """Central auto-fading notification — the only on-screen notification
    surface for in-game events now that the corner cards are retired.

    ``severity`` styles the banner: ``"trophy"`` for unlocked milestones,
    ``"warning"`` for country-critical events, ``"critical"`` for
    collapses / large-scale moments. The renderer maps each to an accent
    colour + tag label.

    ``country_id`` makes the banner *clickable*: when set, clicking the
    banner body (anywhere except the × close button) calls
    ``select_country(country_id)`` so the player can jump to the
    affected country's info panel. The flag was previously a dead
    parameter on ``push_event_card`` — the old corner-card system
    consumed it, the migration to the central banner left it silently
    dropped. Now it threads through to the banner and the input
    handler honours it.
    """
    title: str
    severity: str = "trophy"  # trophy / warning / critical
    age: int = 0
    lifetime: int = MILESTONE_LIFETIME_FRAMES
    country_id: str | None = None


# NB: ``EventCard`` and the ``event_cards`` deque are gone — the top-right
# stacked-card notification system was retired in favour of the central
# milestone banner. ``push_event_card`` (kept for callers) now routes
# content through ``milestone_banners`` instead. Constants / dataclass /
# field / aging loop removed along with their orphan renderer
# (``_draw_event_cards`` + ``event_card_rects``) — no callers, no
# rendering path, just disk weight.

# Skill-cost multiplier applied at purchase time. > 1.0 makes the tree
# more expensive. Round-after-round bump: 1.30 → 1.85 → 2.50. The 1.85
# tier was still pairing with a generous orb value (35), letting an
# engaged mid-game pick up 3-4 skills per orb. With orbs now paying
# 12-81 ÉN at NORMAL, a 2.50 multiplier turns the 5-ÉN tier-1 skills
# into 13 effective, the 10-ÉN tier-2 into 25, and the 15-ÉN tier-3
# into 38 — a median orb (≈ 20 ÉN) buys exactly one mid-tier upgrade,
# a high-state orb pays for one top-tier, and the player has to *plan*
# which axis to invest in instead of bulk-buying the whole tree.
SKILL_COST_MULTIPLIER = 2.50

# ÉN granted on first-time completion of a Fondations tier on any axis,
# and subtracted back (capped at 0) when a refund breaks that completion.
# Was two separate ``bonus = 10`` literals in ``_check_axis_synergy`` and
# ``_revoke_synergy_if_broken`` — drift-prone: bumping one without the
# other would either over-pay on apply (instant exploit at +15 / -10)
# or under-pay on revoke (asymmetric refund cycles). Pull to a single
# module constant so any future tuning lands on both paths atomically.
SYNERGY_BONUS = 10  # legacy alias: still the Fondations payout, kept so any
                   # external module still importing the old name keeps
                   # building. New code uses ``_SYNERGY_BONUS_BY_TIER``.

# Per-tier synergy bonus paid out when the player completes every skill
# in a tier of the same axis. Previously only Fondations earned a bonus,
# so once a player had committed to one axis's foundations there was no
# mechanical reward for deepening that axis through Amplification or
# Transformation — players could scatter further purchases across other
# axes at no opportunity cost. Adding scaled bonuses for the two upper
# tiers gives "specialist" play a clear payoff path:
#   * Fondations:    +10 ÉN  on 3 × 5-ÉN baseline = ~27 % rebate
#   * Amplification: +20 ÉN  on 3 × 10-ÉN baseline = ~27 % rebate
#   * Transformation: +30 ÉN on 3 × 15-ÉN baseline = ~27 % rebate
# Each bonus is the same ~27 % completion rebate proportionally, so the
# strategic choice is purely "broad vs. deep", not "which tier has the
# better return on bonus alone". Completing all three tiers of one
# axis yields +60 ÉN total — outpacing the previous +40 ÉN ceiling
# from scattering Fondations across the four axes.
_SYNERGY_BONUS_BY_TIER: dict[str, int] = {
    "Fondations": 10,
    "Amplification": 20,
    "Transformation": 30,
}

# Per-country indicator boost applied to every non-collapsed country on
# each HUMANITÉ skill purchase, and subtracted back on refund. Used by
# both ``_apply_skill_effect`` and ``_unapply_skill_effect``. Was a
# ``boost = 0.04`` local in apply and a bare ``0.04`` literal in
# unapply — drift-prone in the same way ``SYNERGY_BONUS`` was: a
# designer raising the boost to 0.05 in apply while missing the
# unapply path would leave each buy-refund cycle netting a free
# +0.01 indicator bump per non-collapsed country, instant exploit.
# Pulling to one constant keeps the two paths in lockstep so
# buy-refund cycles always net zero (the existing exploit-closure
# invariant).
INDICATOR_BOOST_PER_SKILL = 0.04

# Maps the in-code country attribute name (``country.resilience`` etc.)
# to the JSON's indicator name under ``Impact sur les indicateurs``.
# Used by ``_indicator_boost_for_level`` to pull the per-level
# ``Valeur_de_Base`` weight from the catalog. The JSON uses
# accent-stripped ASCII names; the in-code attributes are short
# slugs. Keep this here (not in skill_catalog) because the mapping is
# game.py's choice of how to translate skill axes to country state.
_INDICATOR_JSON_BY_ATTR: dict[str, str] = {
    "resilience": "Resilience Technologique",
    "stability": "Stabilite Societale",
    "adaptation": "Adaptation Evolutive",
    "regeneration": "Regeneration Ecologique",
}

# Reference Valeur_de_Base from the JSON — the L1 weight that the
# ``INDICATOR_BOOST_PER_SKILL`` constant was originally calibrated
# against. With JSON L1=4 / L2=8 / L3=12, scaling by ``vdb / 4``
# yields L1=1× / L2=2× / L3=3× the base boost — matching the linear
# 5 / 10 / 15 cost progression so each ÉN spent yields the same
# indicator gain regardless of level. Pulled to a constant so a
# future re-tune of either the JSON values or the boost magnitude
# stays internally consistent.
_INDICATOR_VDB_REFERENCE = 4.0

# Per-country indicator damage applied to every non-collapsed country
# when the GAIA player buys a catastrophe skill. Scales with the JSON's
# ``Valeur_de_Base × Facteur_Affinite`` for the axis-matched indicator
# — so different skills carry genuinely different per-indicator
# pressure, reading from the JSON instead of a flat-per-axis bump.
# Half the magnitude of ``INDICATOR_BOOST_PER_SKILL`` because the
# GAIA path *also* mutates catastrophe parameters (base_impact,
# spread_distance_half, jump_chance) on the same purchase — the
# indicator damage is the *additional* pressure, not the only one.
# HUMANITÉ side only mutates one of two things per purchase (dampen
# OR boost), so its single-effect magnitude can run higher without
# becoming overwhelming.
GAIA_INDICATOR_DAMAGE_PER_SKILL = 0.02


# Educational micro-captions used by the news ticker + alert cards.
# Each entry is a brief, real-world impact summary so the player sees why a
# country is in trouble, not just that it is.
_CRITICAL_HINTS: dict[str, str] = {
    "Eau":   "crues, infrastructures côtières submergées",
    "Feu":   "incendies, fumées toxiques, sécheresse",
    # "sismes" was a missing-accent typo — the correct French spelling is
    # "séismes". The hint is surfaced on the news ticker every time a
    # country tips into "zone critique" under Terre, so the typo would
    # surface dozens of times per simulation.
    "Terre": "séismes, glissements de terrain",
    "Air":   "tempêtes, vents extrêmes",
    # "épidémie" → "épidémies" to restore plural parallelism with the
    # other four hints' first nouns (crues / incendies / séismes /
    # tempêtes — all plural, conveying "multiple instances of the
    # phenomenon hitting the country"). Vie was the lone singular
    # outlier and surfaces on the same news ticker on every Vie-
    # catastrophe critical-tip, so the inconsistency repeated as often
    # as the "sismes" typo above used to.
    "Vie":   "épidémies, immunité dépassée",
}

# French display labels for the JSON-id axis names — duplicated from the
# renderer to keep the model independent of pygame imports.
_AXIS_DISPLAY_LABELS: dict[str, str] = {
    "Intensite":         "Intensité",
    "Portee":            "Portée",
    "Duree":             "Durée",
    "Impact Ecologique": "Impact écologique",
}


_COLLAPSE_HINTS: dict[str, str] = {
    # Each entry is the news-ticker tail shown when a country crosses
    # the collapse threshold (state ≥ 1.0). Both Air and Vie used to
    # end in "pertes massives" — when two countries collapsed in the
    # same turn under different catastrophes, the ticker repeated
    # the same boilerplate twice in a row. Varied the second clause
    # so each catastrophe collapse has its own concrete consequence
    # (matches the doc's per-element vocabulary).
    "Eau":   "littoral détruit, exode forcé",
    "Feu":   "écosystèmes calcinés, air irrespirable",
    "Terre": "structures effondrées, sols stériles",
    "Air":   "atmosphère instable, vagues d'évacuation",
    "Vie":   "système sanitaire saturé, transmission incontrôlée",
}

# Educational fact pool per catastrophe — seeded into the news ticker at
# game start so the rolling ticker carries real-world context from turn
# 1, not just an em-dash placeholder until the first event fires. Facts
# are short, French, and cite credible sources where possible (GIEC,
# OMM, USGS, OMS).
_NEWS_EDUCATIONAL_FACTS: dict[str, tuple[str, ...]] = {
    # The picker's ``CATASTROPHE_REFERENCES`` (renderer side) already
    # shows the canonical agency-cited headline fact ("GIEC : +1 m…",
    # "OMM : 2023 a brûlé…", etc.) when the player selects the card.
    # Leading the news ticker with the *same* fact 30 s later was
    # redundant — same pattern as the earlier Eau 230 M duplicate and
    # the Feu pyrocumulonimbus duplicate already noted below. Each
    # element's first NEWS entry has been dropped so the player gets
    # the picker headline once on the briefing screen, then a rotation
    # of three *distinct* facts on the in-game ticker.
    "Eau": (
        "Le delta du Mékong perd ~1,5 km de littoral par an depuis 2010.",
        "Les Pays-Bas protègent 26 % de leur territoire sous le niveau de la mer.",
        "Les zones humides absorbent 20× plus d'eau qu'un sol urbain équivalent.",
    ),
    "Feu": (
        # Doc's signature Feu insight (À RETENIR § p. 192-197): diverse
        # forests as a fire-defence biomechanism. Replaced an earlier
        # pyrocumulonimbus line that itself duplicated LOADING_FACTS
        # Feu gaia — two layers of de-duplication on this entry.
        "Une forêt diverse résiste mieux : essences mélangées limitent flammes et maladies.",
        "Les fumées de feux représentent 5 % des émissions globales annuelles.",
        "Les coupe-feux divisent par 3 la vitesse de propagation d'un incendie.",
    ),
    "Terre": (
        # Doc's signature Terre line (À RETENIR § p. 283-287): the
        # parasismic-design philosophy of "danser avec la secousse".
        # Replaced an earlier "Japon ~1500 séismes / an" that duplicated
        # LOADING_FACTS Terre gaia.
        "Bâtir parasismique, c'est concevoir pour danser avec la secousse — plier sans rompre.",
        "Les normes parasismiques modernes résistent jusqu'à magnitude 8,5.",
        "La liquéfaction transforme un sol saturé en boue lors d'une secousse.",
    ),
    "Air": (
        "Le courant-jet polaire s'affaiblit de 5 km/h par décennie depuis 1979.",
        "Les abris anti-tornade EF5 doivent résister à 320 km/h en rafales.",
        "Un dôme de chaleur a battu +49,6 °C au Canada en 2021.",
    ),
    "Vie": (
        "Une mutation virale émerge environ toutes les ~10⁴ réplications.",
        "Un vaccin à ARN peut être adapté à un nouveau variant en ~100 jours.",
        "Le traçage de contacts réduit le R effectif jusqu'à 50 % en zone dense.",
    ),
}
TUTORIAL_SLIDE_COUNT = 4     # rôle / carte / évolution / objectif
LOADING_BRIDGE_FRAMES = 30   # 0.5 s @60fps. Earlier rounds tried 132 / 90 /
                             # 80 — every one felt sluggish in playtesting
                             # because the player has *already* committed
                             # (clicked LANCER on the picker) and just
                             # wants the simulation to start. 0.5 s is a
                             # quick visual punctuation, not a wait — the
                             # progress bar still completes its arc, the
                             # title still drifts in, but the player is
                             # in the simulation before they notice.

# Educational fact pool, keyed by catastrophe name. One is picked at random
# when the loading bridge starts so repeated runs surface different content.
LOADING_FACTS: dict[str, dict[str, tuple[str, ...]]] = {
    # Each entry is split per side. GAIA facts surface real-world catastrophe
    # phenomena; HUMANITÉ facts surface real environmental / public-health
    # achievements. Sources spot-checked; we keep numbers conservative and
    # cite mechanisms over precise statistics where there's ambiguity.
    "Eau": {
        "gaia": (
            "Le tsunami de Sumatra 2004 a traversé l'océan Indien à ~800 km/h.",
            "Une crue centennale peut isoler 30 % d'une zone habitée en quelques heures.",
            # Doc-anchored (Eau § "le sais-tu ?", line 41-43). Viscerally
            # scaled — translates abstract "flood danger" into something
            # the player's body remembers next time they cross 15 cm of
            # running water.
            "Quinze centimètres d'eau en mouvement font tomber un adulte ; soixante emportent une voiture.",
            "Plus d'un milliard de personnes vivent à moins de 10 m du niveau de la mer.",
            "Les océans absorbent environ 25 % du CO₂ émis chaque année.",
            "La fonte du Groenland contribue à ~25 % de l'élévation des mers.",
            "Le phytoplancton produit près de la moitié de l'oxygène que nous respirons.",
            "Le bassin amazonien rejette ~20 % de l'eau douce mondiale dans les océans.",
            # Was "Une élévation d'un mètre menacerait directement plus de
            # 230 millions de personnes." — that fact was already cited
            # in ``NEWS_EDUCATIONAL_FACTS["Eau"]`` ("GIEC : +1 m d'élévation
            # expose 230 M…"), so the player saw the same statistic twice
            # across sessions (one in the boot news ticker, one in the
            # loading bridge). Replaced with a distinct angle — Himalayan
            # glaciers as the freshwater source for nearly 2 billion
            # people — to add a mountain-glacier dimension the pool was
            # missing (Eau coverage was coast / ocean / Amazon-heavy).
            "Les glaciers de l'Himalaya alimentent en eau douce près de 1,9 milliard de personnes.",
        ),
        "humanite": (
            "Le Bangladesh a divisé par 100 la mortalité de ses cyclones depuis 1970.",
            "Les Pays-Bas protègent par digues et écluses 60 % de leur territoire inondable.",
            "Restaurer des mangroves coûte ~10 × moins cher que construire des digues.",
            "Singapour recycle plus de 40 % de son eau via le programme NEWater.",
            "Les digues mobiles MOSE ont protégé Venise des marées hautes dès 2020.",
            "Les zones humides naturelles absorbent jusqu'à 40 % des excès de pluie locaux.",
            "Le Bangladesh a construit plus de 12 000 abris anti-cycloniques depuis 1991.",
            # Doc-anchored (Eau § "des raisons d'espérer", line 83-86).
            # Modern urban-water concept the player likely hasn't heard
            # named — "ville-éponge" puts a word on a recoverable city.
            "Une ville-éponge laisse la pluie s'infiltrer : noues, toitures végétalisées, chaussées drainantes.",
        ),
    },
    "Feu": {
        "gaia": (
            "Un mégafeu peut générer son propre climat (pyrocumulonimbus).",
            "Les forêts boréales stockent près du tiers du carbone terrestre.",
            "Les feux australiens 2019-2020 ont émis ~715 Mt de CO₂.",
            "Les feux de tourbières peuvent couver pendant des décennies sous terre.",
            "Le black carbon des incendies accélère la fonte des glaces polaires.",
            "Les forêts régénérées continuent de capter du carbone pendant plus d'un siècle.",
            "Un incendie majeur peut décaler la saison des pluies localement.",
            # Doc-anchored (Feu § "le sais-tu ?", line 141-143). Physics
            # fact that reshapes intuition: most people imagine fire
            # spreading downhill from a high source. The opposite is
            # true, and that asymmetry shapes evacuation routes.
            "Le feu monte plus vite qu'il ne descend : sur une pente, il préchauffe la végétation au-dessus.",
        ),
        "humanite": (
            "Le Costa Rica a doublé sa couverture forestière entre 1985 et 2020.",
            "La Grande Muraille Verte africaine vise à reboiser 8 000 km du Sahel.",
            "La Corée du Sud a reboisé la majorité de son territoire après 1953.",
            "Les feux froids des peuples aborigènes brûlent ~70 000 km² par an en Australie.",
            "Un Canadair largue ~6 tonnes d'eau en 12 secondes sur un foyer.",
            "Les satellites détectent désormais un départ de feu en moins de 15 minutes.",
            "Les brûlages dirigés réduisent de 50 à 80 % la sévérité des feux de saison suivante.",
            # Doc-anchored (Feu § "des raisons d'espérer", line 171-173).
            # Names *biodiversity* as a fire defence — a tier most
            # players don't intuit. Pairs with the HUMANITÉ skill tree's
            # "Impact écologique" axis where mixed-species reforestation
            # is a Niveau 2-3 milestone.
            "Une forêt diverse résiste mieux : mélanger les essences limite la propagation des flammes.",
        ),
    },
    "Terre": {
        "gaia": (
            "Le séisme de Sumatra 2004 a raccourci la journée terrestre de ~2,68 µs.",
            "La grande majorité des décès en séisme vient des effondrements de bâtiments.",
            "Le séisme du Chili 1960 (M9,5) reste le plus puissant jamais enregistré.",
            "Le Japon ressent ~1 500 séismes par an, dont une poignée perceptibles partout.",
            "L'éruption du Pinatubo en 1991 a refroidi la planète de ~0,5 °C pendant 2 ans.",
            "Les ondes sismiques traversent la Terre en moins d'une heure.",
            # Doc-anchored (Terre § "le sais-tu ?", line 221-223). Vivid
            # analogy: tectonic motion is at fingernail-growth scale.
            # Reframes "the ground is stable" into "the ground is
            # always moving, just slowly".
            "Les plaques tectoniques avancent à la vitesse où poussent les ongles — quelques cm par an.",
        ),
        "humanite": (
            "Les normes parasismiques réduisent la mortalité d'environ un facteur 10.",
            "Le système japonais EEW envoie l'alerte sismique en ~10 secondes.",
            "Le Chili impose depuis 1985 des normes parmi les plus strictes au monde.",
            "InSAR par satellite mesure les déformations du sol au millimètre près.",
            # Doc-anchored. The source pedagogy's "À RETENIR" for
            # Terre opens on this line: bâtiments parasismiques
            # ne *résistent* pas à la secousse, ils dansent avec
            # elle. Captures the philosophy of coexistence rather
            # than confrontation — same engineering, different
            # mental model.
            "Les bâtiments parasismiques ne résistent pas à la secousse : ils dansent avec elle.",
            "Les pays formant les enfants aux gestes d'urgence divisent par 4 les pertes.",
            # Doc-anchored (Terre § "des raisons d'espérer", line 264-266).
            # Frames reforestation as a *defensive infrastructure* (slope
            # stability) — same trees as the Feu / climate cases but
            # measured here in landslide reduction. Pairs with the
            # HUMANITÉ Terre / Impact écologique tier "Plantes
            # fixatrices" (vetiver, bambou) in the skills catalog.
            "Les racines des arbres tissent un filet vivant qui retient les pentes — reboiser, c'est se protéger.",
        ),
    },
    "Air": {
        "gaia": (
            "Les ouragans de catégorie 5 soufflent à plus de 252 km/h soutenus.",
            "Le typhon Patricia (2015) a culminé à ~345 km/h — record de l'hémisphère ouest.",
            "Le sable du Sahara traverse l'Atlantique jusqu'aux Caraïbes chaque été.",
            "Les tornades EF5 peuvent soulever des wagons de marchandises.",
            "L'élévation des mers amplifie la portée des submersions cycloniques.",
            "Un grand cyclone déplace plus d'énergie qu'un mois de consommation mondiale.",
            # Doc-anchored (Air § "le sais-tu ?", line 331-334). Key
            # correction to the common mental model: people picture
            # hurricanes as wind events, but most cyclone victims are
            # killed by rain and storm surge, not gusts. Reframes which
            # defensive measures actually matter (drainage, levees,
            # evacuation > windbreaks for life safety).
            "La majorité des dégâts d'un cyclone vient de l'eau : pluies torrentielles et onde de tempête.",
        ),
        "humanite": (
            "Cuba évacue régulièrement plus de 2 millions de personnes sans pertes.",
            "La trajectoire des ouragans est désormais prévue à ~200 km près 72 h à l'avance.",
            "L'OMM coordonne 193 services météo nationaux en temps réel.",
            # "Hurricane Hunters" — proper-noun designation of the
            # 53rd Weather Reconnaissance Squadron. Quotes dropped to
            # match the house style for borrowed names (NEWater, MOSE,
            # Canadair, EEW, InSAR) — all rendered unquoted in this
            # same dict. The previous U+2018 / U+2019 marks were also
            # the only two such codepoints in any user-facing
            # string; Inter ships those glyphs but some pygame system-
            # font fallbacks render them as tofu, so removing them
            # eliminates a latent rendering risk in stripped installs.
            "Les Hurricane Hunters américains volent à l'intérieur des cyclones pour mesurer.",
            "Les normes japonaises anti-typhon résistent à des rafales > 200 km/h.",
            "Une haie brise-vent réduit la vitesse du vent au sol de 50 à 75 % sur 10 × sa hauteur.",
            # Doc-anchored (Air § "des raisons d'espérer", line 350-352).
            # Frames building design as a *collaborator* with wind, not
            # an adversary — pairs with the "danser avec elle" Terre
            # line and the EAU "danser" tagline. The aerodynamic-shape
            # angle (Burj Khalifa setbacks, CFD-tuned towers) is in the
            # HUMANITÉ Air / Intensité catalog as "Architecture aéro-
            # dynamique".
            "Une architecture pensée pour le vent le laisse glisser au lieu de le subir.",
        ),
    },
    "Vie": {
        "gaia": (
            "Le R0 grippal est ~1,3 ; la rougeole, l'une des plus contagieuses, atteint 12-18.",
            "L'immunité collective contre une maladie nécessite ~1 − 1/R0 vaccinés.",
            "La peste noire (1346-1353) a tué environ un tiers de l'Europe.",
            # "grippe espagnole" — established historical name; the
            # scare quotes signalled "misnomer" (the 1918 pandemic
            # wasn't actually Spanish — Spain's neutral press just
            # reported on it earlier than belligerent countries did),
            # but that footnote isn't worth a typographic inconsistency
            # in a one-line news ticker. Quotes dropped to match the
            # rest of the file's ASCII-apostrophe-only style.
            "La grippe espagnole (1918-1919) a tué entre 50 et 100 millions de personnes.",
            # Doc-anchored: zoonotic origin of ~60% of human
            # infectious diseases is a cornerstone One-Health stat
            # in the source pedagogy. Surfacing it here pairs with
            # the humanité-side "One Health" sensibilities and shows
            # why mangroves / forests / biodiversity protection
            # matter to public health.
            "Environ 6 maladies infectieuses sur 10 chez l'humain sont d'origine animale (zoonoses).",
            "La vitesse de mutation virale dépend du taux de réplication du pathogène.",
            # Doc-anchored (Vie § "le sais-tu ?", line 420-422). Visceral
            # food-chain insight: each bite of a plate is one in three
            # owed to a pollinator. Reframes "biodiversity loss" as
            # "your dinner shrinks" — closer to the body than the
            # abstract 100-1000× extinction-rate stat.
            "Près d'une bouchée sur trois dans votre assiette existe grâce aux pollinisateurs.",
        ),
        "humanite": (
            "La variole, qui tuait ~30 % des malades, a été éradiquée par la vaccination en 1980.",
            "La poliomyélite a chuté de plus de 99 % depuis le lancement du programme en 1988.",
            "Les vaccins ARNm anti-COVID ont été conçus et autorisés en moins d'un an.",
            # Doc-anchored: this single statistic is the strongest
            # number in the source pedagogy (Vie, "À RETENIR"). The
            # prior "Rwanda 95 %" was specific but read as a country
            # award rather than a planetary scale-of-good achievement.
            "En 50 ans, la vaccination a sauvé environ 154 M de vies — soit six chaque minute.",
            "L'éradication de la polio est documentée comme l'effort de santé mondial le plus rapide.",
            "La séquence d'un virus nouveau est désormais partagée publiquement en moins d'une semaine.",
            # Doc-anchored (Vie § "des raisons d'espérer", line 451-454).
            # Names the One-Health framework explicitly — a concept the
            # source pedagogy builds the entire Vie chapter on. Pairs
            # with the zoonoses fact on the GAIA side: 6/10 human
            # infectious diseases are animal-origin, so protecting
            # ecosystems IS public health.
            "L'approche One Health relie la santé humaine, animale et des écosystèmes — un seul réseau.",
        ),
    },
    # Cross-catastrophe inspirational facts used as fallbacks.
    "_universal": {
        "humanite": (
            "Le Protocole de Montréal (1987) a enrayé la destruction de la couche d'ozone.",
            "L'accord de Paris (2015) engage 196 États à limiter le réchauffement.",
            "Le GIEC synthétise tous les ~7 ans le consensus scientifique mondial sur le climat.",
            "Les énergies renouvelables ont dépassé le charbon dans la production électrique mondiale en 2024.",
        ),
        "gaia": (
            "Près de 90 % des catastrophes naturelles sont aujourd'hui d'origine climatique.",
            "Les pertes économiques liées aux catastrophes ont quadruplé en 40 ans.",
            "La biodiversité décline à un rythme 100 à 1 000 fois supérieur au taux naturel d'extinction.",
        ),
    },
}


@dataclass
class LoadingBridge:
    """500 ms bridge between picker LANCER and gameplay start
    (``LOADING_BRIDGE_FRAMES = 30`` at 60 fps).

    Shows the catastrophe name, a progress bar, and one rotating educational
    fact. When ``age`` reaches ``lifetime``, ``country_id`` is committed via
    ``start_with_country`` and the bridge clears.
    """
    country_id: str
    catastrophe_name: str
    fact: str
    accent: tuple[int, int, int]
    age: int = 0
    lifetime: int = LOADING_BRIDGE_FRAMES


@dataclass
class ImpactCard:
    """Educational pop-up shown when a skill is purchased."""
    skill_name: str
    skill_axis: str
    level: int
    effects: dict[str, str]
    impact_descriptions: dict[str, str]
    accent: tuple[int, int, int]
    age: int = 0
    lifetime: int = IMPACT_CARD_LIFETIME_FRAMES


def _global_dead_fraction(game: "Game") -> float:
    total = sum(c.population for c in game.world.countries.values())
    if total <= 0:
        return 0.0
    dead = sum(c.dead for c in game.world.countries.values())
    return dead / total


def _global_critical_share(game: "Game") -> float:
    """Population-weighted share living in critical-state countries.

    Mirrors the secondary defeat path in ``_check_outcome``: the share
    of *people* (not countries) in regions whose ``state >= 0.5``. Used
    by the defeat-approach milestones so the markers fire on the same
    metric the simulator uses to decide collapse, not on a count of
    polygons (Tuvalu and India would otherwise weigh equally).
    """
    total = sum(c.population for c in game.world.countries.values())
    if total <= 0:
        return 0.0
    critical_pop = sum(
        c.population for c in game.world.countries.values() if c.state >= 0.5
    )
    return critical_pop / total


def _branch_complete(game: "Game") -> bool:
    """An axis is "complete" when every skill in it is owned at level >= 1.

    Was checking ``n.purchased`` on the legacy EvolutionTree nodes,
    which the current flow never sets (the actual flow uses
    ``purchase_skill`` and writes to ``purchased_skills`` instead).
    Now queries the live skill catalog for the active side.
    """
    catalog = getattr(game, "skill_catalog", None)
    if not catalog:
        return False
    cat = catalog.for_catastrophe_side(game.gaia.active.name, game.player_side)
    if cat is None:
        return False
    for axis in cat.axes:
        if all(
            game.purchased_skills.get(skill.id, 0) > 0
            for tier in axis.tiers
            for skill in tier.skills
        ):
            return True
    return False


# (id, title, predicate, severity). Order is the unlock check order; ids
# must be unique. Title text is shown on the central milestone banner —
# French typography applies.
#
# ``severity`` maps to banner chrome:
#   * "trophy"   — player-progress markers (gold accent, celebratory)
#   * "warning"  — early state-change markers, attention without alarm
#   * "critical" — defeat-approach / collapse markers (red, dramatic)
#
# Backfill notes:
#   * Previously every milestone unlocked with the default ``trophy``
#     severity, so "Décimation planétaire : 10 % de pertes" rendered
#     with the same celebratory chrome as "Branche évolutionnaire
#     achevée" — a gold trophy stamp for a mass-casualty event was
#     tonally wrong. Death-count markers now escalate to ``warning``
#     (1 %), ``critical`` (10 % décimation onwards).
#
# Defeat-approach milestones added because between the 10 % dead marker
# and the 65 % defeat threshold (``defeat_mortality_ratio``), a 55-point
# range, the player crossed nothing visible — they walked into defeat
# without the banner system acknowledging the approach. New markers at
# 25 % / 50 % critical share / 60 % dead surface the slope toward the
# end-state with progressively heavier chrome.
#
# Title wording notes:
#   * "décimée" originally meant *one in ten* (Roman army discipline).
#     Using it for "1 % perdu" is etymologically wrong; the 10 % tier
#     now reads "décimation planétaire" where the word is accurate.
#   * "1%" → "1 %" — French typography puts a (non-breaking) space
#     before the percent sign.
#   * "Premier pays critique" → "Première bascule critique" — the
#     country tipped over the 0.5 threshold; the tip is what matters,
#     not the country.
#   * "10 pays en zone critique" — "zone critique" was redundant with
#     "critique"; tightened to "Dix foyers critiques".
# Each milestone tuple now carries a ``favors`` field at the end —
# "gaia" for catastrophe-progress events (good news for the GAIA
# player, bad news for HUMANITÉ), "humanite" for human-recovery events
# (the inverse), "neutral" for player-progress markers that mean the
# same thing to both sides (first skill bought, branch completed).
# ``_check_milestones`` reads this field and flips the displayed
# severity per player side, so a "10 % dead" banner shows as critical-
# red to the HUMANITÉ player (their fight is failing) but as a trophy
# to the GAIA player (their attack is landing). Without this, both
# sides saw identical milestone styling regardless of who benefited —
# the GAIA player kept getting alarm-red banners for events that were
# actually *their wins*, which read as design tonally confused.
MILESTONES: tuple[tuple[str, str, "callable", str, str], ...] = (
    (
        "first_critical",
        "Première bascule critique",
        lambda g: any(c.state >= 0.5 for c in g.world.countries.values()),
        "warning",
        "gaia",
    ),
    (
        "ten_critical",
        "Dix foyers critiques",
        lambda g: sum(1 for c in g.world.countries.values() if c.state >= 0.5) >= 10,
        "warning",
        "gaia",
    ),
    (
        "one_pct_dead",
        "1 % de pertes humaines à l'échelle planétaire",
        lambda g: _global_dead_fraction(g) >= 0.01,
        "warning",
        "gaia",
    ),
    (
        "ten_pct_dead",
        "Décimation planétaire : 10 % de pertes",
        lambda g: _global_dead_fraction(g) >= 0.10,
        "critical",
        "gaia",
    ),
    # ---- Defeat-approach milestones — added to bridge the 10 % → 65 %
    # silent gap. Each marks an unambiguous slope toward the collapse
    # threshold so the player isn't caught off-guard at game-over.
    (
        "quarter_dead",
        "Un quart de pertes humaines",
        lambda g: _global_dead_fraction(g) >= 0.25,
        "critical",
        "gaia",
    ),
    (
        "half_critical_share",
        "Demi-bascule planétaire : un humain sur deux en zone critique",
        lambda g: _global_critical_share(g) >= 0.50,
        "critical",
        "gaia",
    ),
    (
        "collapse_imminent",
        "Effondrement imminent : 60 % de pertes",
        # 5 points before ``defeat_mortality_ratio`` (0.65). A final
        # warning before the simulation closes — gives the player one
        # last frame to read the situation rather than ending cold.
        lambda g: _global_dead_fraction(g) >= 0.60,
        "critical",
        "gaia",
    ),
    (
        "first_evolution",
        "Première évolution déployée",
        # Was `any(n.purchased for n in g.evolution.nodes)` — but the
        # legacy EvolutionTree nodes are never marked purchased
        # (purchase_evolution is dead code, purchase_skill writes to
        # purchased_skills instead). Check the live dict.
        lambda g: any(level > 0 for level in g.purchased_skills.values()),
        "trophy",
        "neutral",
    ),
    (
        "branch_complete",
        "Branche évolutionnaire achevée",
        _branch_complete,
        "trophy",
        "neutral",
    ),
    # ---- Victory-approach milestone — analogue of ``collapse_imminent``
    # on the defeat side: a final checkpoint just before the win
    # threshold so the player can read the situation, not be surprised
    # by the victory.
    #
    # Note on the absent "quarter" / "half" siblings: the equilibrium
    # bar doesn't start at 0 — the population-weighted average of
    # country indicator baselines is roughly 0.55 at session start.
    # Threshold milestones at 0.25 / 0.50 would therefore fire on turn
    # one of a clean session, before the player has done anything,
    # which inverts the "you're making progress" signal they were
    # supposed to carry. Setting them as *deltas* from session start
    # would require milestone state to become stateful (track the
    # initial value), which the predicate-only ``MILESTONES`` shape
    # doesn't accommodate today. So we keep just the one absolute
    # threshold that's reliably above the natural baseline.
    #
    # For the GAIA player this still reads as a *warning* — "humanity
    # is approaching stabilisation, your grip is slipping" — the same
    # way the death-fraction milestones double as "you're losing" cues
    # for the HUMANITÉ player.
    (
        "victory_imminent",
        "Victoire imminente — seuil de stabilisation en vue",
        # 5 points before ``victory_progress_threshold`` (0.75) and
        # well above the ~0.55 session-start baseline, so this fires
        # only when the HUMANITÉ player has actively pushed progress
        # up beyond the typical starting equilibrium — never on turn
        # one. Mirrors the 0.60 → 0.65 gap on the ``collapse_imminent``
        # side: 5 points of warning before the threshold trip.
        lambda g: g.humans.global_progress >= 0.70,
        "trophy",
        "humanite",
    ),
)


class GameOutcome(Enum):
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"


class Phase(Enum):
    """High-level state machine for the run.

    TITLE   — main menu, no map shown
    PICKER  — patient-zero selection (was awaiting_start)
    PLAYING — turns advancing
    OUTRO   — game ended, end-screen reachable (was game_over)
    """

    TITLE = "title"
    PICKER = "picker"
    PLAYING = "playing"
    OUTRO = "outro"


@dataclass(frozen=True)
class _DifficultyTuning:
    label: str
    impact_multiplier: float
    dna_multiplier: float
    spread_multiplier: float


class Difficulty(Enum):
    """Run-wide difficulty presets, locked in at picker time."""

    CASUAL = _DifficultyTuning("FACILE", impact_multiplier=0.7, dna_multiplier=1.5, spread_multiplier=0.85)
    NORMAL = _DifficultyTuning("NORMAL", impact_multiplier=1.0, dna_multiplier=1.0, spread_multiplier=1.0)
    BRUTAL = _DifficultyTuning("BRUTAL", impact_multiplier=1.4, dna_multiplier=0.7, spread_multiplier=1.2)

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def impact_multiplier(self) -> float:
        return self.value.impact_multiplier

    @property
    def dna_multiplier(self) -> float:
        return self.value.dna_multiplier

    @property
    def spread_multiplier(self) -> float:
        return self.value.spread_multiplier


_DIFFICULTY_ORDER = (Difficulty.CASUAL, Difficulty.NORMAL, Difficulty.BRUTAL)


class GameEvent(Enum):
    """Semantic events emitted by Game; consumers (e.g. audio) drain the queue."""
    BUTTON_CLICK = "button_click"
    PATIENT_ZERO = "patient_zero"
    COUNTRY_CRITICAL = "country_critical"
    EVOLUTION_PURCHASED = "evolution_purchased"
    MILESTONE = "milestone"
    VICTORY = "victory"
    DEFEAT = "defeat"


EVENT_BUFFER = 32


@dataclass
class Game:
    config: Config = DEFAULT_CONFIG
    world: World = None  # type: ignore[assignment]
    humans: Humans = None  # type: ignore[assignment]
    gaia: Gaia = None  # type: ignore[assignment]
    turn: int = 0
    outcome: GameOutcome = GameOutcome.IN_PROGRESS
    info_panel_country: str | None = None
    info_panel_visible: bool = False
    selected_point: CatastrophePoint | None = None
    rng: random.Random = None  # type: ignore[assignment]
    news: deque[str] = field(default_factory=lambda: deque(maxlen=NEWS_CAPACITY))
    evolution: EvolutionTree = None  # type: ignore[assignment]
    evolution_open: bool = False
    help_open: bool = False
    pause_menu_open: bool = False
    pause_confirm: str | None = None  # "abandon" / "quit" / None
    settings_open: bool = False
    settings_tab: str = "audio"
    # Accessibility flags — synced from prefs by app.py.
    reduce_motion: bool = False
    disable_flash: bool = False
    high_contrast: bool = False
    spread_edges: deque[SpreadEdge] = field(
        default_factory=lambda: deque(maxlen=EDGE_BUFFER)
    )
    floating_texts: deque[FloatingText] = field(
        default_factory=lambda: deque(maxlen=FLOATER_BUFFER)
    )
    flash: FlashMessage | None = None
    impact_card: ImpactCard | None = None
    loading_bridge: LoadingBridge | None = None
    hovered_country: str | None = None
    unlocked_milestones: set[str] = field(default_factory=set)
    milestone_banners: deque[MilestoneBanner] = field(
        default_factory=lambda: deque(maxlen=MILESTONE_BUFFER)
    )
    # Last turn on which a banner was pushed — used by the rate-limit
    # check in ``push_event_card`` so the central banner can't spam
    # during cascade events. -100 so the first banner of the run
    # always passes regardless of starting turn.
    _last_banner_turn: int = -100
    infected_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=STATS_HISTORY_LEN)
    )
    dead_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=STATS_HISTORY_LEN)
    )
    speed: int = DEFAULT_SPEED
    last_speed: int = DEFAULT_SPEED
    phase: Phase = Phase.PICKER
    restart_to: Phase | None = None
    audio_muted: bool = False
    difficulty: Difficulty = Difficulty.NORMAL
    events: deque["GameEvent"] = field(
        default_factory=lambda: deque(maxlen=EVENT_BUFFER)
    )
    skill_catalog: SkillCatalog = field(default_factory=SkillCatalog)
    # Most-recent run summary loaded from history.json — surfaced on the title.
    # Stored as a plain dict (not RunRecord) to keep this module persistence-agnostic.
    last_run_summary: dict | None = None
    # Per-skill levels purchased from the JSON catalog (1..3 per skill).
    purchased_skills: dict[str, int] = field(default_factory=dict)
    # Currently-displayed axis in the skill tree overlay.
    skill_tree_axis: str = "Intensite"
    # Skill currently selected in the overlay; click commits via detail panel.
    selected_skill_id: str | None = None
    # Patient-zero candidate selected via map click during the picker phase.
    # Click on map sets it; LANCER button confirms by calling start_with_country.
    pending_country: str | None = None
    # Picker is a 4-step wizard:
    #   -1 = choose side (GAIA / HUMANITÉ)
    #    0 = choose catastrophe
    #    1 = choose difficulty
    #    2 = choose origin country.
    # Each step is a distinct sub-screen so the player isn't presented with
    # everything at once.
    picker_step: int = -1
    # Sidebar collapse — when True the right dashboard panel is hidden and
    # the world map expands to fill the freed space. Defaults to True so the
    # player lands on the cinematic map view; toggle via the chevron pill on
    # the right edge or the TAB key when stats are needed.
    sidebar_collapsed: bool = True
    # Country info panel active tab: 0 = bilan, 1 = équilibre, 2 = tendance.
    info_panel_tab: int = 0
    # Skill detail panel active tab: 0 = aperçu, 1 = impacts, 2 = niveaux.
    skill_detail_tab: int = 0
    # Vertical scroll offset (pixels) for the skill detail panel content
    # when the description / impact follow-up doesn't fit in the visible
    # band. Resets to 0 when the selected skill or active tab changes.
    # Clamped by the renderer based on actual content height (it knows
    # the visible area + total content extent after each draw).
    skill_detail_scroll: int = 0
    # Last-rendered content height of the skill detail aperçu tab,
    # written by the renderer at the end of each draw so the next
    # frame's wheel event can clamp the scroll. Read-only outside
    # the renderer.
    skill_detail_content_h: int = 0
    # Visible height of the scrollable region (similar contract to
    # ``skill_detail_content_h``). Renderer writes; input handler reads
    # to compute the max scroll bound.
    skill_detail_visible_h: int = 0
    # Scrollbar track geometry (x, y, w, h) written by the renderer on
    # each frame so the input handler can hit-test clicks and drags
    # without re-computing the panel layout. ``None`` when no scrollbar
    # is currently drawn (content fits in the visible band).
    skill_detail_scrollbar: tuple[int, int, int, int] | None = None
    # Drag state for click-and-drag scrollbar interaction. ``None`` when
    # not dragging; otherwise the mouse y at drag start (used to track
    # the relative move). Drag-start offset is not needed because the
    # interaction is slider-style: scroll = mouse-pos-on-track maps
    # directly to scroll percentage.
    skill_detail_scroll_drag_y: int | None = None
    # Outro recap active tab: 0 = bilan, 1 = impacts, 2 = parcours.
    outro_tab: int = 0
    # Which side the player picks: "gaia" runs the catastrophe (default), or
    # "humanite" runs the countermeasures. Affects outcome framing and the
    # direction skill purchases push the simulation in `_apply_skill_effect`.
    player_side: str = "gaia"
    # Populated by the renderer each frame so the input handler can hit-test
    # leaderboard rows without coupling controller → view.
    leaderboard_rects: list[tuple[str, "object"]] = field(default_factory=list)
    _tick_accumulator: int = 0
    _country_thresholds_hit: set[str] = field(default_factory=set)
    # Tracks which "first-of-class" auto-pause events have already
    # fired. Pure auto-pause flags only: "first_critical",
    # "first_collapse". Synergy-bonus dedup flags live in a separate
    # set below so the two namespaces can't collide as new classes
    # ship.
    auto_paused_classes: set[str] = field(default_factory=set)
    # Tracks which axis-synergy bonuses have already paid out (the
    # "complete the Fondations of one axis → +10 ÉN" reward). Each
    # entry is "<catastrophe>:<axis>" so the same axis can only pay
    # out once per run. Was previously mixed into ``auto_paused_classes``
    # which suggested it controlled the speed/pause state — it
    # doesn't; this is purely a deduplication marker.
    _synergy_bonuses_paid: set[str] = field(default_factory=set)
    # MP4 cinematic currently overlaying the game (None when idle). The name
    # matches an entry in CinematicLibrary (e.g. "intro" / "outro"). When set,
    # the renderer takes over the full surface and the input handler routes
    # clicks/ESC to "skip cinematic" rather than the underlying phase.
    cinematic_playing: str | None = None
    cinematic_started_ms: int = 0
    # Cinematics that have already played in this session (each name plays at
    # most once per run so the player isn't trapped re-watching the same intro
    # after each restart).
    cinematic_played: set[str] = field(default_factory=set)
    # "How to play" tutorial overlay — discrete chip in the top-left of
    # the map opens a 4-slide procedural cinematic. Manual click-through
    # (Suivant / Passer); no auto-advance. Closing returns to PLAYING
    # without affecting simulation state — the slide content is purely
    # explanatory.
    tutorial_open: bool = False
    tutorial_step: int = 0
    # Set True the first time the tutorial is opened so the discreet
    # accent pulse on the button can stop after first use — the chip
    # stays available but no longer glows.
    tutorial_seen: bool = False
    # Player-progression flag used by the midgame cinematic trigger:
    # set True when the player buys their first Transformation-tier
    # skill on any axis. Together with the existing "≥ 50 % critical
    # countries" condition in app.py this gives the cinematic a path
    # that fires on player agency rather than only on passive world
    # state, so heavy skill-tree users (who freeze ticks while the
    # tree is open) still reach the moment.
    _milestone_transformation_reached: bool = False

    def __post_init__(self) -> None:
        self.world = self.world or World()
        self.humans = self.humans or Humans()
        self.gaia = self.gaia or Gaia()
        self.rng = self.rng or random.Random()
        self.evolution = self.evolution or EvolutionTree()
        if not self.news:
            self.news.append("Scénario démarré — observez la bascule planétaire.")

    @classmethod
    def create(
        cls,
        config: Config = DEFAULT_CONFIG,
        geojson_path: Path = ZONES_GEOJSON,
        seed: int | None = None,
        phase: Phase = Phase.PICKER,
        skills_path: Path = SKILLS_JSON,
    ) -> Game:
        rng = random.Random(seed)
        catalog = load_skill_catalog(skills_path)
        game = cls(config=config, rng=rng, phase=phase, skill_catalog=catalog)
        game.world.load_countries(geojson_path, rng=rng)
        return game

    @property
    def awaiting_start(self) -> bool:
        """Phase-derived: True while the player is choosing patient zero."""
        return self.phase is Phase.PICKER

    @property
    def game_over(self) -> bool:
        """Phase-derived: True once the run has concluded."""
        return self.phase is Phase.OUTRO

    def next_turn(self) -> None:
        self.turn += 1
        catastrophe = self.gaia.active
        # Update intensity first so orb spawns + spread both use the
        # *current* intensity for this turn. Was: orbs spawned with
        # intensity from the previous turn's update, then intensity
        # got refreshed, then spread ran with fresh intensity — orb
        # values lagged by one turn. The orb's ``value`` formula
        # reads ``self.intensity`` at spawn time, so leading with the
        # gaia update ties orb income to this turn's actual state of
        # the simulation.
        human_impact = 1.0 - self.humans.global_progress
        self.gaia.update(human_impact)

        catastrophe.update(self.world, self.config.gameplay, self.rng)
        self._apply_spread(catastrophe)

        # Slow indicator drift back toward the baseline in undamaged
        # countries — the recovery path that lets the player reach the
        # victory threshold.
        for country in self.world.countries.values():
            country.regenerate()
        self.humans.update(self.world)
        for country in self.world.countries.values():
            country.snapshot_state()
        self._snapshot_global_stats()
        self._emit_turn_news(catastrophe.name)
        self._check_outcome()
        self._check_milestones()

    def _snapshot_global_stats(self) -> None:
        # Single-pass accumulation. Was three separate ``sum(...)``
        # generators that each walked the country dict — three O(N)
        # passes per turn for the same iteration. One fused loop is
        # equivalent in semantics and a third of the work.
        total_pop = 0
        total_affected = 0
        total_dead = 0
        for c in self.world.countries.values():
            total_pop += c.population
            total_affected += c.affected
            total_dead += c.dead
        if total_pop <= 0:
            return
        self.infected_history.append(total_affected / total_pop)
        self.dead_history.append(total_dead / total_pop)

    def _apply_spread(self, catastrophe: Catastrophe) -> None:
        """Country-to-country spread plus natural progression of infected zones."""
        countries = list(self.world.countries.values())
        if not countries:
            return

        infected = [c for c in countries if c.state >= SPREAD_INFECTED_THRESHOLD]
        impact = (
            catastrophe.base_impact
            * catastrophe.intensity
            * self.difficulty.impact_multiplier
        )

        # Seed: if nothing is infected yet, ignite one random country.
        # The picker normally seeds patient zero before this code runs;
        # this branch is the safety net for runs that somehow reach
        # _apply_spread without a patient-zero set (e.g. very early-game
        # debug states). Routes through ``_random_uninfected`` so the
        # safety-net ignition uses the same population × vulnerability
        # weighting as the long-distance jump target picker, instead of
        # the prior pop-only formula. Without this, a Vie safety-net
        # seed had the same odds of landing on Iceland (low vie
        # vulnerability) as on Bangladesh (high vie vulnerability),
        # which was incoherent with how every other spread target gets
        # picked.
        if not infected:
            seed = self._random_uninfected(countries, catastrophe=catastrophe)
            if seed is None:
                # All countries already past SPREAD_INFECTED_THRESHOLD
                # somehow — nothing meaningful to seed onto. Defensive:
                # this branch is the safety net for a no-infected world,
                # so by construction the helper should always return.
                return
            seed.state = max(seed.state, 0.18)
            seed.recompute_population_impact()
            self.push_news(f"Premier foyer {catastrophe.name} — {seed.name}.")
            return

        # Natural progression — each infected country drifts worse,
        # scaled by:
        #   * defense AND per-country vulnerability (in apply_catastrophe)
        #   * the element-specific progression curve (here) — see
        #     ``_natural_progression_multiplier`` for the shape per
        #     element. Vie / Feu accelerate as state climbs (epidemic
        #     growth, mature fire), Terre / Eau / Air taper after the
        #     initial shock (aftershocks, recession, front passes).
        for country in infected:
            shape = _natural_progression_multiplier(catastrophe.name, country.state)
            # Stability indicator slows natural progression — high
            # societal stability (functioning institutions, trust,
            # social cohesion) buys the population time to organise
            # response before each crisis wave compounds. Previously
            # Stability had no distinct mechanical effect; it only
            # contributed to the ``defense`` average that reduced
            # incoming impact. Now it has its own role: *rate of
            # escalation*, the temporal counterpart to Resilience's
            # *magnitude of damage*. Scaling: stability=0 → 1.0×
            # progression (baseline), stability=1 → 0.7×. The 30 % cap
            # keeps the mechanic from stalling progression entirely on
            # a fully-stable country — escalation still happens, just
            # at a measurably lower per-turn rate.
            stability_slowdown = 1.0 - 0.3 * country.stability
            country.apply_catastrophe(
                impact * SPREAD_NATURAL_FRACTION * shape * stability_slowdown,
                element=catastrophe.name,
            )

        # Spread to neighbors via centroid distance.
        neighbors_k = max(1, catastrophe.spread_neighbors)
        spread_mult = self.difficulty.spread_multiplier
        new_infections: list[tuple[Country, Country]] = []
        for source in infected:
            neighbors = self._nearest_neighbors(source, countries, neighbors_k)
            for target, distance in neighbors:
                # No collapsed-target guard needed — `_nearest_neighbors`
                # already filters at SPREAD_INFECTED_THRESHOLD (0.05),
                # so any country reaching this point has state ≪ 1.0
                # and is a legitimate spread target.
                chance = self._spread_chance(catastrophe, target, distance, spread_mult)
                if self.rng.random() < chance:
                    target.apply_catastrophe(impact, element=catastrophe.name)
                    new_infections.append((source, target))

            # Long-distance jump (e.g., pandemic via air travel). Seeds a real
            # foothold rather than a sub-threshold nudge, so the jumped country
            # immediately becomes a new spread source. The target picker is
            # element-aware so jumps preferentially land where the element
            # can actually take hold (see ``_random_uninfected``).
            if catastrophe.jump_chance > 0.0 and self.rng.random() < catastrophe.jump_chance:
                jump_target = self._random_uninfected(countries, catastrophe=catastrophe)
                if jump_target is not None and jump_target is not source:
                    jump_target.state = max(jump_target.state, 0.12)
                    jump_target.recompute_population_impact()
                    new_infections.append((source, jump_target))

        for source, target in new_infections:
            self.spread_edges.append(SpreadEdge(source_id=source.id, target_id=target.id))

        # Cluster cascade — countries surrounded by critical neighbours
        # take extra damage even without a direct spread event. Runs
        # *after* spread so the surrounded-region count reflects the
        # same turn's spread effects (newly infected neighbours can
        # contribute to a cluster the same turn they cross threshold,
        # not the turn after).
        #
        # Walks every non-collapsed country (not just infected ones):
        # the whole point is that a still-clean country can deteriorate
        # purely from being surrounded. A previously-defended island
        # in a collapsing region now feels the pressure.
        #
        # No spread_edges entries here — cluster damage is ambient
        # regional pressure, not a directed transmission event; the
        # spread-line UI shouldn't suggest one country attacked another.
        for target in countries:
            if target.state >= 1.0:
                continue
            # Compute K nearest by raw distance without the spread-side
            # uninfected filter. ``_nearest_neighbors`` strips anything
            # with ``state >= SPREAD_INFECTED_THRESHOLD`` (0.05) because
            # the spread loop's frontier-expansion semantics ignore
            # already-infected targets — but the cluster cascade needs
            # the *opposite* set: it specifically looks for critical
            # (state ≥ 0.5) neighbours. Routing through
            # ``_nearest_neighbors`` here meant the candidate set was
            # always empty and the cascade could never fire.
            ranked: list[tuple[Country, float]] = []
            for other in countries:
                if other is target:
                    continue
                ranked.append(
                    (other, _great_circle_distance(target.centroid, other.centroid)),
                )
            ranked.sort(key=lambda kv: kv[1])
            neighbours = ranked[:CLUSTER_NEIGHBOURS_LOOKED]
            critical_count = sum(
                1 for n, _dist in neighbours
                if n.state >= CLUSTER_CRITICAL_NEIGHBOUR_STATE
            )
            if critical_count < 3:
                continue
            # Cap on the 4+ bucket — five critical neighbours don't add
            # more pressure than four (the diminishing-returns shape
            # matches the real-world saturation: once every surrounding
            # region is in crisis, marginal extra collapse next door
            # doesn't make things meaningfully worse).
            pressure = CLUSTER_CASCADE_PRESSURE_BY_COUNT.get(
                min(critical_count, 4), 0.40,
            )
            target.apply_catastrophe(
                impact * pressure, element=catastrophe.name,
            )

    def _random_uninfected(
        self,
        countries: list[Country],
        catastrophe: Catastrophe | None = None,
    ) -> Country | None:
        """Population × element-vulnerability weighted random uninfected
        country for jump targets.

        Used by long-distance jumps (pandemic via air travel, storm
        fronts crossing continents). Two-step refinement:

        * Was uniformly random — Tuvalu had the same odds of receiving
          a transcontinental jump as Bangladesh, which doesn't match
          the actual transmission mechanic (air-travel routes are
          heavily skewed toward populous hubs).
        * Was then ``max(1, population)`` only — better, but ignored
          *who's vulnerable to the element doing the jumping*. A Vie
          jump from London weighted Bangladesh and Iceland by population
          alone, even though Bangladesh's high ``vie`` vulnerability
          (density, sanitation) is exactly what makes a pandemic land
          there in real life; the natural-spread pass already uses
          ``vulnerability`` for impact size, so it was incoherent to
          ignore it for target selection.

        Final weight is ``population × clamp(vulnerability, 0.5, 1.7)``.
        The clamp keeps low-vulnerability countries non-zero (an Air
        jump *can* land on Iceland, just less often) and prevents one
        extremely-vulnerable host from monopolising every jump. The
        clamp range mirrors the one in ``_spread_chance`` so the two
        codepaths weight vulnerability consistently. The ``catastrophe``
        argument is keyword-only and optional so legacy tests that
        call this helper without an element-context still work.
        """
        candidates = [c for c in countries if c.state < SPREAD_INFECTED_THRESHOLD]
        if not candidates:
            return None
        element = catastrophe.name if catastrophe is not None else None
        weights: list[float] = []
        for c in candidates:
            pop_w = float(max(1, c.population))
            if element and c.vulnerability:
                vuln = c.vulnerability.get(element, 1.0)
                vuln_w = max(0.5, min(1.7, vuln))
            else:
                vuln_w = 1.0
            weights.append(pop_w * vuln_w)
        total = sum(weights)
        if total <= 0.0:
            # Defensive: pop ≥ 1 and vuln ≥ 0.5 guarantee positive
            # weights, but a zero-population test fixture could
            # otherwise trip this path.
            return self.rng.choice(candidates)
        roll = self.rng.uniform(0, total)
        running = 0.0
        for c, w in zip(candidates, weights):
            running += w
            if roll <= running:
                return c
        return candidates[-1]  # numeric edge-case fallback

    @staticmethod
    def _nearest_neighbors(
        source: Country, countries: list[Country], k: int
    ) -> list[tuple[Country, float]]:
        """K nearest *uninfected* countries to ``source``, by great-circle
        distance between centroids.

        Already-infected neighbours (state ≥ SPREAD_INFECTED_THRESHOLD)
        are excluded so the catastrophe behaves like a frontier-expansion
        model — each turn pushes outward to new ground rather than
        bouncing impact between countries that the natural-progression
        pass already covers. Previously infected neighbours were
        included as candidates, which meant a tight cluster spent its
        spread budget re-hitting itself while uninfected neighbours
        further out went untouched for several turns.

        Distance metric is the haversine great-circle distance (in
        degrees of arc), not raw Euclidean ``hypot`` over lon/lat. The
        Euclidean approximation broke two pathologies:
          * **Antimeridian wrap**: Russia (60° N, 100° E) ↔ Alaska
            (65° N, −150° E) → Euclidean ~250°, great-circle ~80°.
            Pandemics and storm fronts crossing the dateline were
            systematically under-spread relative to physical reality.
          * **High-latitude longitude compression**: 10° of longitude
            at 70° N is much shorter on the ground than 10° at the
            equator, so polar-country pairs read as farther apart than
            they actually are.
        For mid-latitude same-hemisphere pairs the two metrics differ
        by < 5 %, so existing balance is preserved on typical spread
        events; the fix only changes behaviour where the Euclidean
        result was already physically wrong.
        """
        candidates: list[tuple[Country, float]] = []
        for other in countries:
            if other is source:
                continue
            if other.state >= SPREAD_INFECTED_THRESHOLD:
                continue  # natural progression already covers infected.
            distance = _great_circle_distance(source.centroid, other.centroid)
            candidates.append((other, distance))
        candidates.sort(key=lambda kv: kv[1])
        return candidates[:k]

    @staticmethod
    def _spread_chance(
        catastrophe: Catastrophe,
        target: Country,
        distance: float,
        difficulty_multiplier: float = 1.0,
    ) -> float:
        # Defence-as-spread-resistance. Multiplier raised 0.7 → 0.85 so
        # maxed-defence countries actually feel the resistance their
        # indicators are supposed to provide:
        #
        #   defense=0.0  → factor=1.00 (no resistance)
        #   defense=0.5  → factor=0.575 (≈ 42 % reduction; typical mid)
        #   defense=1.0  → factor=0.15  (≈ 85 % reduction; was 0.30)
        #
        # At 0.7 the formula's natural floor was 0.30 — the ``max(0.15,
        # …)`` clamp had been dead code, and a fully-prepared country
        # still caught the catastrophe at 30 % of normal rate, giving
        # the late-game HUMANITÉ build no real "I've turned this
        # around" payoff. 0.85 makes the clamp engage at the natural
        # ceiling (defense=1.0) and pairs the in-game cap with what
        # real-world preparedness achieves: ~85 % reduction in
        # transmission via combined early-warning + infrastructure +
        # governance + ecosystem health.
        defense_factor = max(0.15, 1.0 - target.defense * 0.85)
        half = catastrophe.spread_distance_half or SPREAD_DISTANCE_HALF
        distance_factor = half / (half + distance)
        intensity_factor = min(catastrophe.intensity, 3.0)
        # Per-country vulnerability also tilts spread odds — Bangladesh
        # catches a water disaster faster than Switzerland; the Sahel
        # catches a fire faster than Iceland. Clamped to avoid runaway
        # propagation.
        vuln = target.vulnerability.get(catastrophe.name, 1.0) if target.vulnerability else 1.0
        vuln_factor = max(0.5, min(1.7, vuln))
        chance = (
            SPREAD_BASE_MULT
            * intensity_factor
            * defense_factor
            * distance_factor
            * difficulty_multiplier
            * vuln_factor
        )
        return min(0.65, chance)

    def tick_animations(self) -> None:
        """Per-frame tick: age visuals and drive auto-advance based on speed."""
        for edge in self.spread_edges:
            edge.age += 1
        while self.spread_edges and self.spread_edges[0].age >= self.spread_edges[0].lifetime:
            self.spread_edges.popleft()

        for ft in self.floating_texts:
            ft.age += 1
        while self.floating_texts and self.floating_texts[0].age >= self.floating_texts[0].lifetime:
            self.floating_texts.popleft()

        if self.flash is not None:
            self.flash.age += 1
            if self.flash.age >= self.flash.lifetime:
                self.flash = None

        if self.impact_card is not None:
            self.impact_card.age += 1
            if self.impact_card.age >= self.impact_card.lifetime:
                self.impact_card = None

        # Loading bridge — when it expires, commit the patient-zero choice.
        if self.loading_bridge is not None:
            self.loading_bridge.age += 1
            if self.loading_bridge.age >= self.loading_bridge.lifetime:
                bridge = self.loading_bridge
                self.loading_bridge = None
                self.start_with_country(bridge.country_id)

        for banner in self.milestone_banners:
            banner.age += 1
        # ``popleft``-only would leak when a younger but shorter-lived
        # banner is queued behind an older longer-lived one. With the
        # current trophy=100 / critical=125 spread, the leak window is
        # 0-24 frames (~0.4 s) — invisible because the renderer's
        # alpha envelope clamps at age==lifetime, but the deque
        # accumulates stale entries forever in that pattern. A proper
        # expiration filter sweeps every element so the contract
        # ("banner is removed when its age reaches its own lifetime")
        # holds regardless of insertion order vs lifetime order.
        # Cheap — milestone_banners typically holds 1-3 elements.
        if any(b.age >= b.lifetime for b in self.milestone_banners):
            self.milestone_banners = deque(
                b for b in self.milestone_banners if b.age < b.lifetime
            )

        # Tick gate — any modal that takes the player's focus away from
        # the world map should freeze ``next_turn`` so the simulation
        # doesn't bleed turns while they're reading / watching.
        # Originally only ``evolution_open`` was here; the help modal,
        # the tutorial overlay, and mid-run cinematics (element_*,
        # midgame, point_de_non_retour) all silently advanced the
        # simulation under the overlay. Reproducible at speed 3:
        # press H mid-game and the world degrades several turns
        # before you close the modal.
        #
        # The pause menu and settings overlay don't need explicit
        # gates here — ``open_pause_menu`` calls ``set_speed(0)`` and
        # the settings overlay is only reachable from the pause menu,
        # so the ``speed <= 0`` clause already covers them.
        if (
            self.phase is not Phase.PLAYING
            or self.evolution_open
            or self.tutorial_open
            or self.help_open
            or self.cinematic_playing is not None
            or self.flash is not None
            or self.speed <= 0
        ):
            return
        self._tick_accumulator += 1
        budget = SPEED_FRAMES_PER_TURN.get(self.speed, SPEED_FRAMES_PER_TURN[1])
        if self._tick_accumulator >= budget:
            self._tick_accumulator = 0
            self.next_turn()

    def set_speed(self, speed: int) -> None:
        speed = max(0, min(MAX_SPEED, speed))
        if speed == self.speed:
            return
        if speed > 0:
            self.last_speed = speed
        self.speed = speed
        self._tick_accumulator = 0

    def toggle_pause(self) -> None:
        if self.speed == 0:
            self.set_speed(self.last_speed or DEFAULT_SPEED)
        else:
            self.last_speed = self.speed
            self.set_speed(0)

    def _emit_turn_news(self, catastrophe_name: str) -> None:
        critical_hint = _CRITICAL_HINTS.get(catastrophe_name, "")
        collapse_hint = _COLLAPSE_HINTS.get(catastrophe_name, "")
        crossed_critical = False
        # Track all same-turn threshold-crossers so we can pick the
        # *most populous* for the auto-pause headline rather than
        # whichever happens to be first in dict-iteration order. The
        # auto-pause is a one-shot moment of player attention; it
        # should highlight the most dramatic country, not Andorra
        # because it sorted alphabetically before Bangladesh.
        critical_this_turn: list[Country] = []
        collapsed_this_turn: list[Country] = []
        # Iterate countries population-descending so the *first* banner
        # push in this loop (and thus the one that wins the cooldown
        # slot) is the most populous crosser. Without this, the
        # banner shown to the player was determined by dict-iteration
        # order (alphabetical by ISO code) — Andorra would steal the
        # alert from India if both crossed the same turn. News ticker
        # entries also benefit from leading with the most dramatic.
        ordered_countries = sorted(
            self.world.countries.values(),
            key=lambda c: -c.population,
        )
        for country in ordered_countries:
            # Pre-compute both flags so the critical branch can skip the
            # banner when collapse is also firing this turn (the
            # collapse banner is the more dramatic event and shouldn't
            # have its cooldown slot eaten by the warning).
            just_critical = (
                country.state >= 0.5
                and country.id not in self._country_thresholds_hit
            )
            collapse_key = f"collapsed:{country.id}"
            just_collapsed = (
                country.state >= 1.0
                and collapse_key not in self._country_thresholds_hit
            )
            if just_critical:
                self._country_thresholds_hit.add(country.id)
                crossed_critical = True
                critical_this_turn.append(country)
                ticker = f"{country.name} · {catastrophe_name.upper()} en zone critique"
                if critical_hint:
                    ticker += f" — {critical_hint}"
                self.push_news(ticker + ".")
                # Skip the warning banner when this same country is also
                # collapsing this turn — the collapse banner (critical
                # severity) is what the player should see, and pushing
                # both would just burn the cooldown without showing
                # the more important one.
                if not just_collapsed:
                    card_text = (
                        f"{country.name} · {critical_hint}"
                        if critical_hint else f"{country.name} en zone critique"
                    )
                    self.push_event_card(
                        card_text,
                        severity="warning",
                        country_id=country.id,
                    )
            if just_collapsed:
                self._country_thresholds_hit.add(collapse_key)
                collapsed_this_turn.append(country)
                ticker = f"{country.name} s'effondre"
                if collapse_hint:
                    ticker += f" — {collapse_hint}"
                self.push_news(ticker + ".")
                card_text = (
                    f"{country.name} effondré · {collapse_hint}"
                    if collapse_hint else f"{country.name} s'effondre"
                )
                self.push_event_card(
                    card_text,
                    severity="critical",
                    country_id=country.id,
                )
        # Pick the most populous threshold-crosser as the auto-pause
        # headline. Population is the proxy for "human-scale drama" —
        # India crossing critical matters more to the player than
        # Tuvalu, even if Tuvalu sorted first in the dict. The two
        # lists are built by walking ``ordered_countries`` (sorted
        # population-descending above), so the first entry is already
        # the most populous crosser; no second max-pass needed.
        first_critical_country = (
            critical_this_turn[0].id if critical_this_turn else None
        )
        first_collapse_country = (
            collapsed_this_turn[0].id if collapsed_this_turn else None
        )
        if crossed_critical:
            self.push_event(GameEvent.COUNTRY_CRITICAL)

        # Auto-pause on first-of-class events so the player can absorb them.
        # Each class fires only once per run. Messages name the country
        # so the player isn't left guessing which one triggered the
        # pause — the auto-pause banner is the *only* feedback they
        # get when control yanks away mid-turn, so it should be
        # specific, not generic.
        if (
            first_critical_country is not None
            and "first_critical" not in self.auto_paused_classes
            and self.speed > 0
        ):
            self.auto_paused_classes.add("first_critical")
            crit_country = self.world.countries.get(first_critical_country)
            crit_name = crit_country.name if crit_country else "?"
            self._auto_pause(
                f"{crit_name} en zone critique — Espace pour reprendre."
            )
        if (
            first_collapse_country is not None
            and "first_collapse" not in self.auto_paused_classes
            and self.speed > 0
        ):
            self.auto_paused_classes.add("first_collapse")
            coll_country = self.world.countries.get(first_collapse_country)
            coll_name = coll_country.name if coll_country else "?"
            self._auto_pause(
                f"{coll_name} s'effondre — Espace pour reprendre."
            )

    def _auto_pause(self, message: str, *, with_banner: bool = True) -> None:
        """Pause the simulation and surface a stacked card explaining why.

        Always force=True on the explanation banner — auto-pause is one
        of the few moments where the player is *guaranteed* to notice
        the screen (they just lost control of the speed). Without
        force, the same turn's preceding warning banner has already
        consumed the cooldown slot and the "why" message gets silently
        dropped, leaving the pause unexplained.

        ``with_banner=False`` skips the banner push — used by
        ``_check_milestones`` because it already pushed its own
        milestone banner (with the player-side-translated severity)
        and the auto-pause path would otherwise duplicate that on
        screen with the same title and a near-identical "— Espace…"
        suffix. The other two callers (first_critical_country /
        first_collapse_country in ``_emit_turn_news``) keep the
        default True because they don't pre-push a banner — the
        auto-pause banner is their only feedback surface.
        """
        # Stash the speed so toggle_pause can restore it (set_speed
        # only writes last_speed when going up; we're going down).
        if self.speed > 0:
            self.last_speed = self.speed
        # Route through set_speed for the canonical pause path —
        # it handles tick_accumulator reset and the no-op guard for
        # us. Was inlined as direct assignment, which silently drifted
        # from set_speed's behaviour as that helper evolved.
        self.set_speed(0)
        if with_banner:
            self.push_event_card(message, severity="critical", force=True)
        if self.turn % 5 == 0:
            self.push_news(
                f"Jour {self.turn} : équilibre planétaire à {int(self.humans.global_progress * 100)} %."
            )

    def push_news(self, message: str) -> None:
        self.news.append(message)

    def dismiss_milestone_banner(self, index: int) -> bool:
        """Remove a single milestone banner by its position in the deque.

        Returns True when a banner was actually removed. Used by the
        input handler's × close-button click handling so the player can
        dismiss notifications immediately instead of waiting for the
        auto-fade.
        """
        if not 0 <= index < len(self.milestone_banners):
            return False
        # deque doesn't support __delitem__; rebuild without the target.
        kept = [b for i, b in enumerate(self.milestone_banners) if i != index]
        self.milestone_banners.clear()
        self.milestone_banners.extend(kept)
        return True

    def push_event_card(
        self,
        text: str,
        severity: str = "info",
        country_id: str | None = None,
        *,
        force: bool = False,
    ) -> None:
        """Surface a game event as a central auto-fading banner.

        Used to push to the top-right corner cards as well; that side
        notification surface has been retired so this method now routes
        the same content through ``milestone_banners`` — the central
        auto-fading notification — which gives the player a single place
        to read about important moments. ``severity`` ("info" /
        "warning" / "critical") maps to the banner's visual style.
        """
        # Map event-card severities to milestone-banner severities.
        # "info" → just news ticker (no banner), so the player isn't
        # interrupted for minor updates.
        if severity not in ("warning", "critical"):
            return
        # Rate-limit: at most one banner every BANNER_COOLDOWN_TURNS
        # turns. Suppressed events still surface on the news ticker
        # (pushed earlier by the caller), so no information is lost —
        # the player just isn't interrupted multiple times in a row.
        # Critical events bypass the cooldown by half so two
        # collapses in the same turn can both flash. ``force=True``
        # callers (currently only ``_auto_pause``) bypass the cooldown
        # entirely — when the simulation auto-pauses to surface a
        # first-of-class event, the explanation banner MUST appear
        # even if another banner just fired this turn.
        cooldown = (
            BANNER_COOLDOWN_TURNS // 2 if severity == "critical"
            else BANNER_COOLDOWN_TURNS
        )
        if not force and self.turn - self._last_banner_turn < cooldown:
            return
        self._last_banner_turn = self.turn
        banner_severity = severity
        # Slightly longer lifetime for critical events so they sit
        # on-screen ~5 s instead of the default ~4.
        lifetime = MILESTONE_LIFETIME_FRAMES * (
            5 if severity == "critical" else 4
        ) // 4
        self.milestone_banners.append(
            MilestoneBanner(
                title=text, severity=banner_severity, lifetime=lifetime,
                country_id=country_id,
            )
        )

    def push_event(self, event: "GameEvent") -> None:
        self.events.append(event)

    def _check_outcome(self) -> None:
        if self.humans.global_progress >= self.config.gameplay.victory_threshold:
            self.outcome = GameOutcome.VICTORY
            self.phase = Phase.OUTRO
            self.push_news("Scénario clos : l'équilibre planétaire tient.")
            self.push_event(GameEvent.VICTORY)
            logger.info("Victory: humanity reached balance with Gaia.")
            return
        countries = list(self.world.countries.values())
        # Single-pass accumulation for the three population aggregates
        # the two defeat paths need. Was three separate ``sum(...)``
        # generators walking the country dict — three O(N) passes per
        # check. The critical-population pass below was skipped when
        # primary defeat fired early, but fusing here is still
        # cleaner: same complexity in the common no-defeat case
        # (all three needed), and the early-return path just leaves
        # ``critical_pop`` unread.
        total_population = 0
        total_dead = 0
        critical_pop = 0
        for c in countries:
            total_population += c.population
            total_dead += c.dead
            if c.state >= 0.5:
                critical_pop += c.population
        # Primary defeat — mortality ratio crosses the threshold.
        # End-screen ticker names the actual percentage that just
        # tripped the threshold — "Scénario clos : la planète a
        # basculé." was state-of-the-world but gave the player no
        # concrete number to chew on at game-end. Mortality at the
        # tipping moment is the load-bearing fact of a defeat-by-
        # mortality close: surfacing it pairs the close with the
        # final report's casualty headline.
        if total_population > 0 and total_dead / total_population >= self.config.gameplay.defeat_mortality_ratio:
            self.outcome = GameOutcome.DEFEAT
            self.phase = Phase.OUTRO
            mortality_pct = int(total_dead / total_population * 100)
            self.push_news(
                f"Scénario clos : la planète a basculé — {mortality_pct} % de pertes humaines."
            )
            self.push_event(GameEvent.DEFEAT)
            logger.info(
                "Defeat: mortality reached %d %% of humanity.", mortality_pct,
            )
            return
        # Secondary defeat path — population-weighted critical share.
        # Was a raw country count: Tuvalu (≈10k people) and India
        # (≈1.4 G) each contributed 1 / N_countries to the threshold,
        # so a cascade of 200 small islands plus a handful of mid-size
        # countries could trip the 75 % gate while most of the world's
        # *people* were still safe — a defeat that didn't match the
        # player's lived experience. Now: % of world *population*
        # living in critical-state countries, so the trigger reflects
        # the human toll, not the polygon toll.
        if countries and total_population > 0:
            # ``critical_pop`` was already accumulated in the single-
            # pass loop above.
            critical_share = critical_pop / total_population
            critical_threshold = self.config.gameplay.defeat_critical_share_ratio
            if critical_share >= critical_threshold:
                self.outcome = GameOutcome.DEFEAT
                self.phase = Phase.OUTRO
                # Threshold percentage interpolated from config so the
                # ticker stays accurate if the threshold is re-tuned.
                # "Effondrement systémique" names the mechanism (the
                # tertiary social-collapse trigger that mortality
                # alone hadn't yet driven) so the player reads *why*
                # the simulation just ended, not just that it did.
                self.push_news(
                    f"Effondrement systémique : {int(critical_threshold * 100)} % de la population basculée en zone critique."
                )
                self.push_event(GameEvent.DEFEAT)
                logger.info(
                    "Defeat: %.0f%% of world population in critical state.",
                    critical_share * 100,
                )

    def cycle_catastrophe(self, forward: bool = True) -> None:
        # Catastrophe choice locks in at patient-zero. After PLAYING
        # begins, switching catastrophes mid-run would expose the four
        # inactive ones (whose ``base_impact`` / ``spread_*`` are still
        # at archetype defaults) with the live ``intensity`` and a fresh
        # ``active_points`` queue — effectively a free reset of damage
        # progress. Input handler gates this on ``K_c``, but the public
        # API surface needs the same guarantee for any future caller.
        if not self.awaiting_start:
            return
        if forward:
            self.gaia.next_catastrophe()
        else:
            self.gaia.prev_catastrophe()
        # "Scénario : passage à la catastrophe X." read as stilted
        # screenwriting jargon — the player is *browsing* catastrophes
        # in the picker (cycle, not commit), so naming what they're
        # looking at directly is cleaner doc-voice.
        self.push_news(f"Catastrophe : {self.gaia.active.name}.")

    def request_loading_bridge(self, country_id: str) -> bool:
        """Begin the picker→playing bridge: a short loading card with a fact.

        Duration is ``LOADING_BRIDGE_FRAMES / fps`` (~0.5 s at 60 fps).
        ``tick_animations`` advances the bridge each frame; when it
        expires ``start_with_country`` is called automatically.
        """
        if self.phase is not Phase.PICKER:
            return False
        if self.loading_bridge is not None:
            return False
        if country_id not in self.world.countries:
            return False
        cat = self.gaia.active
        side = self.player_side
        # Catastrophe-specific facts first, fall back to universal cross-side
        # facts when the bucket is empty.
        per_cat = LOADING_FACTS.get(cat.name, {})
        facts: tuple[str, ...] = per_cat.get(side, ()) or per_cat.get("gaia", ())
        universal = LOADING_FACTS.get("_universal", {}).get(side, ())
        all_facts = facts + universal
        fact = self.rng.choice(all_facts) if all_facts else ""
        self.loading_bridge = LoadingBridge(
            country_id=country_id,
            catastrophe_name=cat.name,
            fact=fact,
            accent=cat.arc_color,
        )
        return True

    def request_restart(self) -> None:
        """Restart into a fresh patient-zero picker (used by RECOMMENCER)."""
        self.restart_to = Phase.PICKER

    def request_menu(self) -> None:
        """Restart into the title screen."""
        self.restart_to = Phase.TITLE

    def toggle_mute(self) -> None:
        self.audio_muted = not self.audio_muted

    def collect_point(self, point: CatastrophePoint) -> int:
        """Harvest a catastrophe point: bank the ADN and emit a floating text.

        Floating text was a bare "+5" with no unit — ambiguous against
        the rest of the HUD where the same number type carries the
        ``ÉN`` suffix (ÉNERGIE DISPONIBLE counter, AMÉLIORER button
        cost, ÉVOLUTION top-bar pill). The renderer's docstring even
        called the popups "Rising +ÉN" while the actual text omitted
        the unit. Now matches the HUD vocabulary so a collected orb's
        +N value reads as the same currency the player spends.
        """
        value = max(1, round(point.value * self.difficulty.dna_multiplier))
        self.humans.evolution_points += value
        self.gaia.active.remove_point(point)
        self.floating_texts.append(
            FloatingText(
                text=f"+{value} ÉN",
                world_position=point.position,
                color=(120, 220, 130),
            )
        )
        return value

    def cycle_difficulty(self, forward: bool = True) -> None:
        """Cycle the difficulty preset; only meaningful while picking.

        The chosen difficulty's ``impact_multiplier`` /
        ``spread_multiplier`` / ``dna_multiplier`` are read on every
        turn — verified callers are ``_apply_spread`` (impact +
        spread, invoked from ``next_turn``) and ``collect_point``
        (dna). Was documented as ``apply_catastrophe_progress`` which
        doesn't exist anywhere; the doc-reference drifted out of sync
        when that method was renamed to ``_apply_spread``. Cycling
        mid-PLAYING would rebalance the run silently for the
        *remainder* of the simulation — already-applied damage at the
        old setting plus new damage at the new setting yields a
        half-and-half score that doesn't match any preset. The input
        handler gates this on ``K_d``, but the public API surface
        needs the same guarantee.
        """
        if not self.awaiting_start:
            return
        idx = _DIFFICULTY_ORDER.index(self.difficulty)
        step = 1 if forward else -1
        self.difficulty = _DIFFICULTY_ORDER[(idx + step) % len(_DIFFICULTY_ORDER)]

    def start_with_country(self, country_id: str) -> bool:
        """Choose patient zero. Idempotent once the game has started."""
        if self.phase is not Phase.PICKER:
            return False
        country = self.world.countries.get(country_id)
        if country is None:
            return False
        country.state = max(country.state, 0.18)
        country.recompute_population_impact()
        self.phase = Phase.PLAYING
        self.set_speed(DEFAULT_SPEED)
        # Initialize ``humans.global_progress`` from the actual world
        # state *before* the first turn ticks. Was: ``humans`` defaults
        # to ``global_progress = 0.0`` and ``humans.update()`` only ran
        # in ``next_turn`` — so turn 1 computed
        # ``human_impact = 1.0 - 0.0 = 1.0`` and gaia.update gave
        # ``intensity = 3.0`` (the maximum). The catastrophe jumped
        # from baseline to fully-amplified in one turn, then settled
        # to its real value on turn 2 once ``humans.update`` had been
        # called from the previous ``next_turn``. Running it here so
        # turn 1 sees the actual mid-range intensity (~1.8 for typical
        # archetype mix) and the simulation isn't shocked into a
        # max-intensity start.
        self.humans.update(self.world)
        # Seed the news ticker with 3 educational facts about the active
        # catastrophe so the rolling banner carries real-world context
        # from turn 1 — beats showing "—" until the first game event.
        for fact in _NEWS_EDUCATIONAL_FACTS.get(self.gaia.active.name, ())[:3]:
            self.push_news(fact)
        self.push_news(
            f"Premier foyer {self.gaia.active.name} — {country.name}."
        )
        self.push_event(GameEvent.PATIENT_ZERO)
        self.flash = FlashMessage(
            text=self.gaia.active.name.upper(),
            subtitle=f"FOYER INITIAL : {country.name.upper()}",
            color=self.gaia.active.point_color,
        )
        return True

    def select_country(self, country_id: str | None) -> None:
        self.world.selected_country = country_id
        self.info_panel_country = country_id
        self.info_panel_visible = country_id is not None

    def close_info_panel(self) -> None:
        self.info_panel_visible = False

    def toggle_evolution_panel(self) -> None:
        self.evolution_open = not self.evolution_open

    def toggle_help(self) -> None:
        self.help_open = not self.help_open

    # ------------------------------------------------------------- tutorial
    # "How to play" overlay (TUTORIAL_SLIDE_COUNT slides). Reads as four
    # short steps: rôle / carte / évolution / objectif. The overlay
    # never mutates simulation state — it's purely explanatory — so
    # there's no need to pause the speed clock or freeze inputs to the
    # underlying phase. The renderer dims the background and the
    # input handler routes clicks to the modal until it's closed.
    def open_tutorial(self) -> None:
        self.tutorial_open = True
        self.tutorial_step = 0
        self.tutorial_seen = True

    def close_tutorial(self) -> None:
        self.tutorial_open = False
        self.tutorial_step = 0

    def advance_tutorial(self) -> None:
        """Step forward by one slide; close when past the last slide."""
        if not self.tutorial_open:
            return
        self.tutorial_step += 1
        if self.tutorial_step >= TUTORIAL_SLIDE_COUNT:
            self.close_tutorial()

    def open_settings(self) -> None:
        self.settings_open = True

    def close_settings(self) -> None:
        self.settings_open = False

    def open_pause_menu(self) -> None:
        """Open the pause menu and freeze the simulation."""
        if self.phase is not Phase.PLAYING:
            return
        self.pause_menu_open = True
        self.last_speed = self.speed if self.speed > 0 else self.last_speed
        self.speed = 0
        self._tick_accumulator = 0

    def close_pause_menu(self) -> None:
        self.pause_menu_open = False
        self.pause_confirm = None

    def abandon_run(self) -> None:
        """Player chose to abandon — go back to picker."""
        self.pause_menu_open = False
        self.pause_confirm = None
        # "Simulation abandonnée." read as punitive (the player gave
        # up), but the action is just a return to the picker —
        # naming the destination rather than judging the choice fits
        # the doc-voice register the rest of the ticker now speaks.
        self.push_news("Retour au choix de scénario.")
        self.restart_to = Phase.PICKER

    @staticmethod
    def _parse_prereq_part(part: str) -> tuple[str, int]:
        """Pull (skill_name, required_level) out of one prereq fragment.

        Handles the three formats that actually appear in the JSON
        data files:
          * ``Name``                  → level 1
          * ``Name Niveau N``         → level N  (skills_humanite.json)
          * ``Name (Niveau N)``       → level N  (skills.json)

        Compound joins (``A + B``) are split at the caller; this helper
        only sees a single skill expression.
        """
        part = part.strip()
        # Parenthesised form: "Name (Niveau N)".
        if "(" in part and ")" in part:
            name_part = part.split("(", 1)[0].strip()
            inside = part.split("(", 1)[1].rstrip(")")
            level = 1
            for token in inside.split():
                if token.isdigit():
                    level = max(1, int(token))
                    break
            return (name_part, level)
        # Trailing-"Niveau N" form: "Name Niveau N".
        tokens = part.split()
        if (
            len(tokens) >= 2
            and tokens[-1].isdigit()
            and tokens[-2].lower() == "niveau"
        ):
            level = max(1, int(tokens[-1]))
            name = " ".join(tokens[:-2]).strip()
            return (name, level)
        # Bare-name form.
        return (part, 1)

    def is_skill_unlocked(self, skill: "object") -> bool:
        """A skill is unlocked when its JSON ``Prerequis`` is satisfied.

        Supports all formats currently present in the data files:
          * ``Aucun``                                  → always unlocked
          * ``Première Vague``                         → that skill at lvl ≥ 1
          * ``Premières digues Niveau 3``              → lvl ≥ 3 (humanité)
          * ``Première Vague (Niveau 3)``              → lvl ≥ 3 (gaia)
          * ``A (Niveau 2) + B (Niveau 2)``            → both at lvl ≥ 2

        Previously only the parenthesised form was parsed — every one
        of the 40 humanité prereqs (which use the non-parens form) was
        silently failing open, and every compound prereq in skills.json
        was only checking the first half. That let players unlock the
        Amplification + Transformation tiers from turn 1.
        """
        prereq_raw = getattr(skill, "prerequis", "Aucun") or ""
        prereq = prereq_raw.strip()
        if not prereq or prereq.lower() == "aucun":
            return True

        if not self.skill_catalog:
            return True
        cat = self.skill_catalog.for_catastrophe_side(
            self.gaia.active.name, self.player_side,
        )
        if cat is None:
            return True

        # Compound prereqs join requirements with " + ". Every part
        # must be satisfied for the skill to unlock; unknown names
        # fail open per-part so a typo in one data file doesn't lock
        # the entire downstream tree.
        for raw_part in prereq.split("+"):
            name, required_level = self._parse_prereq_part(raw_part)
            if not name:
                continue
            found = False
            for axis in cat.axes:
                for tier in axis.tiers:
                    for candidate in tier.skills:
                        if candidate.name == name:
                            found = True
                            owned = self.purchased_skills.get(candidate.id, 0)
                            if owned < required_level:
                                return False
                            break
                    if found:
                        break
                if found:
                    break
            # If the prereq name didn't match anything in the catalog,
            # treat as a noop (fail-open).
        return True

    def purchase_skill(self, skill_id: str) -> bool:
        """Buy the next level of a JSON-catalog skill.

        Side-effects, all in this single function so the caller stays simple:
          * deducts the level cost from ADN,
          * advances ``purchased_skills[skill_id]`` by one,
          * mutates the active catastrophe's spread params (intensity, range,
            jump chance, base impact) according to which axis the skill belongs to,
          * pushes news + emits ``EVOLUTION_PURCHASED`` event so the audio routes.

        Returns False if the skill can't be bought yet (locked, max level, broke).
        """
        if self.phase is not Phase.PLAYING:
            return False
        if not self.skill_catalog:
            return False
        skill = self.skill_catalog.find_skill(skill_id)
        if skill is None or not skill.levels:
            return False
        # Must belong to the active catastrophe (skill_id starts with the name).
        if not skill_id.startswith(f"{self.gaia.active.name}:"):
            return False
        if not self.is_skill_unlocked(skill):
            return False
        current_level = self.purchased_skills.get(skill_id, 0)
        if current_level >= len(skill.levels):
            return False
        next_level = skill.levels[current_level]
        # Apply the global cost multiplier so the JSON values become a
        # baseline rather than the final price (see SKILL_COST_MULTIPLIER).
        effective_cost = max(1, int(round(next_level.cost * SKILL_COST_MULTIPLIER)))
        if self.humans.evolution_points < effective_cost:
            return False
        # Commit.
        self.humans.evolution_points -= effective_cost
        self.purchased_skills[skill_id] = current_level + 1
        self._apply_skill_effect(skill_id)
        # Educational impact card.
        parts = skill_id.split(":", 3)
        axis_name = parts[1] if len(parts) >= 4 else ""
        tier_name = parts[2] if len(parts) >= 4 else ""
        # Player-progression hook for the midgame cinematic.
        # The trigger in app.py used to be purely world-state
        # ("≥ 50 % of countries critical"). But the skill-tree
        # overlay freezes ``next_turn`` (see ``tick_animations``),
        # so a player who lives in the tree — accumulating ÉN and
        # spending it in bursts — would freeze world state below
        # 50 % and never see the cinematic. Mark the first
        # Transformation-tier purchase as the player's narrative
        # peak so the trigger has an alternative path that's
        # driven by the player's own deepest investment, not the
        # passive simulation arc.
        if tier_name == "Transformation":
            self._milestone_transformation_reached = True
        self.impact_card = ImpactCard(
            skill_name=skill.name,
            skill_axis=axis_name,
            level=current_level + 1,
            effects=dict(next_level.effects),
            impact_descriptions=dict(next_level.impact_descriptions),
            accent=self.gaia.active.arc_color,
        )
        self.push_news(
            f"Évolution : {skill.name} — niveau {current_level + 1}."
        )
        self.push_event(GameEvent.EVOLUTION_PURCHASED)
        self._check_milestones()
        self._check_axis_synergy(skill_id)
        # A Humanité skill purchase boosts indicators on every country
        # → ``humans.update`` already ran in ``_apply_skill_effect`` →
        # ``global_progress`` may now have crossed the victory
        # threshold. Without this outcome check, the player has to
        # wait for the next turn tick to register the win — and if
        # they buy the threshold-crossing skill while paused, the
        # game would sit in PLAYING forever (no tick = no outcome
        # check). Run the check inline so victory fires the instant
        # it's actually achieved.
        self._check_outcome()
        return True

    def _check_axis_synergy(self, skill_id: str) -> None:
        """Fire a synergy bonus when the player completes any tier of an axis.

        Bonus per tier: 10 / 20 / 30 ÉN (Fondations / Amplification /
        Transformation) — see ``_SYNERGY_BONUS_BY_TIER``. Each amount
        is the same proportional rebate (~27 % of that tier's total
        cost), so the strategic shape is "the deeper you commit to one
        axis, the more total bonus" rather than "Fondations is the
        only sweet spot".

        Encourages players to specialise: completing all three tiers of
        one axis yields +60 ÉN against the four-axis breadth ceiling of
        +40 ÉN (= 4 × Fondations).
        """
        if not self.skill_catalog:
            return
        parts = skill_id.split(":", 3)
        if len(parts) < 4:
            return
        cat_name, axis_name, tier_name, _skill = parts
        bonus_amount = _SYNERGY_BONUS_BY_TIER.get(tier_name)
        if bonus_amount is None:
            return
        cat = self.skill_catalog.for_catastrophe_side(cat_name, self.player_side)
        if cat is None:
            return
        axis = cat.axis(axis_name)
        if axis is None or not axis.tiers:
            return
        # Look up the tier by name. Mirrors the apply path's defensive
        # lookup pattern: trusting an index into ``axis.tiers`` would
        # silently misroute if the catalog ever reordered tiers; the
        # named lookup keeps apply and revoke speaking the same tier.
        target_tier = next(
            (t for t in axis.tiers if t.name == tier_name),
            None,
        )
        if target_tier is None:
            return
        all_owned = all(
            self.purchased_skills.get(sk.id, 0) > 0
            for sk in target_tier.skills
        )
        if not all_owned:
            return
        # Tier-scoped flag so each of the three tiers can fire
        # independently. Was ``cat:axis`` (axis-scoped, Fondations-
        # only); migrating to ``cat:axis:tier`` lets every tier track
        # its own state without colliding.
        flag = f"{cat_name}:{axis_name}:{tier_name}"
        if flag in self._synergy_bonuses_paid:
            return
        self._synergy_bonuses_paid.add(flag)
        self.humans.evolution_points += bonus_amount
        verbose_axis = _AXIS_DISPLAY_LABELS.get(axis_name, axis_name)
        # Lowercase plural form of the tier name for the news string:
        # "fondations complètes", "amplifications complètes",
        # "transformations complètes" — reads naturally in French.
        tier_plural = {
            "Fondations": "fondations",
            "Amplification": "amplifications",
            "Transformation": "transformations",
        }.get(tier_name, tier_name.lower())
        self.push_news(
            f"Synergie {verbose_axis} — {tier_plural} complètes, "
            f"+{bonus_amount} ÉN."
        )
        self.push_event(GameEvent.MILESTONE)

    def refund_skill(self, skill_id: str) -> bool:
        """Devolve one level of a purchased skill (Plague-Inc-style undo).

        Returns 70 % of the refunded level's cost back to ÉN, rounded to
        the nearest integer (``max(1, int(round(paid_cost * 0.70)))`` —
        was a truncating ``int(paid_cost * 0.70)`` earlier this session,
        which the docstring still described as "round down"; the
        rounding fix aligned the refund-side with ``purchase_skill``'s
        ``int(round(cost * MULT))`` and the docstring now follows).
        Reverses the catastrophe parameter mutation by reapplying the
        upgrade formula in reverse — practically the math is
        asymmetric, so we just accept some drift; values are hard-
        clamped on application anyway.
        """
        if self.phase is not Phase.PLAYING:
            return False
        current = self.purchased_skills.get(skill_id, 0)
        if current <= 0:
            return False
        skill = self.skill_catalog.find_skill(skill_id) if self.skill_catalog else None
        if skill is None or not skill.levels or current > len(skill.levels):
            return False
        refunded_level = skill.levels[current - 1]
        # Refund 70 % of the actually-paid cost (which includes the
        # global multiplier), not the JSON baseline. Uses the same
        # ``max(1, int(round(...)))`` pattern as ``purchase_skill``'s
        # cost computation — was ``int(paid_cost * 0.70)``, which
        # truncated instead of rounded. At the current 2.50× multiplier
        # a tier-2 skill paid 25 ÉN and the refund target is 17.5: the
        # old code returned 17 (68 %), so the docstring's "70 %" was
        # cumulatively 0.5 ÉN-shy per tier-2 refund and 0.6 per tier-3.
        # Rounding matches the cost side and keeps the player's mental
        # model of the refund accurate. ``max(1, …)`` defends against
        # the degenerate refund=0 case for any future low-cost skill.
        paid_cost = max(1, int(round(refunded_level.cost * SKILL_COST_MULTIPLIER)))
        refund = max(1, int(round(paid_cost * 0.70)))
        self.purchased_skills[skill_id] = current - 1
        if self.purchased_skills[skill_id] == 0:
            del self.purchased_skills[skill_id]
        self.humans.evolution_points += refund
        self._unapply_skill_effect(skill_id)
        # Synergy-bonus integrity check — when this refund breaks a
        # Fondations tier that previously earned its +10 ÉN synergy
        # bonus, revoke the flag *and* subtract the bonus back. Without
        # this, a player could buy 3 Fondations skills (cost 30 ÉN),
        # collect the +10 ÉN synergy, then refund 1 skill (recover
        # +7 ÉN), and walk away with 2 Fondations skills for a net 13 ÉN
        # — cheaper than the 20 ÉN cost of buying 2 directly. The flag
        # locks the bonus forever, but the refund used to leave the
        # commitment broken without taking the reward back.
        #
        # Re-completing Fondations after this revocation re-triggers
        # the bonus cleanly via the existing ``_check_axis_synergy``
        # path (the flag is gone, so the next purchase that completes
        # the tier fires the +10 again).
        self._revoke_synergy_if_broken(skill_id)
        # "Régression" read as deterioration / punishment, but a
        # skill refund is a deliberate strategic step — naming the
        # action ("Annulation") instead of the implication
        # ("regression") matches how the rest of the UI names player
        # choices neutrally. "ÉN" suffix matches the rest of the HUD
        # vocabulary (the previous ⚡ lightning glyph rendered as a
        # tofu box on the fallback Inter weight, and the rest of the
        # economy is already labelled in "ÉN" units).
        self.push_news(
            f"Annulation : {skill.name} (+{refund} ÉN)."
        )
        self.push_event(GameEvent.BUTTON_CLICK)
        return True

    def _revoke_synergy_if_broken(self, refunded_skill_id: str) -> None:
        """Revoke the +10 ÉN axis-synergy bonus when a refund breaks a
        previously-completed Fondations tier.

        Called from ``refund_skill`` after the refund has been applied.
        Reads the now-updated ``purchased_skills`` to decide whether
        the Fondations tier of the affected axis still has every skill
        at level >= 1. If it does (multi-level refunds that only
        dropped levels but not below 1), nothing happens. If it
        doesn't, the flag is discarded and 10 ÉN is subtracted (capped
        at 0 so the player can't end up with negative energy).
        """
        parts = refunded_skill_id.split(":", 3)
        if len(parts) < 4:
            return
        cat_name, axis_name, tier_name, _skill = parts
        bonus_amount = _SYNERGY_BONUS_BY_TIER.get(tier_name)
        if bonus_amount is None:
            return
        flag = f"{cat_name}:{axis_name}:{tier_name}"
        if flag not in self._synergy_bonuses_paid:
            return
        if not self.skill_catalog:
            return
        cat = self.skill_catalog.for_catastrophe_side(cat_name, self.player_side)
        if cat is None:
            return
        axis = cat.axis(axis_name)
        if axis is None or not axis.tiers:
            return
        # Look up the tier by name. Apply and revoke paths must agree
        # on which tier they consider, otherwise a data-layout shift
        # could leave the synergy flag awarded by the apply path but
        # unrevocable here (or vice versa).
        target_tier = next(
            (t for t in axis.tiers if t.name == tier_name),
            None,
        )
        if target_tier is None:
            return
        still_complete = all(
            self.purchased_skills.get(sk.id, 0) > 0
            for sk in target_tier.skills
        )
        if still_complete:
            return
        # Tier is now broken — revoke flag + subtract that tier's bonus
        # so refund cycles can't farm the synergy.
        self._synergy_bonuses_paid.discard(flag)
        self.humans.evolution_points = max(
            0, self.humans.evolution_points - bonus_amount,
        )
        verbose_axis = _AXIS_DISPLAY_LABELS.get(axis_name, axis_name)
        tier_plural = {
            "Fondations": "fondations",
            "Amplification": "amplifications",
            "Transformation": "transformations",
        }.get(tier_name, tier_name.lower())
        self.push_news(
            f"Synergie {verbose_axis} révoquée — {tier_plural} "
            f"incomplètes."
        )

    def _indicator_damage_for_level(
        self, skill_id: str, level: int, attr: str,
    ) -> float:
        """Per-country indicator damage magnitude for a GAIA skill buy.

        Mirrors ``_indicator_boost_for_level`` (HUMANITÉ) but uses both
        the JSON's ``Valeur_de_Base`` *and* ``Facteur_Affinite`` for the
        matched indicator. The GAIA-side JSON has diverse per-skill
        Fa values (0.7 / 0.8 / 0.9 / 1.2) that encode each skill's
        affinity to each indicator — a Tsunami's Fa on Resilience
        Technologique is high (it specifically shatters built
        infrastructure) while its Fa on Stabilité Sociétale is lower
        (people adapt to coastal danger over generations). Folding Fa
        in differentiates "buy Tsunami" from "buy Crue Éclair"
        mechanically, not just narratively.

        Formula: ``GAIA_INDICATOR_DAMAGE_PER_SKILL × (vdb / 4) × fa``.

        Returns 0 when the catalog has no data — i.e. the GAIA path
        keeps its existing catastrophe-parameter mutation but adds no
        bonus indicator damage when the JSON is partial. Never
        regresses a buy to weaker-than-baseline.
        """
        if not self.skill_catalog:
            return 0.0
        skill = self.skill_catalog.find_skill(skill_id)
        if skill is None or level < 1 or level > len(skill.levels):
            return 0.0
        level_data = skill.levels[level - 1]
        json_indicator = _INDICATOR_JSON_BY_ATTR.get(attr)
        if not json_indicator:
            return 0.0
        weight = level_data.indicator_impacts.get(json_indicator)
        if weight is None:
            return 0.0
        vdb, fa = weight
        return (
            GAIA_INDICATOR_DAMAGE_PER_SKILL
            * (vdb / _INDICATOR_VDB_REFERENCE)
            * fa
        )

    def _indicator_boost_for_level(
        self, skill_id: str, level: int, attr: str,
    ) -> float:
        """Per-country indicator boost magnitude for a HUMANITÉ skill buy.

        Reads the JSON's ``Valeur_de_Base`` for the skill+level+
        indicator triple and scales ``INDICATOR_BOOST_PER_SKILL`` by
        ``vdb / 4`` — the reference VdB the constant was originally
        calibrated against. Concretely:

          * Level 1 (VdB=4)  → boost = 0.04 × 1.0 = 0.04  (current)
          * Level 2 (VdB=8)  → boost = 0.04 × 2.0 = 0.08
          * Level 3 (VdB=12) → boost = 0.04 × 3.0 = 0.12

        The linear scaling mirrors the linear cost progression
        (5 / 10 / 15 ÉN per level), so each ÉN spent yields ~0.008
        indicator gain regardless of which level it bought — players
        no longer get less mechanical bang per buck by deepening a
        skill they've already started.

        Returns the flat constant when the catalog has no data for the
        skill or the indicator (legacy installs / partial JSON) so the
        worst case is "as good as the pre-refactor behaviour", never
        regression to weaker.
        """
        if not self.skill_catalog:
            return INDICATOR_BOOST_PER_SKILL
        skill = self.skill_catalog.find_skill(skill_id)
        if skill is None or level < 1 or level > len(skill.levels):
            return INDICATOR_BOOST_PER_SKILL
        level_data = skill.levels[level - 1]
        json_indicator = _INDICATOR_JSON_BY_ATTR.get(attr)
        if not json_indicator:
            return INDICATOR_BOOST_PER_SKILL
        weight = level_data.indicator_impacts.get(json_indicator)
        if weight is None:
            return INDICATOR_BOOST_PER_SKILL
        vdb, _fa = weight
        return INDICATOR_BOOST_PER_SKILL * (vdb / _INDICATOR_VDB_REFERENCE)

    def _unapply_skill_effect(self, skill_id: str) -> None:
        """Inverse of ``_apply_skill_effect`` — best-effort reversal.

        Previously this only knew how to reverse the GAIA-side
        catastrophe mutations (`*= 1.10` → `/= 1.10`). When a Humanité
        player refunded a skill, the same GAIA inverse ran — and since
        the Humanité purchase had *decreased* the catastrophe values
        (`*= 0.90`), the refund's GAIA inverse decreased them again.
        Buy-refund-buy loops drove `base_impact` to its floor for ~30 %
        of the original cost each cycle; the per-country indicator
        boosts were also never rolled back, so cheap-cycle gains
        compounded on Humanité runs.

        Now: branch on ``player_side`` and apply the matching inverse
        for each side, including rolling back the Humanité indicator
        boost on every country.
        """
        cat = self.gaia.active
        parts = skill_id.split(":", 3)
        if len(parts) < 4:
            return
        axis_name = parts[1]
        side = getattr(self, "player_side", "gaia")
        if side == "humanite":
            # Inverse of the Humanité countermeasure mutations.
            attr: str | None = None
            if axis_name == "Intensite":
                cat.base_impact = min(0.06, cat.base_impact / 0.90)
                attr = "resilience"
            elif axis_name == "Portee":
                cat.spread_distance_half = min(80.0, cat.spread_distance_half / 0.90)
                # Mirror the apply-side 50 % chance of -1
                # spread_neighbors with a 50 % chance of +1 here.
                # Independent rolls (apply rolled at purchase time,
                # this rolls at refund time) — in expectation each
                # cycle nets zero spread_neighbors change, killing the
                # buy-refund-buy exploit that "accept the drift" used
                # to leave open (refund cycles paid 30 % cost per
                # cycle for an asymmetric one-way bump that never came
                # back). Variance remains, so an unlucky cycle still
                # gives the player back the right value, but the
                # economic exploit is closed: expected cycle yield is
                # now 0 spread_neighbors at -30 % ÉN cost.
                if self.rng.random() < 0.5:
                    cat.spread_neighbors = min(6, cat.spread_neighbors + 1)
                attr = "stability"
            elif axis_name == "Duree":
                cat.base_impact = min(0.06, cat.base_impact / 0.94)
                # Mirror the apply-side correction: Duree pairs with
                # adaptation per the canonical ``BRANCH_TO_AXIS``
                # mapping. Apply and unapply must agree on the
                # boosted indicator or refund cycles would drift one
                # indicator down and a different one up over time.
                attr = "adaptation"
            elif axis_name == "Impact Ecologique":
                cat.jump_chance = min(0.20, cat.jump_chance + 0.01)
                # Companion swap of the line above; matches the
                # apply-side fix at ``_apply_skill_effect``.
                attr = "regeneration"
            # Roll back the per-country indicator boost so buy-refund
            # cycles can't accumulate free indicator gains. The level
            # being unapplied is the level *just removed* by
            # ``refund_skill`` — by the time we get here,
            # ``purchased_skills[skill_id]`` already holds the post-
            # refund value (or is missing entirely on a refund-to-zero),
            # so the unapplied level is ``current_after_refund + 1``.
            # Same VdB-scaled lookup as the apply path keeps the
            # exploit-closure invariant intact (buy + refund nets zero
            # per-country indicator change, regardless of level).
            # Skip collapsed countries — they were skipped on the way
            # up too, so subtracting here would yank legitimate baseline
            # indicators off uninvolved countries.
            if attr is not None:
                unapplied_level = self.purchased_skills.get(skill_id, 0) + 1
                boost = self._indicator_boost_for_level(
                    skill_id, unapplied_level, attr,
                )
                for country in self.world.countries.values():
                    if country.state >= 1.0:
                        continue
                    current = getattr(country, attr)
                    setattr(
                        country, attr, max(0.0, current - boost),
                    )
                self.humans.update(self.world)
            return
        # GAIA side — inverse of the apply ladder, plus rollback of the
        # per-country indicator damage so refund cycles can't farm a
        # net indicator *gain* on the human population.
        attr: str | None = None
        if axis_name == "Intensite":
            cat.base_impact = max(0.005, cat.base_impact / 1.10)
            attr = "resilience"
        elif axis_name == "Portee":
            cat.spread_distance_half = max(8.0, cat.spread_distance_half / 1.10)
            # Mirror the apply-side 50 % chance of +1 spread_neighbors
            # with an independent 50 % chance of -1 here. Without this,
            # a GAIA player could buy/refund Portee in a loop:
            # apply has a 50 % +1 bump that the inverse never undid,
            # so each cycle paid 30 % of cost for an expected
            # 0.5 spread_neighbors gain (capped at 6). The independent
            # reverse roll makes expected cycle yield = 0 — variance
            # still allows lucky single-cycle gains, but the player
            # loses 30 % ÉN per cycle to chase them, removing the
            # cheap-grind exploit while preserving the dramatic feel
            # of the probabilistic +1 on a clean purchase.
            if self.rng.random() < 0.5:
                cat.spread_neighbors = max(1, cat.spread_neighbors - 1)
            attr = "stability"
        elif axis_name == "Duree":
            cat.base_impact = max(0.005, cat.base_impact / 1.06)
            attr = "adaptation"
        elif axis_name == "Impact Ecologique":
            cat.jump_chance = max(0.0, cat.jump_chance - 0.01)
            attr = "regeneration"
        # Rollback the per-country indicator damage that the apply
        # path inflicted. Reads the same JSON (VdB × Fa) at the level
        # being refunded so apply + refund nets zero per-country
        # indicator change, matching the HUMANITÉ-side exploit-closure
        # invariant. Skip collapsed countries — they were skipped on
        # the apply path too, so adding here would gift baseline
        # indicators back to uninvolved countries.
        if attr is not None:
            unapplied_level = self.purchased_skills.get(skill_id, 0) + 1
            damage = self._indicator_damage_for_level(
                skill_id, unapplied_level, attr,
            )
            if damage > 0:
                for country in self.world.countries.values():
                    if country.state >= 1.0:
                        continue
                    current = getattr(country, attr)
                    setattr(
                        country, attr, min(1.0, current + damage),
                    )
                self.humans.update(self.world)

    def _apply_skill_effect(self, skill_id: str) -> None:
        """Translate a JSON skill into a mechanical mutation on the simulation.

        On GAIA side: the player evolves the catastrophe (each axis bumps a
        different spread parameter).

        On HUMANITÉ side: the same skill is reframed as a *countermeasure*.
        The catastrophe is dampened proportionally, and every country gets a
        small lift on the indicator family that maps to the skill's axis.
        """
        cat = self.gaia.active
        parts = skill_id.split(":", 3)
        if len(parts) < 4:
            return
        axis_name = parts[1]
        side = getattr(self, "player_side", "gaia")
        if side == "humanite":
            # Countermeasures dampen the catastrophe + boost the matching
            # indicator family in every country.
            if axis_name == "Intensite":
                cat.base_impact = max(0.002, cat.base_impact * 0.90)
                attr = "resilience"
            elif axis_name == "Portee":
                cat.spread_distance_half = max(8.0, cat.spread_distance_half * 0.90)
                if self.rng.random() < 0.5:
                    cat.spread_neighbors = max(1, cat.spread_neighbors - 1)
                attr = "stability"
            elif axis_name == "Duree":
                cat.base_impact = max(0.002, cat.base_impact * 0.94)
                # Was ``attr = "regeneration"`` — the
                # ``BRANCH_TO_AXIS`` mapping in evolution.py
                # canonically pairs Duree with adaptation
                # (adaptation lets societies survive prolonged
                # stress, which is what Duree skills target). The
                # game.py side and the renderer-side mapping had
                # the Duree ↔ Impact Ecologique pair swapped, so a
                # HUMANITÉ player buying Duree skills was getting
                # the wrong indicator boost. Critically:
                # ``recompute_population_impact`` reads
                # ``country.adaptation`` for the mortality
                # coefficient, so the bug meant Duree purchases —
                # which players intuit as the "fight long catastrophe"
                # axis — produced no mortality benefit. Now they do.
                attr = "adaptation"
            elif axis_name == "Impact Ecologique":
                cat.jump_chance = max(0.0, cat.jump_chance - 0.01)
                # Companion swap of the line above: Impact Ecologique
                # pairs with regeneration (ecosystem self-repair
                # counters ecological damage). Was ``"adaptation"``.
                attr = "regeneration"
            else:
                attr = None
            if attr is not None:
                # Scale the boost by the JSON's ``Valeur_de_Base`` for
                # the level just purchased so L1/L2/L3 yield 1×/2×/3×
                # the base boost — matching the linear cost progression
                # (5 / 10 / 15) so every ÉN spent yields the same
                # indicator gain regardless of which level you're on.
                # Falls back to ``INDICATOR_BOOST_PER_SKILL`` flat when
                # the catalog is missing data (legacy installs / partial
                # JSON) so we never regress to weaker-than-baseline.
                #
                # ``INDICATOR_BOOST_PER_SKILL`` applied to every non-
                # collapsed country per buy. Collapsed countries
                # (state >= 1.0) decay indicators back toward 0 every
                # turn under sustained damage, so the boost is wasted
                # there within one tick. Worse, it ephemerally lifts
                # ``global_progress`` enough to trigger the inline
                # ``_check_outcome`` in ``purchase_skill`` — gifting
                # unearned victories that wouldn't survive the next
                # turn's tick.
                applied_level = self.purchased_skills.get(skill_id, 1)
                boost = self._indicator_boost_for_level(
                    skill_id, applied_level, attr,
                )
                for country in self.world.countries.values():
                    if country.state >= 1.0:
                        continue
                    current = getattr(country, attr)
                    setattr(
                        country, attr, min(1.0, current + boost),
                    )
                self.humans.update(self.world)
            return
        # GAIA side — catastrophe parameter mutations + per-country
        # indicator damage on the axis-matched indicator. The damage
        # magnitude reads from the JSON's per-skill (VdB × Fa) so
        # different skills hit different indicators with different
        # strength — Tsunami's higher VdB and 1.2 Fa on Resilience
        # makes it a structural-damage powerhouse, while Crue Éclair's
        # smaller weights make it a chip-damage opener. Same axis →
        # indicator mapping as HUMANITÉ for symmetry: the indicator a
        # HUMANITÉ skill of a given axis *boosts* is the same one a
        # GAIA skill of the same axis *damages*.
        attr: str | None = None
        if axis_name == "Intensite":
            cat.base_impact = min(0.06, cat.base_impact * 1.10)
            attr = "resilience"
        elif axis_name == "Portee":
            # Was an ``X = bump if roll else X`` conditional expression
            # — the false branch was a no-op self-assignment. The
            # HUMANITÉ side uses the cleaner ``if roll: X = bump``
            # statement form for the same 50 % probabilistic bump;
            # match it here so both sides of the Portee apply read
            # identically. Semantically unchanged.
            if self.rng.random() < 0.5:
                cat.spread_neighbors = min(6, cat.spread_neighbors + 1)
            cat.spread_distance_half = min(80.0, cat.spread_distance_half * 1.10)
            attr = "stability"
        elif axis_name == "Duree":
            cat.base_impact = min(0.06, cat.base_impact * 1.06)
            attr = "adaptation"
        elif axis_name == "Impact Ecologique":
            cat.jump_chance = min(0.20, cat.jump_chance + 0.01)
            attr = "regeneration"
        if attr is not None:
            applied_level = self.purchased_skills.get(skill_id, 1)
            damage = self._indicator_damage_for_level(
                skill_id, applied_level, attr,
            )
            if damage > 0:
                for country in self.world.countries.values():
                    if country.state >= 1.0:
                        continue
                    current = getattr(country, attr)
                    setattr(
                        country, attr, max(0.0, current - damage),
                    )
                self.humans.update(self.world)

    def _check_milestones(self) -> None:
        # Track whether *this turn* has already auto-paused on a
        # critical milestone, so two milestones crossing on the same
        # tick (e.g. 10 % and 25 % dead during a fast catastrophe
        # burst) don't stack two pause-explanation cards. Existing
        # ``self.speed > 0`` checks elsewhere use the same convention.
        paused_this_check = False
        player_side = getattr(self, "player_side", "humanite")
        for ident, title, predicate, base_severity, favors in MILESTONES:
            if ident in self.unlocked_milestones:
                continue
            try:
                triggered = predicate(self)
            except Exception:  # noqa: BLE001 — defensive; bad predicate must not crash a turn.
                logger.exception("Milestone predicate %s failed", ident)
                self.unlocked_milestones.add(ident)
                continue
            if triggered:
                self.unlocked_milestones.add(ident)
                # Translate the milestone's intrinsic severity into the
                # severity that *this player* should see. The base
                # severity describes the event objectively (a 10 %
                # mortality is intrinsically a "critical" event), but
                # the player's stake in it flips depending on which
                # side they're on. Without this, the GAIA player got
                # alarm-red banners for events that were their *wins*
                # (every spread milestone) and trophy banners for
                # events that meant their *defeat* (victory_imminent),
                # both of which read as tonally confused.
                #
                # Translation rules:
                #   * ``favors == "neutral"`` → keep the base severity.
                #     Player-progress markers (first_evolution,
                #     branch_complete) read the same to both sides.
                #   * ``favors == player_side`` → show as ``trophy``.
                #     Their side is winning at this checkpoint, so the
                #     banner should celebrate.
                #   * ``favors != player_side`` AND base is ``trophy``
                #     → flip to ``warning`` (opponent's victory
                #     approach reads as the player's grip slipping).
                #   * Otherwise → keep the base severity (warning /
                #     critical bad-news events read the same way to
                #     whoever it's bad news for).
                if favors == "neutral":
                    effective_severity = base_severity
                elif favors == player_side:
                    effective_severity = "trophy"
                elif base_severity == "trophy":
                    effective_severity = "warning"
                else:
                    effective_severity = base_severity
                # Use ``effective_severity`` for the banner *and* for
                # the news-ticker prefix so both surfaces tell the
                # same player-side-aware story. The auto-pause check
                # below still keys on ``base_severity == "critical"``
                # because "this is a landscape-changing event" is a
                # property of the event itself, not of who benefits —
                # both sides should pause to read it.
                severity = effective_severity
                # Decide upfront whether this milestone is *also* going
                # to auto-pause, so the banner title can carry the
                # "Espace pour reprendre" hint inline instead of being
                # duplicated by a second banner from ``_auto_pause``.
                # Previously: ``_check_milestones`` pushed banner A
                # with the bare title, then ``_auto_pause`` pushed
                # banner B with title + " — Espace pour reprendre." —
                # both visible at the same time, near-identical text,
                # read as a duplicate notification to the player.
                # Combining the suffix here lets a single banner carry
                # both the event and the resume hint.
                will_auto_pause = (
                    base_severity == "critical"
                    and self.speed > 0
                    and not paused_this_check
                    and ident not in self.auto_paused_classes
                )
                banner_title = (
                    f"{title} — Espace pour reprendre."
                    if will_auto_pause else title
                )
                self.milestone_banners.append(
                    MilestoneBanner(title=banner_title, severity=effective_severity),
                )
                # News-ticker prefix tracks severity so the ticker
                # voice matches the banner's chrome instead of stamping
                # every milestone with the same "Jalon :" register.
                # "Trophée" was the gaming-genre default but several
                # of the milestone titles ("Décimation planétaire",
                # "1 % de pertes humaines") are *grim markers*, not
                # achievements; "Jalon" stays as the neutral synonym
                # for player-progress markers (trophy), while warning
                # and critical milestones speak in matching registers.
                prefix = {
                    "critical": "Bascule",
                    "warning": "Alerte",
                    "trophy": "Jalon",
                }.get(severity, "Jalon")
                self.push_news(f"{prefix} : {title}.")
                self.push_event(GameEvent.MILESTONE)
                # Auto-pause on landscape-changing critical milestones
                # (10 % / 25 % / 50 % / 60 % defeat-approach markers,
                # branch-complete grim-events) so a fast-forwarding
                # player can't miss them. Was: only ``first_critical``
                # and ``first_collapse`` country-events ever auto-paused
                # — once past those two early-game beats, every
                # subsequent collapse milestone fired silently against
                # the speed-3 ticker. The auto-pause class key is the
                # milestone ident itself so each unique critical event
                # pauses at most once per run, and ``paused_this_check``
                # gates same-turn duplicates (two critical milestones
                # crossing on one tick).
                #
                # Keys on ``base_severity`` rather than the player-
                # translated ``effective_severity``: "this is a
                # landscape-changing event" is a property of the event
                # itself, not of who benefits from it. A GAIA player
                # *also* benefits from pausing on "10 % dead" — that's
                # their victory celebration moment — so the auto-pause
                # behaviour should be symmetric across sides.
                if will_auto_pause:
                    self.auto_paused_classes.add(ident)
                    paused_this_check = True
                    # ``with_banner=False`` — the milestone banner above
                    # already carries the title + " — Espace pour
                    # reprendre." suffix, so _auto_pause's own
                    # push_event_card would just be a duplicate.
                    self._auto_pause(
                        f"{title} — Espace pour reprendre.",
                        with_banner=False,
                    )

