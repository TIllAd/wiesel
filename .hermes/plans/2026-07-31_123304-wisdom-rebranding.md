# Wisdom-Rebranding – Umbauplan

> Für Hermes: Diesen Plan erst nach finaler Brand-Office-Freigabe umsetzen. Kein Logo aus einer Signal-Vorschau zur Produktionswahrheit erklären; das wäre erstaunlich effizienter Murks.

**Ziel:** Das sichtbare Produkt heißt überall konsistent **Wisdom** und wird als sachlicher WiSo-Navigator mit Kompass-Motiv geführt, ohne LTI, Datenbank, Analytics oder Deployment unnötig zu gefährden.

**Architektur:** Produktname und technische Identifikatoren werden getrennt. In Phase 1 ändern sich ausschließlich sichtbare Inhalte, Assistenz-Persona und Markenassets. Bestehende interne Namen wie Repository `wiesel`, `wiesel.db`, Umgebungsvariablen und Docker-Container bleiben zunächst bewusst unverändert; sie sind Betriebsinterna, keine Marke.

**Ist-Zustand:** Der lokale Produktionsquellstand unter `C:\Users\tillt\wiesel` enthält noch mindestens 79 getrackte Textdateien mit alten Bezeichnungen. Kritische Treffer liegen in `backend/static/chat.html`, `backend/static/strings.js`, `system-prompt.md`, `backend/main.py`, rechtlichen Seiten, Doku, Skripten und Crawler-User-Agents. Die angegebene Landingpage konnte automatisiert nicht geladen werden, weil der Web-Extractor hier nicht konfiguriert ist; der Plan arbeitet daher gegen die lokale Quellbasis und verlangt einen manuellen Live-Abgleich.

## Nicht verhandelbare Markenregeln

- Produktname in Fließtext, UI, Metadaten und URLs: **Wisdom**. Nicht `WiSdom`, nicht `WISDOM`, nicht übersetzen.
- Die rote Gestaltung von `Wis` darf als Wortmarken-Detail existieren, begründet aber keine abweichende Schreibweise. Text-Renderer, Screenreader, Autokorrektur und Menschen kennen keine Design-Briefings. Tragisch, aber wahr.
- Rolle: **Navigator für den WiSo-Alltag**, nicht „Besserwisser“, Tierfigur oder „Uni-Buddy“.
- Visualität: finaler Brand-Office-Avatar und Kompass-Icon. Kein Einsatz des aktuellen Entwurfs als verbindliches Produktionsasset vor Freigabe.
- Farben nur gemäß freigegebenem FAU-Brand-Office-Paket; aus dem vorliegenden Briefing sind `#041E42` (FAU Dunkelblau) und `#C50F3C` (RW Rot) als Zielwerte ersichtlich.

## Phase 0 – Markenpaket und Freigabekriterien festziehen

**Ziel:** Das Team liefert eine einzige belastbare Quelle statt einer Signal-Archäologie.

1. Brand Office schriftlich um vier Ausgaben bitten: Wortmarke horizontal auf hell/dunkel, Avatar quadratisch transparent, Kompass quadratisch transparent, Druckvorlage für QR-Sticker. Formate: SVG als Master, PNG/WebP als Web-Export; CMYK-PDF/EPS nur für Druck.
2. Eine Kurzdatei `docs/BRAND.de.md` anlegen: Produktname `Wisdom`, Schreibregel, Farbwerte, Mindestgrößen, erlaubte Hintergründe, Alt-Texte, Rollenbeschreibung und Slogan-Regeln. Diese Datei ist der Referenzpunkt für Team, Web und StudOn.
3. Slogans vor der Implementierung final entscheiden. Empfohlene Systemformulierung: „Wisdom – Dein Kompass durch den WiSo-Alltag“. Landingpage-CTA: „Spar dir das Verzetteln. Frag Wisdom.“ Kein Sammelsurium aus „Wegweiser“, „Tourguide“, „Buddy“ und „Navigator“; Marken werden durch Wiederholung gebaut, nicht durch poetisches Herumrudern.
4. Festlegen, ob die öffentliche Chat-URL von `wiesel.chatbot-wiso.de` auf eine Wisdom-URL wechseln darf. Falls ja: neue Subdomain zuerst parallel betreiben, alte URL mindestens ein Semester per 301 weiterleiten und die LTI-Launch-URL erst nach StudOn-Test umstellen.

**Abnahme:** Brand Office bestätigt Assets und Farben; Team bestätigt genau eine Schreibweise und maximal zwei freigegebene Slogans.

