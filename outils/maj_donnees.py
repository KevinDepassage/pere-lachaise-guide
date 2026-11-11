#!/usr/bin/env python3
"""Mise à jour des données du site (sans dépendance externe, Python 3.8+).

Produit, pour chaque cimetière :
  - osm-<id>.json    : enceinte, allées (réseau de guidage) et sépultures nommées d'OpenStreetMap
  - tombes-<id>.json : sépultures et personnalités issues de Wikidata (position exacte, ou centre de la division)

Usage :
  python3 outils/maj_donnees.py               # tous les cimetières
  python3 outils/maj_donnees.py pl mm         # seulement certains
  python3 outils/maj_donnees.py --portes mm   # propose les entrées trouvées dans OSM (pour configurer un cimetière)

Sources : API OpenStreetMap (ODbL) et Wikidata (CC0). La liste éditoriale (DATA dans index.html) n'est pas modifiée :
les fiches déjà présentes dans index.html sont simplement écartées des fichiers produits (pas de doublon).
"""
import gzip, json, math, re, sys, time, unicodedata, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
UA = "PereLachaiseGuideDataTool/1.1 (https://github.com/KevinDepassage/pere-lachaise-guide)"

# id : élément Wikidata du cimetière, emprise OSM (ouest,sud,est,nord), préfixe des noms de photos (pour compacter)
CIMETIERES = {
    "pl": {"q": "Q311", "bbox": "2.3855,48.8570,2.4025,48.8655", "ph": "Père-Lachaise - Division {div} - "},
    "mp": {"q": "Q272208", "bbox": "2.3205,48.8335,2.3355,48.8435"},
    "ly": {"q": None, "bbox": "1.2500,45.8470,1.2700,45.8590"},
    "mm": {"q": "Q746647", "bbox": "2.3255,48.8850,2.3360,48.8905"},
    "pa": {"q": "Q1092107", "bbox": "2.2825,48.8605,2.2880,48.8645"},
    "ba": {"q": "Q2655037", "bbox": "2.3125,48.8955,2.3205,48.9000", "sans_position": True},
}

# ---------------------------------------------------------------- réseau
def get(url, data=None, tries=8, accept="*/*"):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()  # réponse compressée : Wikidata limite fortement les clients qui ne la demandent pas
                return gzip.decompress(body) if r.headers.get("Content-Encoding") == "gzip" else body
        except Exception as e:
            if i == tries - 1: raise
            attente = 5 * (i + 1)
            if getattr(e, "code", None) == 429:  # limitation de débit (Wikidata) : respecter Retry-After
                attente = max(65, int((e.headers or {}).get("Retry-After", "65") or 65))
            print(f"  nouvel essai dans {attente} s :", e); time.sleep(attente)

_dernier = [0.0]
def sparql(q):
    # espacer les appels (politesse envers le service public de Wikidata)
    attente = _dernier[0] + 10 - time.time()
    if attente > 0: time.sleep(attente)
    _dernier[0] = time.time()
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q, "format": "json"})
    return json.loads(get(url, accept="application/sparql-results+json"))["results"]["bindings"]

# ---------------------------------------------------------------- géométrie
def dist(a, b):
    return math.hypot((a[0] - b[0]) * 110574, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))

def in_ring(lat, lon, ring):
    ins = False; j = len(ring) - 1
    for i in range(len(ring)):
        (yi, xi), (yj, xj) = ring[i], ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi: ins = not ins
        j = i
    return ins

def near_ring(p, ring, tol):
    k = 111320 * math.cos(math.radians(p[0]))
    for i in range(1, len(ring)):
        a, b = ring[i - 1], ring[i]
        ax, ay, bx, by = (a[1] - p[1]) * k, (a[0] - p[0]) * 110574, (b[1] - p[1]) * k, (b[0] - p[0]) * 110574
        dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
        u = max(0, min(1, -(ax * dx + ay * dy) / L)) if L else 0
        if math.hypot(ax + u * dx, ay + u * dy) < tol: return True
    return False

def ring_area(r):
    return abs(sum(r[i][1] * r[(i + 1) % len(r)][0] - r[(i + 1) % len(r)][1] * r[i][0] for i in range(len(r))) / 2)

def centroid(r):
    a = cx = cy = 0
    for i in range(len(r)):
        (y0, x0), (y1, x1) = r[i], r[(i + 1) % len(r)]
        f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    if abs(a) < 1e-14: return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))
    return (cy / (3 * a), cx / (3 * a))

