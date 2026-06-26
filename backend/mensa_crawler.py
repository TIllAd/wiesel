"""
Wiesel Mensa Crawler v4
Crawlt alle 6 Erlangen/Nürnberg Mensen und schreibt mensa-woche.md
in die Wissensbasis.

Usage:
  python3 mensa_crawler.py                          # schreibt knowledge_base/mensa-woche.md
  python3 mensa_crawler.py --output /pfad/zur/datei
  python3 mensa_crawler.py --json                   # nur JSON auf stdout
"""

import re
import json
import sys
import argparse
import requests
from datetime import date, timedelta, datetime
from pathlib import Path

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; WieselBot/1.0)"})

MENSEN = {
    "suedmensa":     ("Südmensa Erlangen",          "Erwin-Rommel-Str. 60, Erlangen"),
    "lmp":           ("Mensa Langemarckplatz",       "Langemarckplatz 6, Erlangen"),
    "insel_schuett": ("Mensa Insel Schütt",          "Insel Schütt 8, Nürnberg"),
    "reg_str":       ("Mensa Regensburger Straße",   "Regensburger Str. 160, Nürnberg"),
    "n_ohm":         ("Mensateria Ohm",              "Keßlerplatz 12, Nürnberg"),
    "n_veilh":       ("Cafeteria Veilhofstraße",     "Veilhofstr. 9, Nürnberg"),
}

# Allergen-Codes die auf vegan/vegetarisch hinweisen
VEGAN_CODES = {"veg"}
VEGGIE_CODES = {"V", "veg"}


# ─── Fetch ───────────────────────────────────────────────────────────────────

def submit_filter_form():
    filter_data = {k: "on" for k in [
        "zssS", "zssR", "zssG", "zssL", "zssW", "zssF",
        "zssV", "zssveg", "zssGf", "zssMV", "zssCO2"
    ]}
    resp = SESSION.post(
        "https://stwer.my-mensa.de/chooser.php?form=submitted",
        data=filter_data, allow_redirects=True, timeout=15
    )
    resp.raise_for_status()


def clean_text(raw: str) -> str:
    text = re.sub(r'<sup[^>]*>.*?</sup>', '', raw, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ',
        text.replace('&shy;', '').replace('&nbsp;', ' ')
            .replace('&amp;', '&').replace('&quot;', '"')
            .replace('&auml;', 'ä').replace('&ouml;', 'ö')
            .replace('&uuml;', 'ü').replace('&szlig;', 'ß')
            .replace('&Auml;', 'Ä').replace('&Ouml;', 'Ö').replace('&Uuml;', 'Ü')
    ).strip()


def doy_to_date(day_id: str) -> date:
    year, doy = int(day_id[:4]), int(day_id[4:])
    return date(year, 1, 1) + timedelta(days=doy - 1)


def parse_mensa_html(html: str, slug: str) -> list[dict]:
    chunks = re.split(r'(?=<div[^>]*data-role=["\']page["\'])', html)
    results = []
    for chunk in chunks:
        m = re.search(rf'id=["\']({re.escape(slug)}_tag_(\d{{7}}))["\']', chunk)
        if not m:
            continue
        day_date = doy_to_date(m.group(2))

        gid_to_cat = {}
        for gid, content in re.findall(
            r'<li[^>]+data-gid=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*groupdivider[^"\']*["\'][^>]*>(.*?)</li>',
            chunk, re.DOTALL
        ):
            gid_to_cat[gid] = re.sub(r'<[^>]+>', '', content).strip()

        seen, meals = set(), []
        for gid, refs_raw, content in re.findall(
            r'<li\s+class=["\']conditional[^"\']*["\'][^>]+data-gid=["\']([^"\']+)["\'][^>]*ref=\'([^\']+)\'[^>]*>(.*?)</li>',
            chunk, re.DOTALL
        ):
            if gid in seen:
                continue
            seen.add(gid)
            h3 = re.search(r'<h3[^>]*>(.*?)</h3>', content, re.DOTALL)
            name = clean_text(h3.group(1) if h3 else content)
            if not name:
                continue
            prices = re.findall(r'(\d+,\d+)&nbsp;&euro;', content)
            try:
                allergens = json.loads(refs_raw.replace("'", '"'))
            except Exception:
                allergens = re.findall(r'"([^"]+)"', refs_raw)
            meals.append({
                "name":           name,
                "category":       gid_to_cat.get(gid, ""),
                "allergens":      allergens,
                "price_student":  prices[0].replace(',', '.') if prices else None,
                "price_employee": prices[1].replace(',', '.') if len(prices) > 1 else None,
                "price_guest":    prices[2].replace(',', '.') if len(prices) > 2 else None,
            })
        results.append({
            "date":    day_date.isoformat(),
            "weekday": day_date.strftime("%A"),
            "meals":   meals,
        })
    return sorted(results, key=lambda x: x["date"])