## Phase 1 – Sichtbare Chat-Oberfläche ersetzen

**Ziel:** Kein*e Studierende*r sieht mehr Wiesel/Weasel oder die alte Tier-Metapher.

**Dateien:**
- Ändern: `backend/static/chat.html`
- Ändern: `backend/static/strings.js`
- Ersetzen/neu: `backend/static/assets/wisdom-avatar.*`, `backend/static/assets/wisdom-compass.*`, `backend/static/assets/wisdom-og.*`
- Später entfernen: `backend/static/wiesel_happy.png`, `wiesel_confused.png`, `wiesel_readingMHD.png`, `wiesel_standing.png`, `wiesel_thinking.png` – erst nachdem keine Referenz mehr existiert.

1. In `chat.html` die `--wiesel-*`-CSS-Variablen in semantische Marken-Tokens überführen (`--brand-navy`, `--brand-red`, `--surface`, `--text`). Das ist nicht bloß Kosmetik: Die alten organischen, asymmetrischen Tierformen bei Header-Avatar und Senden-Button werden durch klare, abgerundete Controls ersetzt.
2. Alle Avatar-Zustandsbilder durch ein einziges freigegebenes Avatar-Asset ersetzen. Animationen dürfen bleiben, aber nur neutral: leichte Ruhebewegung beim Denken/Antworten; keine Grab-, Tier- oder „wühl“-Bewegungen.
3. Alle sichtbaren Texte in allen fünf Übersetzungen ersetzen: Titel, Header, Screenreader-Labels, Begrüßung, Tippen-Status, Footer, Eingabefeld und Fehlertexte. Beispiel Deutsch: Header `Wisdom`, Unterzeile `Dein Kompass durch den WiSo-Alltag`, Begrüßung `Ich bin Wisdom. Ich helfe dir, den passenden nächsten Schritt an der WiSo zu finden.`
4. Die Typing-Phrasen von „wühl/nachlegen“ auf neutrale Navigation ändern, etwa `Ich prüfe kurz die passende Stelle…`, `Einen Moment, ich ordne das ein…`. Gleichwertige Übersetzungen in EN/ES/ZH/HI erstellen, nicht maschinisch wirken lassen.
5. Den Robot-Avatar mit einem eindeutigen Alt-Text versehen, etwa `Wisdom, der digitale WiSo-Navigator`; das Kompass-Icon als reine Dekoration (`alt=""`) behandeln, wenn der Kontext schon durch Text vermittelt wird.
6. Viewports 320 px, 768 px und 1440 px testen: Header, Sprachschalter, Flaggen-Button, Avatar, Kontrast, Fokuszustände und das Verhalten bei sehr langem Namen prüfen.

**Abnahme:** Browser-Suche im ausgelieferten Chat findet kein `Wiesel` oder `Weasel`. Tastatur-Navigation und Screenreader-Labels nennen Wisdom korrekt.

## Phase 2 – Bot-Persona und serverseitige Fallbacks

**Ziel:** Der Bot klingt wie ein verlässlicher Navigator, nicht wie das entfernte Tiermaskottchen oder ein übergriffiger Buddy.

**Dateien:**
- Ändern: `system-prompt.md`
- Ändern: `backend/main.py`
- Prüfen/ändern: `backend/eval_ton.py`, `backend/run_eval.py` und zugehörige Fixtures

1. In `system-prompt.md` Titel, Selbstvorstellung und Ton-Abschnitt auf Wisdom umstellen. Kern: Orientierung schaffen, nächsten passenden Schritt nennen, nicht allwissend wirken. Die bestehenden Sicherheits-, Fakten-, Sprach- und Formatregeln bleiben inhaltlich unangetastet.
2. Alle Wiesel-, Weasel-, Tier-, „flink“, „wühlen“, „Buddy“- und Maskottchen-Bezüge entfernen. Dies gilt besonders für Beispiele, Merkzettel und Sprach-Restriktionen; ein altes Verbot für Tier-Emojis kann bleiben, wenn es produktpolitisch gewollt ist, ist aber nach Ent-Tierung logisch zu prüfen.
3. In `backend/main.py` sichtbare FastAPI-Metadaten, `DEFAULT_GREETING`, Budget-Fallback, Prompt-Fallback und Systemprompt-Lade-Fallback auf Wisdom umstellen. Der technische Fallback-Prompt bei fehlender Datei muss ebenfalls Wisdom nennen; sonst fällt das System ausgerechnet im Fehlerfall in seine Vergangenheit zurück.
4. Eval-Fälle um vier Marken-Assertions erweitern: korrekte Selbstbenennung `Wisdom`, keine Tiermetapher, keine Buddy-Anrede, Orientierungssprache ohne Besserwisserei. Bestehende Fach- und Safety-Evals unverändert mitlaufen lassen.

