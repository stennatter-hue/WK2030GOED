#!/usr/bin/env python3
"""
Haalt WK 2026 spelersstatistieken op bij FOX Sports en schrijft spelers.json.
Draait automatisch via GitHub Actions (zie .github/workflows/update-stats.yml),
maar je kunt het ook lokaal draaien:  python auto/fetch_players.py

Geen API-sleutel nodig. Combineert meerdere ranglijsten (goals, assists,
schoten, schoten op doel) zodat je een brede set spelers krijgt.
"""
import json
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

BASE = ("https://www.foxsports.com/soccer/fifa-world-cup/stats"
        "?category=standard&season=2026&sortOrder=desc&sort={}")
SORTS = ["g", "a", "s", "sog", "xg", "mp"]   # verschillende sorteringen = meer unieke spelers
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

# kolomkop -> veld in onze dataset
WANT = {"G": "g", "A": "a", "S": "s", "SOG": "sog", "XG": "xg"}


def num(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return 0.0


def parse_page(html):
    """Geeft een lijst spelers-dicts terug uit één FOX-statistiekpagina."""
    soup = BeautifulSoup(html, "lxml")
    players = []
    for table in soup.find_all("table"):
        header_cells = [th.get_text(strip=True).upper()
                        for th in table.find_all("th")]
        if "SOG" not in header_cells or "S" not in header_cells:
            continue  # niet de standaard-statistiektabel
        # index van elke gewenste kolom binnen een rij
        col_idx = {}
        for i, name in enumerate(header_cells):
            if name in WANT and WANT[name] not in col_idx:
                col_idx[WANT[name]] = i
        for row in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True)
                     for td in row.find_all(["td", "th"])]
            if len(cells) < len(header_cells):
                continue
            # de spelercel bevat "Voornaam Achternaam LAND" (LAND = 3 hoofdletters)
            name_cell = next((c for c in cells
                              if re.search(r"[A-Za-z].*\b[A-Z]{3}\b$", c)), None)
            if not name_cell:
                continue
            m = re.search(r"^(.*?)\s+([A-Z]{3})$", name_cell)
            if not m:
                continue
            name, country = m.group(1).strip(), m.group(2)
            if not name or name.upper() == "PLAYERS":
                continue
            rec = {"n": name, "c": country, "gp": 1}
            for field, idx in col_idx.items():
                rec[field] = num(cells[idx]) if idx < len(cells) else 0
            # goals/assists/schoten als gehele getallen
            for k in ("g", "a", "s", "sog"):
                rec[k] = int(rec.get(k, 0))
            rec["xg"] = round(rec.get("xg", 0.0), 2)
            players.append(rec)
        break
    return players


def fetch(url, tries=3):
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and "SOG" in r.text:
                return r.text
            print(f"  status {r.status_code}, poging {attempt + 1}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  fout: {e}", file=sys.stderr)
        time.sleep(2 + attempt * 2)
    return None


def main():
    merged = {}
    for sort in SORTS:
        url = BASE.format(sort)
        print(f"ophalen sort={sort} ...")
        html = fetch(url)
        if not html:
            print(f"  overslaan (geen data) voor sort={sort}", file=sys.stderr)
            continue
        for p in parse_page(html):
            key = (p["n"].lower(), p["c"])
            # houd de rij met de meeste informatie (hoogste som van stats)
            score = p["g"] * 100 + p["a"] * 50 + p["s"]
            if key not in merged or score > merged[key]["_score"]:
                p["_score"] = score
                merged[key] = p
        time.sleep(1)

    out = sorted(merged.values(),
                 key=lambda p: (p["g"], p["a"], p["s"]), reverse=True)
    for p in out:
        p.pop("_score", None)

    if not out:
        print("GEEN spelers gevonden — FOX-structuur mogelijk gewijzigd of geblokkeerd.",
              file=sys.stderr)
        sys.exit(1)

    with open("spelers.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"klaar: {len(out)} spelers naar spelers.json")


if __name__ == "__main__":
    main()