def join_rings(segs):
    key = lambda p: f"{p[0]:.7f},{p[1]:.7f}"
    segs = [s for s in segs if s]; rings = []
    while segs:
        ring = list(segs.pop(0)); guard = 0
        while key(ring[0]) != key(ring[-1]) and guard < 800:
            guard += 1; end = key(ring[-1])
            i = next((i for i, s in enumerate(segs) if key(s[0]) == end or key(s[-1]) == end), None)
            if i is None: break
            s = segs.pop(i); ring += s[1:] if key(s[0]) == end else list(reversed(s))[1:]
        if len(ring) > 3: rings.append(ring)
    return rings

r6 = lambda v: round(v, 6)
fold = lambda s: unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower()
STOP = {"famille", "de", "du", "des", "la", "le", "les", "et", "tombe", "sepulture", "chapelle", "monument", "caveau", "famile", "von", "van"}
toks = lambda s: {w for w in re.split(r"[^a-z0-9]+", fold(s)) if len(w) >= 3 and w not in STOP}

# ---------------------------------------------------------------- OpenStreetMap
HW = re.compile(r"^(footway|path|pedestrian|service|track|steps|living_street|residential|unclassified|cycleway|corridor)$")
TOMB_S = {"mausoleum": "chapelle funéraire", "vault": "caveau", "sarcophagus": "sarcophage", "pyramid": "tombeau pyramidal", "columbarium": "case de columbarium",
          "war_grave": "sépulture militaire", "tumulus": "tumulus", "obelisk": "obélisque funéraire", "crypt": "crypte", "cenotaph": "cénotaphe",
          "headstone": "tombe", "table": "tombe", "rock": "rocher funéraire"}

def lire_osm(bbox):
    root = ET.fromstring(get("https://api.openstreetmap.org/api/0.6/map?bbox=" + bbox))
    N, W, R = {}, {}, []
    for e in root:
        t = {x.get("k"): x.get("v") for x in e.findall("tag")}
        if e.tag == "node": N[e.get("id")] = (float(e.get("lat")), float(e.get("lon")), t)
        elif e.tag == "way": W[e.get("id")] = ([n.get("ref") for n in e.findall("nd")], t)
        elif e.tag == "relation": R.append(([(m.get("type"), m.get("ref"), m.get("role")) for m in e.findall("member")], t))
    return N, W, R

