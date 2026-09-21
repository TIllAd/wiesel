"""Erzeugt die kuratierte WiSo-Personenübersicht für Kategorie E.

Die Quelle ist ausschließlich die öffentlich sichtbare WiSo-Webseite. Der
Crawler nimmt keine privaten Kontaktdaten auf und listet bei Lehrstühlen nur
Professor:innen sowie klar ausgewiesene Sekretariate/Office-Management.
"""
from datetime import date
from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup

OUTPUT = Path(__file__).resolve().parents[2] / "knowledge_base" / "anlaufstellen" / "ansprechpersonen-wiso.md"
PROFESSORS_URL = "https://www.wiso.rw.fau.de/forschung/forschungsprofil/professorenschaft/"

TEAM_CONTACTS = [
    ("Empirische Wirtschaftssoziologie", "Ulrike Marx", "Sekretariat", "https://www.wirtschaftssoziologie.rw.fau.de/lehrstuhlteam/sekretariat/"),
    ("Wirtschafts- und Sozialpsychologie", "Carina Peterhansl, Hannelore Lang, Susanne Piehl", "Sekretariat", "https://www.psychologie.rw.fau.de/team/"),
    ("Soziologie und Empirische Sozialforschung", "Ursula Straetz", "Sekretariat", "https://www.soziologie.rw.fau.de/team/sekretariat/"),
    ("VWL, insb. Sozialpolitik", "Jody Schimek", "Administrative Staff", "https://www.sozialpolitik.rw.fau.de/lehrstuhlteam-2/sekretariat/"),
    ("Finanzierung und Banken", "Birgit Mayer", "Team-Kontakt", "https://www.lfb.rw.fau.de/team/"),
    ("Controlling und Rechnungslegung", "Christa Heffner", "Sekretariat", "https://www.controlling.rw.fau.de/team/sekretariat/"),
    ("Rechnungslegung und Wirtschaftsprüfung", "Beatrix Hillen", "Sekretariat", "https://www.acc.rw.fau.de/lehrstuhl/beatrix-hillen/"),
    ("Versicherungswirtschaft und Risikomanagement", "Daniela Tagsold", "Sekretariat", "https://www.vwrm.rw.fau.de/team/sekretariat/"),
    ("Business Analytics and Sustainability", "Angela Brunner", "Sekretariat", "https://www.bas.rw.fau.de/faudir/angela-brunner/"),
    ("Wirtschaftsprivatrecht", "Andrea Stöcklein", "Sekretariat", "https://www.precht.rw.fau.de/lehrstuhlteam/sekretariat/"),
    ("Industrielles Management", "Linda Escherich", "Office Management", "https://www.industry.rw.fau.de/team/team-assistance/"),
    ("Internationales Management", "Marion Wehner", "Administrative Staff", "https://www.im.rw.fau.de/team/administrative-staff/"),
    ("Supply Chain Management", "Karoline Wlochowitz", "Lehrstuhlassistenz", "https://www.scm.rw.fau.de/team/"),
    ("Corporate Sustainability Management", "Susanne Piehl", "Sekretariat", "https://www.nachhaltigkeit.rw.fau.de/unser-team/sekretariat/"),
    ("Marketing Intelligence", "Eva Neumüller", "Sekretariat", "https://www.marketing-intelligence.rw.fau.de/team/sekretariat-2/"),
    ("Marketing", "Doris Häusner", "Sekretariat", "https://www.marketing.rw.fau.de/team/"),
    ("Versicherungsmarketing", "Beate Bäumler", "Sekretariat", "https://www.versicherungsmarketing.rw.fau.de/team-2/sekretariat/"),
    ("Arbeitsmarkt- und Berufsforschung", "Ursula Straetz", "Sekretariat", "https://www.wsab.rw.fau.de/team/sekretariat/"),
    ("Statistik und empirische Wirtschaftsforschung", "Felicitas Koetzsch", "Sekretariat", "https://www.empiricalecon.rw.fau.de/team/sekretariat-felicitas-koetzsch/"),
    ("VWL, insb. Finanzwissenschaft", "Andrea Wilhelm", "Sekretariat", "https://www.finanzwissenschaft.rw.fau.de/person/andrea-wilhelm/"),
    ("VWL, insb. Makroökonomie", "Nadja Ipfelkofer", "Sekretariat", "https://www.makro.rw.fau.de/team/secretary/"),
    ("VWL, insb. Wirtschaftstheorie", "Angela Brunner", "Sekretariat", "https://www.wirtschaftstheorie.rw.fau.de/team/sekretariat/"),
    ("Innovation und Wertschöpfung", "Monika Hanisch", "Office Management", "https://www.wi1.rw.fau.de/people/team/office-management/"),
    ("Digitale Transformation", "Julia Neukam", "Administrative Assistant", "https://www.digitaltransformation.rw.fau.eu/team/administrative-assistance/"),
]


