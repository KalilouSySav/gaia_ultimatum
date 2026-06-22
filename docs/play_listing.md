# Terre Vivante — Play Store listing copy

Paste-ready text for Google Play Console. The game is French-first, so
**French is the default locale**. English is the secondary locale (Play lets
you add per-language translations under *Store presence → Main store listing
→ Manage translations*).

---

## App title

```
Terre Vivante
```
(13 chars — well under the 30-char limit.)

---

## Short description (max 80 chars)

### Français (default)
```
Jeu de stratégie : incarnez Gaïa ou l'Humanité. Une planète vivante à comprendre.
```
(79 chars)

### English
```
Strategy game: play Gaia or Humanity on a living planet. Short, replayable runs.
```
(80 chars)

---

## Full description (max 4000 chars)

### Français (default)

```
Comprendre la planète. S'émerveiller du vivant. Agir.

Terre Vivante est un jeu de stratégie où chaque partie est une courte
expérience de pensée sur la coexistence avec une planète vivante.

JOUEZ DEUX CAMPS

• GAÏA — déclenchez une des cinq catastrophes élémentaires (Eau, Feu,
  Terre, Air, Vie). Réveillez les forces géophysiques que la Terre
  utilise depuis toujours pour rééquilibrer ses cycles.

• HUMANITÉ — déployez les réponses scientifiques que nous connaissons
  déjà : adaptation, atténuation, restauration des écosystèmes,
  coopération internationale. La science n'est pas hypothétique.
  Elle est documentée.

CE QUI REND CHAQUE PARTIE UNIQUE

• Carte du monde réelle, ~250 pays simulés indépendamment.
• Cinq éléments distincts, chacun avec ses mécaniques, ses cinématiques
  et ses arbres de compétences.
• Catastrophes en chaîne : un déséquilibre dans un pays se propage à
  ses voisins selon les conditions géographiques.
• Partie courte (15–30 minutes), conçue pour être rejouée.

UN JEU PENSÉ COMME OUTIL

Terre Vivante n'est pas un jeu militant. C'est un simulateur
narratif : il met côte à côte ce que la Terre fait quand on dépasse
ses seuils, et ce que nous savons faire pour les respecter. Vous
choisissez le camp. Vous voyez les conséquences.

CARACTÉRISTIQUES TECHNIQUES

• 100 % hors-ligne. Aucune connexion internet requise, jamais.
• Aucune collecte de données. Aucune publicité. Aucun tracker.
• Aucune permission sensible demandée.
• Sauvegarde automatique locale.
• Optimisé pour téléphone et tablette en mode paysage.

CRÉDITS

Conçu et développé par Kalilou Sy Savane.
Code source : github.com/KalilouSySav/gaia_ultimatum

CONTACT

Questions, retours, bugs : kalilousavane@gmail.com
```

### English

```
Understand the planet. Marvel at what is alive. Act.

Terre Vivante is a strategy game where every run is a short thought
experiment about coexisting with a living planet.

PLAY BOTH SIDES

• GAIA — unleash one of five elemental catastrophes (Water, Fire,
  Earth, Air, Life). Wake the geophysical forces Earth has always
  used to rebalance its own cycles.

• HUMANITY — deploy the scientific responses we already know:
  adaptation, mitigation, ecosystem restoration, international
  cooperation. The science is not hypothetical. It is documented.

WHAT MAKES EACH RUN UNIQUE

• Real-world map, ~250 countries simulated independently.
• Five distinct elements, each with its own mechanics, cinematics
  and skill trees.
• Chain reactions: a destabilised country spreads to its neighbours
  based on geography.
• Short runs (15–30 minutes), designed to be replayed.

A GAME DESIGNED AS A TOOL

Terre Vivante is not an activist game. It is a narrative simulator:
it places side by side what the Earth does when its thresholds are
exceeded, and what we know how to do to respect them. You choose
the side. You see the consequences.

TECHNICAL DETAILS

• 100% offline. No internet connection ever required.
• No data collection. No ads. No trackers.
• No sensitive permissions requested.
• Automatic local save.
• Optimised for phone and tablet in landscape mode.

CREDITS

Designed and developed by Kalilou Sy Savane.
Source code: github.com/KalilouSySav/gaia_ultimatum

CONTACT

Questions, feedback, bugs: kalilousavane@gmail.com
```

---

## Feature graphic (1024 × 500 PNG, required)

The hardest asset to make. Concept brief if you don't have a designer:

- **Composition**: split the canvas vertically. Left half = a stylised
  Earth view tinted in the Gaia palette (deep blues + earthy greens,
  storm/aurora overlay). Right half = the same Earth but in the
  Humanity palette (warm amber + clean white grid overlay, suggesting
  cooperation/infrastructure).
- **Title block centered**: "Terre Vivante" in a clean sans-serif,
  with the tagline "Comprendre la planète. Agir." underneath in a
  lighter weight.
- **No screenshots, no UI** — Play Store guidelines explicitly forbid
  screenshots / device frames in the feature graphic.
- **Avoid text that goes within 24px of any edge** — Play crops the
  graphic on some surfaces.

Tools that produce a usable result in 30 min if you have no designer:
Canva ("Play Store feature graphic" template), Figma (1024×500 frame),
or Photopea (browser-based, free).

---

## Screenshots (2–8 PNG, 16:9 landscape recommended)

Suggested set to capture from a real device or Android Studio emulator:

1. World map mid-game with a Gaia catastrophe active (orbs visible,
   spread arcs animated).
2. Skill tree / picker screen.
3. Country detail panel open.
4. Mid-game cinematic still (one of the element_*_gaia.mp4 frames).
5. Leaderboard / BILAN MONDIAL panel.
6. End-of-run victory or defeat screen.

Capture at the device's native resolution; Play accepts up to
3840 × 2160. Don't add device frames or marketing text overlays
yourself — Play composes those automatically.

---

## App category + tags

- **Category**: Games → Strategy
- **Tags** (Play picks 5): Strategy, Single Player, Offline, Educational,
  Simulation

---

## Email + website for the listing

- **Developer email**: kalilousavane@gmail.com (already public in PRIVACY.md
  contact section, so reusing it costs nothing).
- **Website**: https://github.com/KalilouSySav/gaia_ultimatum
- **Privacy policy URL**:
  https://kalilousysav.github.io/gaia_ultimatum/privacy.html
  (live after the deploy-web workflow finishes for the privacy.html commit).