def construire_osm(cfg, cem, N, W, R):
    """Équivalent de extBuild() dans index.html."""
    pts = lambda refs: [(N[n][0], N[n][1]) for n in refs if n in N]
    is_cem = lambda t: (t.get("landuse") == "cemetery" or t.get("amenity") == "grave_yard") and not t.get("highway")
    refs = [(t["lat"], t["lon"]) for t in cem["tombs"] if t.get("lat") is not None] + [(cem["lat0"], cem["lon0"])]
    rings_of_way = lambda wid: [pts(W[wid][0])]
    def rings_of_rel(members): return join_rings([pts(W[ref][0]) for ty, ref, role in members if ty == "way" and ref in W and role != "inner"])
    polys = []
    for wid, (nds, t) in W.items():
        if is_cem(t): polys += [r for r in rings_of_way(wid) if any(in_ring(p[0], p[1], r) for p in refs)]
    for members, t in R:
        if is_cem(t): polys += [r for r in rings_of_rel(members) if any(in_ring(p[0], p[1], r) for p in refs)]
    seen = set(); polys = [r for r in polys if not (f"{len(r)}:{r[0]}" in seen or seen.add(f"{len(r)}:{r[0]}"))]
    inside = lambda lat, lon, tol: not polys or any(in_ring(lat, lon, r) or (tol and near_ring((lat, lon), r, tol)) for r in polys)
    sectors = []
    for wid, (nds, t) in W.items():
        if t.get("cemetery") == "sector":
            m = re.search(r"\d+", t.get("ref") or t.get("name") or "")
            if m: sectors.append((str(int(m.group(0))), pts(nds)))
    for members, t in R:
        if t.get("cemetery") == "sector":
            m = re.search(r"\d+", t.get("ref") or t.get("name") or "")
            if m: sectors += [(str(int(m.group(0))), r) for r in rings_of_rel(members)]
    curated = [t for t in cem["tombs"] if t.get("lat") is not None]
    tombs = []
    cands = [("n", nid, la, lo, t) for nid, (la, lo, t) in N.items()]
    for wid, (nds, t) in W.items():
        p = pts(nds)
        if p: cands.append(("w", wid, sum(x[0] for x in p) / len(p), sum(x[1] for x in p) / len(p), t))
    for ty, oid, lat, lon, t in cands:
        if not t.get("name") or is_cem(t) or t.get("highway") or t.get("cemetery") == "sector": continue
        if not (t.get("historic") in ("tomb", "grave", "memorial", "monument") or t.get("cemetery") == "grave"): continue
        if not inside(lat, lon, 10): continue
        if not polys and dist((lat, lon), (cem["lat0"], cem["lon0"])) > 600: continue
        memo = t.get("historic") in ("memorial", "monument"); tk = toks(t["name"])
        if any(dist((k["lat"], k["lon"]), (lat, lon)) < (150 if k.get("pl") else 35) and toks(k["n"]) & tk for k in curated): continue  # plan officiel prioritaire
        if any(k["n"] == t["name"] and dist((k["lat"], k["lon"]), (lat, lon)) < 8 for k in tombs): continue
        div, est = "", False
        sec = next((d for d, r in sectors if in_ring(lat, lon, r)), None)
        if sec: div = sec
        else:
            nb = sorted(((dist((k["lat"], k["lon"]), (lat, lon)), k) for k in curated if k.get("div") and not k.get("est")), key=lambda x: x[0])
            if nb and nb[0][0] < 70: div, est = nb[0][1]["div"], True
        s = t.get("description:fr") or t.get("description") or ((("plaque commémorative" if t.get("memorial") == "plaque" else "monument aux morts" if t.get("memorial") == "war_memorial" else "monument commémoratif")) if memo else TOMB_S.get(t.get("tomb"), "sépulture"))
        o = {"id": "o" + ty + oid, "n": t["name"].strip(), "s": s, "b": "", "d": "", "div": div, "lat": r6(lat), "lon": r6(lon), "c": ["osm", "memo"] if memo else ["osm"], "note": "", "find": "", "x": 1}
        if est: o["est"] = 1
        wd = t.get("subject:wikidata") or t.get("buried:wikidata")
        if wd: o["wd"] = wd.split(";")[0].strip()
        if t.get("wikidata"): o["wg"] = t["wikidata"].split(";")[0].strip()
        tombs.append(o)
    nodes, nix, ways = [], {}, []
    for wid, (nds, t) in W.items():
        if not t.get("highway") or not HW.match(t["highway"]) or t.get("access") in ("private", "no"): continue
        if not polys or not any(n in N and inside(N[n][0], N[n][1], 0) for n in nds): continue
        r = []
        for n in nds:
            if n not in N: continue
            if n not in nix: nix[n] = len(nodes); nodes.append([r6(N[n][0]), r6(N[n][1])])
            r.append(nix[n])
        if len(r) > 1: ways.append({"n": (t.get("name") or "").strip(), "k": t["highway"], "r": r})
    outline = [[r6(a), r6(b)] for a, b in max(polys, key=ring_area)] if polys else None
    ext = {"v": 1, "tombs": tombs, "nodes": nodes, "ways": ways, "outline": outline, "polys": [[[r6(a), r6(b)] for a, b in r] for r in polys], "at": int(time.time() * 1000)}
    centres = {d: centroid(r) for d, r in sectors if len(r) > 3}
    return ext, centres, polys

def portes(N, W, polys):
    """Entrées OSM situées sur l'enceinte (aide à la configuration d'un nouveau cimetière)."""
    streets = [(t.get("name"), [(N[n][0], N[n][1]) for n in nds if n in N]) for nds, t in W.values() if t.get("highway") and t.get("name") and t.get("highway") not in ("footway", "path", "steps", "service")]
    out = []
    for nid, (la, lo, t) in N.items():
        if not (t.get("entrance") in ("main", "yes") or t.get("barrier") == "gate"): continue
        if not any(near_ring((la, lo), r, 8) for r in polys): continue
        st = min(((min((dist((la, lo), p) for p in ps), default=1e9), nm) for nm, ps in streets), default=(1e9, ""))
        out.append({"id": nid, "lat": r6(la), "lon": r6(lo), "main": t.get("entrance") == "main", "name": t.get("name", ""), "rue": st[1] if st[0] < 60 else ""})
    return out