**Abnahme:** Lokaler Chat startet mit Wisdom; bei absichtlich fehlendem Systemprompt bleibt der serverseitige Fallback markenkonsistent. Alle vorhandenen Evals und die neuen Marken-Assertions bestehen.

## Phase 3 – Öffentliche Kommunikation, Rechtliches und Doku

**Ziel:** Produktrealität, Dokumentation und Suchvorschau erzählen dasselbe.

**Dateien:**
- Ändern: `README.md`, `STRUKTUR.md`, `BEITRÄGE.md`
- Ändern: `docs/ARCHITECTURE.de.md`, `docs/DEPLOYMENT.de.md`
- Ändern: `backend/static/docs/index.html`, `backend/static/docs/public/*.html`, `backend/static/docs/internal/*.html`, `backend/static/docs/assets/*.js`, `backend/static/docs/assets/*.css`
- Ändern: `backend/static/legal/impressum.html`, `datenschutz.html`, `barrierefreiheit.html`
- Prüfen: `backend/static/docs/public/weasel_roadmap.html` – in `wisdom_roadmap.html` umbenennen oder bewusst als historische, nicht öffentliche Datei archivieren.

1. Alle öffentlich sichtbaren Produktreferenzen zu Wisdom ändern: Titel, Navigation, Bild-Alttexte, Überschriften, Download-Namen, Footer und Begriffserklärungen.
2. Meta-Tags, Open-Graph- und JSON-LD-Angaben der Landingpage und aller öffentlich indexierbaren Seiten auf `Wisdom` setzen; `og:image` auf das finale Wisdom-OG-Asset verweisen. Alte Suchergebnisse brauchen Zeit, das ist kein Grund für hektische Magie.
3. Datenschutz, Barrierefreiheit und Impressum sorgfältig prüfen: Produktbezeichnung ersetzen, aber technische Beschreibungen, Speicherdauer, Verantwortlichkeiten und Rechtsgrundlagen nicht versehentlich umschreiben.
4. In `README.md` klar trennen: sichtbarer Produktname `Wisdom`; Repository-/Betriebsnamen dürfen bis zu einem separat geplanten Infrastruktur-Migrationsprojekt `wiesel` heißen. Das verhindert, dass ein neuer Mitwirkender die Datenbank aus ästhetischer Empörung löscht.
5. GitHub-Issue-Templates und Beitragsguide auf Wisdom umstellen, ohne Repository-URL umzubenennen. Die bestehende Repo-URL bleibt vorerst gültig.

**Abnahme:** Öffentliche Doku, Rechtstexte, Social Preview und GitHub-Onboarding enthalten keine veraltete Produktbezeichnung. Interne technische Namen sind erkennbar als interne Namen markiert.

## Phase 4 – Betriebsnamen und Reporting nur gezielt anfassen

**Ziel:** Keine sichtbaren Altbegriffe in Team-Artefakten, ohne Datenpfade oder Cronjobs blind zu brechen.

**Dateien zur Prüfung:**
- `backend/analyze.py`, `backend/eval_ton.py`, `backend/db_backup.py`
- `export_analytics.py`, `export_flagged_chats_html.py`, `clear_chat_flags.py`
- `backend/fau_news_crawler.py`, `backend/mensa_crawler.py`
- `start-wiesel.ps1`, `docker-compose.yml`, `.env.example`

1. Sichtbare Report-Titel, Konsolenmeldungen, HTML-Reporttitel und User-Agent-Kennungen auf Wisdom ändern. Datenbankdateiname, Umgebungsvariablen, Python-Modulpfade, Docker-Container und Tunnelname zunächst nicht ändern.
2. `export_flagged_chats_html.py` von tierischem Rollensymbol und Wiesel-Überschriften auf textliche Wisdom-Kennzeichnung umstellen. Dabei Datenschutz- und Zugriffsmodell nicht verändern.
3. Für Analytics und Tagesberichte nur die sichtbaren Titel sowie den GitHub-Linktext ändern; Dateiformate und Speicherpfade in dieser Runde stabil lassen.
4. Einen separaten ADR-Abschnitt in `docs/ARCHITECTURE.de.md` ergänzen: „Produktname Wisdom, technische Legacy-IDs wiesel“. Erst danach entscheiden, ob ein späteres Infrastrukturprojekt die Identifikatoren migriert.

