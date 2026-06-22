"""Evolution tree: DNA-cost upgrades that boost humanity's balance indicators.

Plague-Inc-style: 4 branches (resilience, stability, regeneration, adaptation),
each with 4 tiered nodes. Higher tiers cost more DNA and require the previous
tier in the same branch. Purchasing a node bumps the matching indicator on
every country (capped at 1.0) and emits a news entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Branch = Literal["resilience", "stability", "regeneration", "adaptation"]
BRANCHES: tuple[Branch, ...] = ("resilience", "stability", "regeneration", "adaptation")

BRANCH_LABELS: dict[Branch, str] = {
    "resilience": "RÉSILIENCE TECH.",
    "stability": "STABILITÉ",
    "regeneration": "RÉGÉNÉRATION",
    "adaptation": "ADAPTATION",
}

# Each humanity branch counters one catastrophe axis (matching the keys in
# data/skills.json). The educational caption on each evolution node is sourced
# from the catalog entry for the active catastrophe along this axis.
BRANCH_TO_AXIS: dict[Branch, str] = {
    "resilience": "Intensite",
    "stability": "Portee",
    "regeneration": "Impact Ecologique",
    "adaptation": "Duree",
}

# Indicator name used inside the JSON's "Impact sur les indicateurs" map for
# each branch (without French accents — the JSON omits them on these keys).
BRANCH_TO_INDICATOR: dict[Branch, str] = {
    "resilience": "Resilience Technologique",
    "stability": "Stabilite Societale",
    "regeneration": "Regeneration Ecologique",
    "adaptation": "Adaptation Evolutive",
}


@dataclass
class EvolutionNode:
    id: str
    branch: Branch
    tier: int
    name: str
    description: str
    cost: int
    boost: float
    purchased: bool = False


def _default_nodes() -> list[EvolutionNode]:
    """Four tiers per branch. Cost ramps; boost grows with tier."""
    catalog: dict[Branch, list[tuple[str, str]]] = {
        "resilience": [
            ("Réseaux durcis", "Infrastructures résistantes aux chocs."),
            ("Énergies décentralisées", "Micro-réseaux régionaux."),
            ("IA d'alerte précoce", "Anticipe les pics catastrophiques."),
            ("Bouclier orbital", "Atténue les phénomènes extrêmes."),
        ],
        "stability": [
            ("Coordination ONU", "Réponse internationale unifiée."),
            ("Sécurité alimentaire", "Stocks stratégiques répartis."),
            ("Pacte climatique", "Réduction concertée des émissions."),
            ("Gouvernance planétaire", "Décisions globales rapides."),
        ],
        "regeneration": [
            ("Reforestation massive", "Captation accrue du carbone."),
            ("Restauration océanique", "Récifs et zones humides."),
            ("Biotechnologies vertes", "Sols et écosystèmes réparés."),
            ("Géo-ingénierie douce", "Régulation albédo & cycles."),
        ],
        "adaptation": [
            ("Médecine évolutive", "Réponse rapide aux mutations."),
            ("Génétique adaptative", "Tolérance aux nouveaux stress."),
            ("Habitat modulaire", "Vivre en milieux extrêmes."),
            ("Symbiose Planétaire", "Coopération biosphère/humains."),
        ],
    }
    costs = (10, 25, 60, 140)
    boosts = (0.05, 0.08, 0.12, 0.18)
    nodes: list[EvolutionNode] = []
    for branch, items in catalog.items():
        for tier, (name, desc) in enumerate(items):
            nodes.append(
                EvolutionNode(
                    id=f"{branch}_{tier}",
                    branch=branch,
                    tier=tier,
                    name=name,
                    description=desc,
                    cost=costs[tier],
                    boost=boosts[tier],
                )
            )
    return nodes


@dataclass
class EvolutionTree:
    nodes: list[EvolutionNode] = field(default_factory=_default_nodes)

    def by_branch(self, branch: Branch) -> list[EvolutionNode]:
        return sorted(
            (n for n in self.nodes if n.branch == branch),
            key=lambda n: n.tier,
        )

    def get(self, node_id: str) -> EvolutionNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def is_unlocked(self, node: EvolutionNode) -> bool:
        """A tier-N node requires tier N-1 in the same branch."""
        if node.tier == 0:
            return True
        prev_id = f"{node.branch}_{node.tier - 1}"
        prev = self.get(prev_id)
        return bool(prev and prev.purchased)

    def can_purchase(self, node: EvolutionNode, available_dna: int) -> bool:
        return (
            not node.purchased
            and self.is_unlocked(node)
            and available_dna >= node.cost
        )

    def total_boost(self, branch: Branch) -> float:
        return sum(n.boost for n in self.by_branch(branch) if n.purchased)