def professors():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; WisdomBot/1.0)"})
    response = session.get(PROFESSORS_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    seen, result = set(), []
    for link in soup.select('main a[href*="/professorenschaft/prof-"]'):
        url = link.get("href", "").strip()
        if url in seen:
            continue
        short_name = re.sub(r"\s+", " ", link.get_text(" ", strip=True))
        if not short_name.startswith("Prof"):
            continue
        seen.add(url)
        context = link.parent.get_text(" ", strip=True)
        field = re.sub(r"\s+", " ", context.replace(short_name, "")).strip(" –-: ")
        try:
            profile = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
            name = re.sub(r"\s+", " ", profile.select_one("main h1").get_text(" ", strip=True))
        except (requests.RequestException, AttributeError):
            name = short_name
        result.append((name, field or "Fachgebiet siehe Profil", url))
    if len(result) < 45:
        raise RuntimeError(f"Professorenschaft unvollständig extrahiert ({len(result)} Einträge)")
    return sorted(result, key=lambda item: item[0])


def render(entries):
    lines = [
        "# Anlaufstellen & Ansprechpersonen an der FAU WiSo",
        "Kategorie E – kuratierte Orientierung für die Suche nach der richtigen Person.",
        f"Stand: {date.today().isoformat()}. Primärquellen: offizielle WiSo-Webseiten.",
        "",
        "## Erst die richtige Stelle wählen",
        "- Allgemeine Studienorganisation, Bewerbung, Studiengangwechsel oder Studienzweifel: Zentrale Studienberatung WiSo, offene Sprechstunde Mi/Do 9–12 Uhr oder zsb-rewi@fau.de. Quelle: https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/zentrale-studienberatung/",
        "- Inhaltliche Fragen zu einem konkreten Studiengang, Schwerpunkt oder Studiengangwechsel ab dem 3. Hochschulsemester: Fachstudienberatung. Quelle: https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/fachstudienberatung/",
        "- Prüfungsanmeldung, Fristen und organisatorische Prüfungsfragen: Prüfungsamt WiSo. Nicht zuständig für Immatrikulation, Rückmeldung oder Adresse; dafür die Studierendenverwaltung. Quelle: https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenservice/pruefungsamt/",
        "- Auslandssemester oder Fragen internationaler Studierender: Büro für Internationale Beziehungen, LG 2.232, wiso-international@fau.de, 0911 5302-95627. Quelle: https://www.wiso.rw.fau.de/studium/international-studierende/international-office/",
        "- Praktikum, Berufseinstieg, Bewerbung, Career Day und Mentoring: Career Service WiSo, wiso-career-service@fau.de, 0911 5302-95678. Quelle: https://www.wiso.rw.fau.de/studium/studienorganisation/studierendenberatung/career-service-am-fachbereich/",
        "- Diskriminierung, Diversität, Studium ohne akademische Familientradition oder Raum der Stille: Diversity-Angebote WiSo und Mentoring/Support. Quelle: https://www.wiso.rw.fau.de/fachbereich/strategie/handlungsfeld-people/diversitaet-am-fachbereich/",
        "",
        "## Fachstudienberatung: Bachelor",
        "- International Business Studies (B.Sc.): Nikhila Raghavan, nikhila.raghavan@fau.de.",
        "- International Economic Studies (B.Sc.): Dr. Maximilian Pöhnlein, wiso-ba-ies@fau.de.",
        "- Sozialökonomik (B.A.): PD Dr. Andreas Damelang, wiso-ba-sozoek@fau.de.",
        "- Wirtschaftsinformatik (B.Sc.): Bastian Brechtelsbauer, wiso-ba-win@fau.de.",
        "- Wirtschaftswissenschaften (B.A.), allgemein: Annabell Schneider, wiso-wiwi@fau.de.",
        "- Wirtschaftswissenschaften (B.A.), BWL: Marius Weiß, wiso-wiwi-bwl@fau.de.",
        "- Wirtschaftswissenschaften (B.A.), VWL: Paolo Bontempo, wiso-wiwi-vwl@fau.de.",
        "- Wirtschaftswissenschaften (B.A.), Wirtschaftsinformatik: Tina Wölfl, wiso-wiwi-wi@fau.de.",
        "- Wirtschaftswissenschaften (B.A.), Wirtschafts- und Betriebspädagogik: Dr. Yvonne Schalek, wiso-wiwi-wipaed@fau.de.",
        "",
        "## Lehrstühle: administrative Kontakte",
        "Für konkrete Fragen zu Lehrveranstaltungen ist zuerst StudOn bzw. die Veranstaltungsankündigung maßgeblich. Bei organisatorischen Anliegen an einem Lehrstuhl ist das jeweilige Sekretariat oder Office Management die passende erste Station.",
    ]
    for chair, name, role, url in TEAM_CONTACTS:
        lines.append(f"- {chair}: {name} ({role}) – {url}")
    lines += ["", "## Professorinnen und Professoren: Fachgebiete und Profile", "Diese Liste hilft bei der fachlichen Zuordnung. Sie ersetzt keine Prüfungs- oder Studienberatung; eine Professur ist nicht automatisch die richtige Adresse für individuelle Verwaltungsfragen."]
    for name, field, url in entries:
        suffix = " Nicht als aktuelle Ansprechpartnerin verwenden; die offizielle Seite kennzeichnet sie als verstorben/ehemalig." if "Gatzert" in name else ""
        lines.append(f"- {name}: {field}. Profil: {url}.{suffix}")
    lines += ["", "## Quellen und Aktualisierung", f"- Professorenschaft: {PROFESSORS_URL}", "- Lehrstuhlübersicht: https://www.wiso.rw.fau.de/fachbereich/leitung-und-organisation/institute-und-lehrstuehle/lehrstuehle/", "- Personen- und Rollenangaben bei Lehrstühlen: jeweils verlinkte offizielle Teamseite.", "- Bei abweichenden Angaben auf einer aktuellen offiziellen Seite hat diese Vorrang. Keine privaten Durchwahlen oder nichtöffentlich bereitgestellten Kontaktdaten ausgeben."]
    return "\n".join(lines) + "\n"


def main():
    OUTPUT.write_text(render(professors()), encoding="utf-8")
    print(f"{OUTPUT}: geschrieben")


if __name__ == "__main__":
    main()