**Abnahme:** Tagesbericht, Flag-Export, Admin-Oberfläche und Logs sind für das Team verständlich und nach außen markenkonsistent, während DB, Cron, Docker und Tunnel weiterhin laufen.

## Phase 5 – URL-, LTI- und Deployment-Migration (nur falls Wisdom-Domain beschlossen)

**Ziel:** Neue Marken-URL ohne Ausfall in StudOn bereitstellen.

**Dateien:**
- Prüfen/ändern: `backend/main.py` (`ALLOWED_ORIGINS`)
- Prüfen/ändern: `backend/.env.example`
- Prüfen/ändern: Cloudflare-Tunnel- und DNS-Konfiguration außerhalb des Repos
- Prüfen/ändern: StudOn-LTI-Tool-Konfiguration außerhalb des Repos
- Prüfen/ändern: `docs/DEPLOYMENT.de.md`

1. Neue Wisdom-Domain und TLS in Cloudflare einrichten. Backend zunächst für alte und neue Origin erlauben; in Produktion nur konkrete HTTPS-Origins setzen.
2. Neuen Launch gegen eine Test-StudOn-Instanz oder Testkurs prüfen: OAuth-Signatur, Redirect, Cookie, JWT, CORS, Chat-API und Header-Assets.
3. Erst nach bestandenem Test die Produktions-LTI-Launch-URL ändern. Alte Wiesel-URL per 301 auf die neue Zielseite weiterleiten; keine harte Abschaltung während der Mentor-Testphase.
4. Monitoring und Rollback dokumentieren: vorherige LTI-URL, vorherige Origin-Liste, DNS-/Tunnel-Referenz und ein bestätigter Rückweg.

**Abnahme:** Launch aus StudOn, direkter Browser-Aufruf und API-Chat funktionieren über die neue Domain. Alte URL leitet weiter und erzeugt keine CORS-/Cookie-Fehler.

## Abschließende Qualitätskontrolle

1. Vor Merge: `git grep -I -n -i -E 'Wiesel|Weasel|wieselflink|wühl|Tiermaskottchen'` ausführen und jeden Treffer klassifizieren: erlaubter technischer Legacy-Identifier, historische Migrationsnotiz oder Fehler. Für sichtbare Produkttexte gilt null tolerierte Treffer.
2. Syntax prüfen: `python -m py_compile backend/main.py backend/analyze.py backend/eval_ton.py export_flagged_chats_html.py`; danach bestehende Eval- und Backend-Tests ausführen.
3. Lokal mit frischer Session testen: Deutsch, Englisch, Spanisch, Chinesisch, Hindi; Startbegrüßung, Antwort, Tippstatus, Fehlerfall, Bildanhang, Sprachsteuerung, Chat-Flag und Legal-Links.
4. Vor Veröffentlichung: manuelle Prüfung von Landingpage, OG-Preview, QR-Sticker-Testscan, StudOn-Launch, Mobile Safari/Chrome und Desktop-Browser. Screenshots als Abnahmebeleg im Release-Issue sammeln.
5. Rollback: Release-Tag vor Deployment setzen; alte Assets und Konfiguration bis zur erfolgreichen Mentor-Testphase nicht löschen.

## Reihenfolge und Verantwortlichkeit

1. Brand Office + Team: Phase 0.
2. Engineering: Phasen 1 und 2 auf eigener Branch, danach lokaler Test.
3. Redaktion/Datenschutz: Phase 3 gegenlesen.
4. Engineering/Ops: Phase 4, dann optional Phase 5.
5. Team: gemeinsamer Abnahmetest und erst dann Deploy.

## Bewusste Nicht-Ziele dieser Runde

- Kein Repository-Rename und keine GitHub-URL-Migration.
- Kein Umbenennen von `wiesel.db`, `WIESEL_*`-Umgebungsvariablen, Docker-Containern oder Cloudflare-Tunneln.
- Keine Änderung am Modellanbieter, Billing oder API-Setup.
- Keine inhaltliche Erweiterung der Wissensbasis.

Diese Dinge haben alle ihre eigenen Risiken. Sie unter dem Banner „Rebranding“ mitzuziehen wäre klassisches Scope-Creep mit Lippenstift.
