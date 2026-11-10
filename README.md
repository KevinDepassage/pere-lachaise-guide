# Père-Lachaise guidé

Visite guidée vocale et géolocalisée de cimetières : choisir une personnalité (ou un circuit), puis suivre les consignes vocales, allée par allée, jusqu'à la tombe.

Site : https://kevindepassage.github.io/pere-lachaise-guide/

Lieux : Père-Lachaise, Montparnasse, Montmartre, Passy, Batignolles (Paris), basilique de Saint-Denis, cimetière de Louyat (Limoges).

## Fonctionnement

- **Liste éditoriale** : personnalités avec notice, repères pour trouver la tombe, division et position (253 au Père-Lachaise), plus une sélection de personnalités pour Montmartre, Passy et Batignolles.
- **Base complète** (`tombes-<id>.json`, Wikidata) : sépultures géolocalisées avec photo, division, personnalité, description et dates ; personnalités dont seule la division est connue, guidées jusqu'au centre de la division (repère « ≈ division ») ; sépultures nommées d'OpenStreetMap. Accessibles par la recherche, les filtres thématiques et le filtre « Base complète ».
- **Guidage par les allées** (`osm-<id>.json`, OpenStreetMap) : itinéraire sur le réseau réel des allées, consignes allée par allée (« Suivre l'avenue Principale sur 120 m, puis tourner à droite, puis aussitôt à gauche dans l'avenue Latérale du Sud »), recalcul en cas d'écart, détection de demi-tour. Mise à jour automatique via l'API Overpass tous les 30 jours quand elle répond.
- **Circuits thématiques** : Incontournables, Musique, Écrivains, Peintres, Femmes remarquables, etc. ; ordre de visite optimisé depuis la position ou l'entrée la plus proche, guidage enchaîné étape par étape.
- **Plan zoomable** : molette, pincement, glisser, boutons + / − / position / vue d'ensemble ; noms des tombes affichés en zoom avant.
- **Notices Wikipédia** : résumé chargé en ligne à l'ouverture d'une fiche (licence CC BY-SA 4.0, avec lien vers l'article).
- **Français / anglais** : interface, consignes vocales et descriptions courtes ; les notes éditoriales restent en français.
- **Précision** : positions GPS lissées (filtre de Kalman), sens de marche déduit du déplacement sans boussole, enceinte OSM pour l'entrée/sortie.
- **Hors connexion** : service worker (`sw.js`), application installable (`manifest.webmanifest`).

## Mettre à jour les données

```
python3 outils/maj_donnees.py            # tous les cimetières
python3 outils/maj_donnees.py pl         # un seul
python3 outils/maj_donnees.py --portes mm   # entrées trouvées dans OSM (pour configurer un nouveau cimetière)
```

Le script interroge l'API OpenStreetMap et Wikidata (sans dépendance externe) et régénère `osm-<id>.json` et `tombes-<id>.json`. La liste éditoriale (`DATA` dans `index.html`) n'est pas modifiée ; les fiches qui y figurent déjà sont écartées des fichiers produits. Wikidata limite parfois le débit : le script espace ses requêtes et patiente si besoin.

## Données

Positions © contributeurs OpenStreetMap (ODbL), base SuperLachaise ; descriptions, dates et liens : Wikidata (CC0) ; photos : Wikimedia Commons (licence propre à chaque photo) ; résumés : Wikipédia (CC BY-SA 4.0) ; coordonnées des portes du Père-Lachaise : paris.fr.