# ---------------------------------------------------------------- Wikidata
KW = [("art", r"peintre|sculpt|graveur|dessinat|lithograph|photograph|illustrat|aquarell|céramiste|orfèvre"),
      ("lit", r"écrivain|écrivaine|poète|poétesse|romanc|dramaturge|journaliste|auteur|autrice|librettiste|critique littéraire|essayiste|historien"),
      ("music", r"compositeur|compositrice|chanteu|musicien|pianiste|violon|organiste|chef d'orchestre|cantatrice|chansonnier"),
      ("stage", r"acteur|actrice|comédien|danseu|réalisat|cinéaste|metteur en scène|mime|clown"),
      ("science", r"scientifique|physicien|chimiste|mathématicien|médecin|chirurgien|astronome|naturaliste|botaniste|ingénieur|inventeur|biologiste|géographe|zoologiste|pharmacien"),
      ("pol", r"homme politique|femme politique|député|sénateur|ministre|maire|révolutionnaire|diplomate|syndicaliste|communard"),
      ("mil", r"militaire|général|maréchal|officier|amiral|colonel|soldat|aviateur"),
      ("urb", r"architecte|urbaniste|paysagiste"), ("philo", r"philosophe"), ("resist", r"résistant|déporté")]

def cats(desc, sex):
    c = [k for k, rx in KW if desc and re.search(rx, desc, re.I)]
    if sex and sex.endswith("Q6581072"): c.append("women")
    return c

v = lambda b, k: b[k]["value"] if k in b else None
qid = lambda u: u.rsplit("/", 1)[-1]
fname = lambda u: urllib.parse.unquote(u.rsplit("Special:FilePath/", 1)[-1]) if u else None
yr = lambda t: str(int(t[:t.index("-", 1)])) if t and re.match(r"^-?\d{3,4}-", t) else ""
divnum = lambda s: str(int(re.search(r"\d+", s).group(0))) if s and re.search(r"\d+", s) else ""

PERS = """OPTIONAL { ?p rdfs:label ?pl FILTER(LANG(?pl)="fr") } OPTIONAL { ?p rdfs:label ?plen FILTER(LANG(?plen)="en") }
 OPTIONAL { ?p schema:description ?pd FILTER(LANG(?pd)="fr") } OPTIONAL { ?p schema:description ?pde FILTER(LANG(?pde)="en") }
 OPTIONAL { ?p wdt:P569 ?b } OPTIONAL { ?p wdt:P570 ?d } OPTIONAL { ?p wdt:P21 ?sex } OPTIONAL { ?p wdt:P1442 ?pimg }
 OPTIONAL { ?p wikibase:sitelinks ?sl }
 OPTIONAL { ?wp schema:about ?p; schema:isPartOf <https://fr.wikipedia.org/> }"""

def personne(acc, b):
    p = qid(v(b, "p")); e = acc.setdefault(p, {"q": p})
    for k, kk in (("pl", "n"), ("plen", "ne"), ("pd", "s"), ("pde", "se"), ("wp", "wp"), ("sex", "sex")):
        if v(b, k) and kk not in e: e[kk] = v(b, k)
    for k in ("b", "d"):
        if v(b, k) and k not in e: e[k] = yr(v(b, k))
    if v(b, "pimg") and "img" not in e: e["img"] = fname(v(b, "pimg"))
    if v(b, "sl"): e["sl"] = max(e.get("sl", 0), int(v(b, "sl")))
    return e

def details(qids, lot=150):
    """Détails des personnes (libellés, descriptions, dates, liens), par lots pour ménager le service."""
    acc = {}
    for i in range(0, len(qids), lot):
        vals = " ".join("wd:" + q for q in qids[i:i + lot])
        for b in sparql(f'''SELECT ?p ?pl ?plen ?pd ?pde ?b ?d ?wp ?pimg ?sex ?sl WHERE {{ VALUES ?p {{ {vals} }} {PERS} }}'''): personne(acc, b)
        print(f"   détails : {min(i + lot, len(qids))}/{len(qids)}")
    return acc

def fiche(p, extra=None):
    t = {"n": p.get("n") or p.get("ne") or p["q"], "s": p.get("s") or "", "b": p.get("b", ""), "d": p.get("d", ""), "c": cats(p.get("s", ""), p.get("sex")), "wd": p["q"]}
    if p.get("se"): t["se"] = p["se"]
    if p.get("wp"): t["wp"] = urllib.parse.unquote(p["wp"].split("/wiki/", 1)[1])
    if p.get("sl"): t["sl"] = p["sl"]
    t.update(extra or {})
    return t