def fetch_mensa(slug: str) -> list[dict]:
    url = f"https://stwer.my-mensa.de/essen.php?hyp=1&lang=de&mensa={slug}"
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    return parse_mensa_html(resp.text, slug)


def crawl_all() -> dict:
    submit_filter_form()
    results = {}
    for slug, (name, address) in MENSEN.items():
        try:
            days = fetch_mensa(slug)
            results[slug] = {"name": name, "address": address, "days": days}
        except Exception as e:
            results[slug] = {"name": name, "address": address, "days": [], "error": str(e)}
    return results


# ─── Markdown Generator ──────────────────────────────────────────────────────

WEEKDAY_DE = {
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag",
    "Saturday": "Samstag", "Sunday": "Sonntag"
}

def emoji_for(allergens: list[str]) -> str:
    codes = set(allergens)
    if codes & VEGAN_CODES:
        return " 🌱"
    if codes & VEGGIE_CODES:
        return " 🥗"
    return ""


def format_date_de(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAY_DE[d.strftime('%A')]}, {d.strftime('%d.%m.%Y')}"


def generate_markdown(data: dict) -> str:
    today = date.today()
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Collect all unique dates across all mensen
    all_dates = sorted({
        day["date"]
        for v in data.values()
        for day in v.get("days", [])
        if day["meals"]
    })

    lines = [
        f"# Mensa-Speisepläne FAU – Heute & diese Woche",
        f"*Zuletzt aktualisiert: {now_str}*",
        "",
        "Bezahlung überall bargeldlos mit FAUcard.",
        "",
    ]

    for iso_date in all_dates:
        d = date.fromisoformat(iso_date)
        weekday_de = WEEKDAY_DE[d.strftime("%A")]

        # Section header
        if iso_date == today.isoformat():
            lines.append(f"## **Heute** – {weekday_de}, {d.strftime('%d.%m.%Y')}")
        elif iso_date == (today + timedelta(days=1)).isoformat():
            lines.append(f"## **Morgen** – {weekday_de}, {d.strftime('%d.%m.%Y')}")
        else:
            lines.append(f"## **{weekday_de}** – {weekday_de}, {d.strftime('%d.%m.%Y')}")
        lines.append("")

        for slug, v in data.items():
            name, address = v["name"], v["address"]
            day_data = next((day for day in v.get("days", []) if day["date"] == iso_date), None)
            if not day_data or not day_data["meals"]:
                continue

            lines.append(f"### {name} ({address})")
            for meal in day_data["meals"]:
                cat   = meal["category"] or "Linie ?"
                price = f"{meal['price_student']} €" if meal["price_student"] else "Preis unbekannt"
                emoji = emoji_for(meal["allergens"])
                lines.append(f"- **{cat}:** {meal['name']} – {price} (Stud.){emoji}")
            lines.append("")

    lines += [
        "---",
        "*Quelle: stwer.my-mensa.de – Angaben ohne Gewähr*",
        "*Vollständige Pläne: https://www.werkswelt.de/index.php?id=mensen-cafeterien-cafebars*",
    ]
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT = Path(__file__).parent.parent / "knowledge_base" / "mensa-woche.md"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true", help="JSON auf stdout statt Markdown")
    args = parser.parse_args()

    print("[*] Crawle Mensen...", file=sys.stderr)
    data = crawl_all()

    for slug, v in data.items():
        total = sum(len(d["meals"]) for d in v["days"])
        status = f"✅ {len(v['days'])} Tage, {total} Gerichte"
        if "error" in v:
            status = f"❌ {v['error']}"
        print(f"    {v['name']}: {status}", file=sys.stderr)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    md = generate_markdown(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"[✓] Gespeichert: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()