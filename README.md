# Père-Lachaise guidé

Visite guidée vocale et géolocalisée du cimetière du Père-Lachaise (Paris) : choisir une personnalité, puis suivre les consignes vocales jusqu'à sa tombe. Montparnasse, la basilique de Saint-Denis et le cimetière de Louyat (Limoges) sont aussi couverts.

Site : https://kevindepassage.github.io/pere-lachaise-guide/

## Fonctionnement

- **Liste éditoriale** : 253 personnalités au Père-Lachaise, avec notice, repères pour trouver la tombe, division et position.
- **Base complète** : environ 3 000 sépultures géolocalisées supplémentaires au Père-Lachaise (et quelques-unes à Montparnasse), issues de Wikidata, avec photo, division, et pour près de 900 d'entre elles la personnalité inhumée, sa description et ses dates (`tombes-pl.json`, `tombes-mp.json`). S'y ajoutent les sépultures nommées d'OpenStreetMap. Accessibles par la recherche, les filtres thématiques et le filtre « Base complète ».
- **Allées** : le réseau des allées et l'enceinte de chaque cimetière sont livrés avec le site (`osm-pl.json`, `osm-mp.json`, `osm-ly.json`, extraits OpenStreetMap du 10/11/2026). La page tente ensuite une mise à jour via l'API Overpass tous les 30 jours (ou avec « Actualiser ») et garde le résultat dans le stockage local.
- **Guidage par les allées** : quand le réseau des allées est disponible, l'itinéraire suit les chemins réels (algorithme de Dijkstra) et les consignes sont données allée par allée : « Suivre l'avenue Principale sur 120 m, puis tourner à gauche dans le chemin Lebrun », « Dans 30 mètres… », « Quitter l'allée : la sépulture est sur la droite, à 6 m ». L'itinéraire est recalculé en cas d'écart, et un demi-tour est signalé.
- **Repli** : sans réseau ou si OpenStreetMap ne répond pas, la page garde la liste éditoriale et le guidage à vol d'oiseau d'origine.
- **Précision** : positions GPS lissées (filtre de Kalman), sens de marche déduit du déplacement quand la boussole n'est pas disponible, entrée/sortie du cimetière déterminée d'après l'enceinte OpenStreetMap.
- **Sur place** : photo de la sépulture (Wikimedia Commons, via Wikidata) pour la reconnaître, lien vers l'article Wikipédia, suggestion de la tombe suivante la plus proche à l'arrivée.
- **Hors connexion** : un service worker (`sw.js`) garde la page, les polices et les photos déjà vues ; l'application est installable sur l'écran d'accueil (`manifest.webmanifest`).

## Données

Positions des sépultures © contributeurs OpenStreetMap (ODbL), via la base SuperLachaise et l'API Overpass ; descriptions, dates et photos : Wikidata (CC0) et Wikimedia Commons (licences propres à chaque photo) ; coordonnées des portes : paris.fr.