def wikidata(cid, cfg, centres_div):
    q = cfg["q"]; out = []
    # 1. tombes géolocalisées
    G = sparql(f'''SELECT ?g ?gl ?c ?divl ?img WHERE {{ ?g wdt:P31 wd:Q173387; wdt:P625 ?c; wdt:P276 ?div. ?div (wdt:P361|wdt:P131)* wd:{q}.
      OPTIONAL {{ ?g rdfs:label ?gl FILTER(LANG(?gl)="en") }} OPTIONAL {{ ?div rdfs:label ?divl FILTER(LANG(?divl)="fr") }} OPTIONAL {{ ?g wdt:P18 ?img }} }}''')
    P = sparql(f'''SELECT ?g ?p ?pl ?plen ?pd ?pde ?b ?d ?wp ?pimg ?sex ?sl WHERE {{ ?g wdt:P31 wd:Q173387; wdt:P625 ?c; wdt:P276 ?div. ?div (wdt:P361|wdt:P131)* wd:{q}.
      {{ ?p wdt:P119 ?g }} UNION {{ ?g wdt:P547 ?p }} {PERS} }}''')
    graves = {}
    for b in G:
        g = qid(v(b, "g"))
        if g in graves: continue
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", v(b, "c"))
        graves[g] = {"g": g, "lat": r6(float(m.group(2))), "lon": r6(float(m.group(1))), "lbl": v(b, "gl") or "", "div": divnum(v(b, "divl")), "img": fname(v(b, "img")), "ps": {}}
    for b in P:
        g = qid(v(b, "g"))
        if g in graves: personne(graves[g]["ps"], b)
    deja = set()
    for e in graves.values():
        ps = sorted((p for p in e["ps"].values() if p.get("n") or p.get("ne")), key=lambda p: -p.get("sl", 0))
        base = {"id": "w" + e["g"][1:], "lat": e["lat"], "lon": e["lon"], "div": e["div"]}
        if ps:
            t = fiche(ps[0], base)
            noms = [p.get("n") or p.get("ne") for p in ps]
            t["n"] = ", ".join(noms[:3]) + (f" et {len(noms) - 3} autre{'s' if len(noms) > 4 else ''}" if len(noms) > 3 else "")
            t["c"] = sorted(set(sum((cats(p.get("s", ""), p.get("sex")) for p in ps), [])))
            if len(ps) > 1: t["note"] = "Repose aussi ici : " + ", ".join((p.get("n") or p.get("ne")) + (f" ({p['s']})" if p.get("s") else "") for p in ps[1:6]) + ("…" if len(ps) > 6 else "") + "."
            t["pq"] = [p["q"] for p in e["ps"].values()]
            img = e["img"] or ps[0].get("img")
            deja.update(t["pq"])
        else:
            lbl = re.sub(r"^(Grave|Tomb|Chapel|Vault|Family grave|Columbarium niche|Monument|Funerary monument)s? (of|to) (the )?(families |family )?", "", e["lbl"], flags=re.I).strip()
            t = dict(base, n=lbl or "Sépulture", s="", c=[], wg=e["g"]); img = e["img"]
        if img: t["ph"] = img
        out.append(t)
    # 2. personnalités dont seule la division est connue (tombe sans coordonnées, ou inhumation dans la division)
    DV = {qid(v(b, "dv")): divnum(v(b, "divl")) for b in sparql(f'''SELECT ?dv ?divl WHERE {{ ?dv wdt:P361 wd:{q}; rdfs:label ?divl FILTER(LANG(?divl)="fr") }}''')}
    D = sparql(f'''SELECT ?p ?dv ?gimg WHERE {{
      {{ ?p wdt:P119 ?g. ?g wdt:P31 wd:Q173387; wdt:P276 ?dv. ?dv wdt:P361 wd:{q}. FILTER NOT EXISTS {{ ?g wdt:P625 ?cc }} OPTIONAL {{ ?g wdt:P18 ?gimg }} }}
      UNION {{ ?p wdt:P119 ?dv. ?dv wdt:P361 wd:{q}. }} }}''')
    divs, gimgs = {}, {}
    for b in D:
        pq = qid(v(b, "p")); d = DV.get(qid(v(b, "dv")), "")
        if d: divs.setdefault(pq, d)
        if v(b, "gimg"): gimgs.setdefault(pq, fname(v(b, "gimg")))
    acc = details([pq for pq in divs if pq not in deja])
    # centre de division : polygone OSM, sinon moyenne des tombes géolocalisées de la division
    moy = {}
    for t in out:
        if t["div"]: moy.setdefault(t["div"], []).append((t["lat"], t["lon"]))
    centre = lambda d: centres_div.get(d) or ((sum(x[0] for x in moy[d]) / len(moy[d]), sum(x[1] for x in moy[d]) / len(moy[d])) if d in moy else None)
    for p in acc.values():
        if p["q"] in deja or not (p.get("n") or p.get("ne")): continue
        d = divs.get(p["q"]); c = centre(d) if d else None
        if not c: continue
        t = fiche(p, {"id": "d" + p["q"][1:], "lat": r6(c[0]), "lon": r6(c[1]), "div": d, "ap": 1})
        img = gimgs.get(p["q"]) or p.get("img")
        if img: t["ph"] = img
        out.append(t); deja.add(p["q"])
    # 3. cimetière sans positions publiées : toutes les personnalités inhumées
    if cfg.get("sans_position"):
        A = sparql(f'''SELECT DISTINCT ?p WHERE {{ ?p wdt:P119 wd:{q}. }}''')
        acc = details([qid(v(b, "p")) for b in A if qid(v(b, "p")) not in deja])
        for p in acc.values():
            if p["q"] in deja or not (p.get("n") or p.get("ne")): continue
            t = fiche(p, {"id": "d" + p["q"][1:], "div": ""})
            if p.get("img"): t["ph"] = p["img"]
            out.append(t)
    return out

def compacter(cfg, items, curated):
    """Écarte les fiches déjà présentes dans index.html et allège le JSON."""
    cur_wd = {t["wd"] for t in curated if t.get("wd")}
    cur_xy = [t for t in curated if t.get("lat") is not None]
    res = []
    for w in items:
        if (set(w.get("pq", [])) | ({w["wd"]} if w.get("wd") else set())) & cur_wd: continue
        if w.get("lat") is not None and not w.get("ap") and any(dist((c["lat"], c["lon"]), (w["lat"], w["lon"])) < 30 and toks(c["n"]) & toks(w["n"]) for c in cur_xy): continue
        t = {k: w[k] for k in ("id", "n", "lat", "lon", "div", "s", "se", "b", "d", "note", "c", "wd", "wg", "wp", "ap", "sl", "ph") if w.get(k) not in (None, "", [])}
        if t.get("wd"): t.pop("wg", None)
        pre = cfg.get("ph", "").format(div=w.get("div", ""))
        if pre and t.get("ph", "").startswith(pre): t["ph"] = "~" + t["ph"][len(pre):]
        res.append(t)
    res.sort(key=lambda t: (-t.get("sl", 0), t["n"]))
    return res

def lire_data():
    s = (RACINE / "index.html").read_text(encoding="utf-8")
    return json.loads(re.search(r"const DATA = (\{.*?\});\n", s).group(1))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data = {c["id"]: c for c in lire_data()["cems"]}
    if "--portes" in sys.argv:
        for cid in args:
            cfg = CIMETIERES[cid]; N, W, R = lire_osm(cfg["bbox"])
            cem = data.get(cid) or {"tombs": [], "lat0": None, "lon0": None}
            w, s_, e, n = map(float, cfg["bbox"].split(","))
            cem.setdefault("lat0", (s_ + n) / 2); cem.setdefault("lon0", (w + e) / 2)
            if cem["lat0"] is None: cem["lat0"], cem["lon0"] = (s_ + n) / 2, (w + e) / 2
            _, _, polys = construire_osm(cfg, cem, N, W, R)
            print(cid, json.dumps(portes(N, W, polys), ensure_ascii=False, indent=1))
        return
    for cid in args or list(CIMETIERES):
        cfg = CIMETIERES[cid]; cem = data.get(cid)
        if not cem: print(cid, ": cimetière absent de index.html, ignoré"); continue
        print(f"{cid} : OpenStreetMap…")
        N, W, R = lire_osm(cfg["bbox"])
        ext, centres, _ = construire_osm(cfg, cem, N, W, R)
        (RACINE / f"osm-{cid}.json").write_text(json.dumps(ext, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"   {len(ext['ways'])} allées, {len(ext['tombs'])} sépultures, {len(centres)} divisions")
        if not cfg.get("q"): continue
        print(f"{cid} : Wikidata…")
        items = compacter(cfg, wikidata(cid, cfg, centres), cem["tombs"])
        (RACINE / f"tombes-{cid}.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"   {len(items)} fiches ({sum(1 for t in items if t.get('ap'))} placées au centre de leur division, {sum(1 for t in items if t.get('lat') is None)} sans position)")

if __name__ == "__main__":
    main()
