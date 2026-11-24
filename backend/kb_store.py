"""Wissensbasis auf der Platte: Ort, Metadaten, Prüfungen, Prompt-Text.

Reine Dateilogik ohne FastAPI/DB, damit sie leicht testbar bleibt.

Jede Wissensbasis-Datei kann oben einen kleinen Kopfbereich tragen, den das
Team im Editor pflegt und der NICHT an das Sprachmodell geht:

    ---
    verantwortlich: Studienbüro WiSo
    pruefen_bis: 2027-03-31
    ---
    # Titel
    ...
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Automatisch erzeugte Dateien (Crawler auf der VM). Sie sind im Editor nur
# lesbar und werden nicht mehr an WiSdom gegeben, wenn sie zu alt sind –
# lieber gar keine Info als ein Mensaplan von letzter Woche.
AUTO_FILES = {
    "mensa-woche.md": "Mensa diese Woche",
    "wetter-heute.md": "Wetter heute",
    "oepnv-heute.md": "ÖPNV heute",
    "fau-aktuell.md": "FAU Aktuell",
}
AUTO_MAX_AGE_HOURS = int(os.getenv("KB_AUTO_MAX_AGE_HOURS", "48"))
# Verhalten von WiSdom (System-Prompt, Zusatzregeln). Liegen im Wissensbasis-Ordner
# unter _wisdom/, gehören aber NICHT zur Faktenbasis; main.py baut sie in den Prompt.
BEHAVIOR_FILES = {
    "_wisdom/system-prompt.md": "System-Prompt: Persönlichkeit, Ton, Grenzen",
    "_wisdom/regeln.md": "Zusatzregeln für bestimmte Themen",
}
BEHAVIOR_MIN_CHARS = {"_wisdom/system-prompt.md": 500, "_wisdom/regeln.md": 0}
SOON_DAYS = 30
LARGE_FILE_CHARS = 25_000
META_KEYS = ("verantwortlich", "pruefen_bis")

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_SOURCE_RE = re.compile(r"^\s*[-*]?\s*\**(?:Quelle|Website|Webseite|Offizielle Seite)\**\s*:?\**:?\s*(?:<)?(https?://[^\s>)\]]+)", re.I | re.M)
_URL_RE = re.compile(r"https?://[^\s)>\]}\"'`]+", re.I)
# Platzhalter in GROSSBUCHSTABEN wie [LINK ZUR SEITE] – nicht normale Links [Text](url).
_PLACEHOLDER_RE = re.compile(
    r"\[(?:LINK|TODO|XXX|PLATZHALTER|EINFÜGEN|EINFUEGEN|NAME|DATUM)\b[^\]]*\](?!\()"
    r"|\bTODO\b|\bXXX\b|(?i:lorem ipsum)"
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ── Ort ──────────────────────────────────────────────────────────────────────

def kb_dir() -> Optional[Path]:
    """Wo liegt die Wissensbasis? WISDOM_KB_DIR gewinnt (Betrieb auf der VM,
    außerhalb des Git-Checkouts), sonst die bekannten Orte im Repo/Container."""
    env = os.getenv("WISDOM_KB_DIR", "").strip()
    candidates = [Path(env)] if env else []
    candidates += [
        Path(__file__).parent.parent / "knowledge_base",
        Path("/knowledge_base"),
        Path("/app/knowledge_base"),
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return None


def md_files(base: Path) -> list[Path]:
    return sorted(
        (p for p in base.glob("**/*.md") if not any(part.startswith((".", "_")) for part in p.relative_to(base).parts)),
        key=lambda p: str(p.relative_to(base)).lower(),
    )


def rel(base: Path, path: Path) -> str:
    return path.relative_to(base).as_posix()


def safe_path(base: Path, relative: str) -> Path:
    """Relativen Pfad prüfen: nur .md, keine versteckten Teile, im KB-Ordner."""
    relative = (relative or "").strip().replace("\\", "/").lstrip("/")
    if relative in BEHAVIOR_FILES:
        return (base / relative).resolve()
    if not relative.endswith(".md"):
        raise ValueError("Nur Markdown-Dateien (.md) sind erlaubt.")
    parts = relative.split("/")
    if any(not p or p.startswith((".", "_")) or p == ".." for p in parts):
        raise ValueError("Ungültiger Dateipfad.")
    target = (base / relative).resolve()
    target.relative_to(base.resolve())  # ValueError bei Ausbruch
    return target


def folders(base: Path) -> list[str]:
    out = sorted(
        rel(base, p) for p in base.glob("**/") if p != base
        and not any(part.startswith((".", "_")) for part in p.relative_to(base).parts)
    )
    return [""] + out


def slugify(text: str) -> str:
    text = text.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = text.replace("Ä", "ae").replace("Ö", "oe").replace("Ü", "ue")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:60] or "neue-datei"


def is_behavior(relative: str) -> bool:
    return relative in BEHAVIOR_FILES


def ensure_behavior_files(base: Path, defaults: dict) -> None:
    """Fehlende Verhaltens-Dateien einmalig mit dem Startstand aus dem Repo anlegen."""
    for relative, text in defaults.items():
        target = base / relative
        if not target.exists() and text:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def behavior_body(base: Optional[Path], relative: str, overrides: Optional[dict] = None) -> Optional[str]:
    """Text einer Verhaltens-Datei (Entwurf aus overrides gewinnt) oder None."""
    if overrides and relative in overrides and overrides[relative] is not None:
        return parse(overrides[relative])[1].strip()
    if not base:
        return None
    try:
        return parse((base / relative).read_text(encoding="utf-8"))[1].strip()
    except OSError:
        return None


def is_auto(relative: str) -> bool:
    return "/" not in relative and relative in AUTO_FILES


# ── Kopfbereich ──────────────────────────────────────────────────────────────

def parse(text: str) -> tuple[dict, str]:
    """(Metadaten, Inhalt ohne Kopfbereich)."""
    text = text or ""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    return meta, text[match.end():]


def compose(meta: dict, body: str) -> str:
    lines = [f"{k}: {str(meta.get(k) or '').strip()}" for k in META_KEYS if str(meta.get(k) or "").strip()]
    extra = [f"{k}: {v}" for k, v in meta.items() if k not in META_KEYS and str(v).strip()]
    body = (body or "").replace("\r\n", "\n").lstrip("\n")
    if not body.endswith("\n"):
        body += "\n"
    if not lines and not extra:
        return body
    return "---\n" + "\n".join(lines + extra) + "\n---\n" + body


def parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"„{value}“ ist kein gültiges Datum (erwartet z. B. 2027-03-31).")


def title_of(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def source_url(body: str) -> Optional[str]:
    match = _SOURCE_RE.search(body or "")
    return match.group(1).rstrip(".,;:") if match else None


def urls(body: str) -> list[str]:
    seen = []
    for match in _URL_RE.finditer(body or ""):
        url = match.group(0).rstrip(".,;:!?*")
        if url not in seen:
            seen.append(url)
    return seen


# ── Status & Prüfungen ───────────────────────────────────────────────────────

def review_status(meta: dict, today: Optional[date] = None) -> str:
    """ok | bald | abgelaufen | kein-datum | ungueltig"""
    today = today or date.today()
    try:
        due = parse_date(meta.get("pruefen_bis", ""))
    except ValueError:
        return "ungueltig"
    if due is None:
        return "kein-datum"
    if due < today:
        return "abgelaufen"
    if due <= today + timedelta(days=SOON_DAYS):
        return "bald"
    return "ok"


def auto_is_fresh(path: Path, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    try:
        age = now - datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return False
    return age <= timedelta(hours=AUTO_MAX_AGE_HOURS)


def check(meta: dict, body: str, today: Optional[date] = None, relative: str = "") -> list[dict]:
    """Prüfungen beim Speichern. level=fehler blockiert, hinweis nicht."""
    today = today or date.today()
    issues: list[dict] = []

    def add(level, text):
        issues.append({"level": level, "text": text})

    if is_behavior(relative):
        minimum = BEHAVIOR_MIN_CHARS.get(relative, 0)
        if minimum and len((body or "").strip()) < minimum:
            add("fehler", f"Der System-Prompt ist zu kurz (unter {minimum} Zeichen) – vermutlich wurde versehentlich zu viel gelöscht.")
        placeholders = sorted({m.group(0) for m in _PLACEHOLDER_RE.finditer(body or "")})
        if placeholders:
            add("hinweis", "Platzhalter gefunden: " + ", ".join(placeholders[:5]))
        return issues

    if len((body or "").strip()) < 20:
        add("fehler", "Die Datei ist (fast) leer. Zum Entfernen bitte „Löschen“ verwenden.")
    try:
        due = parse_date(meta.get("pruefen_bis", ""))
    except ValueError as e:
        add("fehler", str(e))
        due = None
    else:
        if due is None:
            add("hinweis", "Kein „Prüfen bis“-Datum gesetzt – niemand wird erinnert, wenn die Infos veralten.")
        elif due < today:
            add("hinweis", f"Das „Prüfen bis“-Datum ({due:%d.%m.%Y}) liegt in der Vergangenheit.")
    if not (meta.get("verantwortlich") or "").strip():
        add("hinweis", "Keine verantwortliche Person/Stelle eingetragen.")
    if not any(line.startswith("# ") for line in (body or "").splitlines()):
        add("hinweis", "Keine Überschrift (Zeile mit „# “ am Anfang) – die erste Überschrift ist der Titel.")
    placeholders = sorted({m.group(0) for m in _PLACEHOLDER_RE.finditer(body or "")})
    if placeholders:
        add("hinweis", "Platzhalter gefunden: " + ", ".join(placeholders[:5]))
    if not source_url(body):
        add("hinweis", "Keine Zeile „Quelle: https://…“ – dann kann WiSdom nicht auf die offizielle Seite verweisen und Änderungen an der Quelle werden nicht erkannt.")
    if len(body or "") > LARGE_FILE_CHARS:
        add("hinweis", f"Sehr lange Datei ({len(body):,} Zeichen). Jede Anfrage schickt die ganze Wissensbasis mit – lange Dateien kosten bei jedem Chat Geld.".replace(",", "."))
    return issues


# ── Prompt ───────────────────────────────────────────────────────────────────

def prompt_content(base: Path, overrides: Optional[dict] = None, now: Optional[datetime] = None) -> tuple[str, list[str]]:
    """Text, der an WiSdom geht, plus Liste übersprungener Auto-Dateien.

    overrides: {relativer_pfad: voller_dateitext | None} für Probe-Antworten mit
    ungespeichertem Entwurf (None = Datei weglassen).
    """
    overrides = overrides or {}
    parts, skipped = [], []
    seen = set()
    for path in md_files(base):
        relative = rel(base, path)
        seen.add(relative)
        if relative in overrides:
            text = overrides[relative]
            if text is None:
                continue
        else:
            if is_auto(relative) and not auto_is_fresh(path, now):
                skipped.append(relative)
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
        _, body = parse(text)
        if body.strip():
            parts.append(body.strip())
    for relative, text in overrides.items():
        if relative not in seen and text and not is_behavior(relative):
            _, body = parse(text)
            if body.strip():
                parts.append(body.strip())
    return "\n\n---\n\n".join(parts), skipped


def signature(base: Path) -> tuple:
    """Ändert sich, sobald eine Datei geändert wird oder eine Auto-Datei veraltet."""
    out = []
    for path in md_files(base):
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            continue
        relative = rel(base, path)
        fresh = auto_is_fresh(path) if is_auto(relative) else True
        out.append((relative, mtime, fresh))
    return tuple(out)


def describe(base: Path, path: Path, today: Optional[date] = None) -> dict:
    relative = rel(base, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse(text)
    stat = path.stat()
    if is_behavior(relative):
        return {"path": relative, "folder": "_wisdom", "title": BEHAVIOR_FILES[relative], "auto": False,
                "behavior": True, "chars": len(body), "mtime": stat.st_mtime, "verantwortlich": "",
                "pruefen_bis": "", "quelle": None, "status": "verhalten"}
    auto = is_auto(relative)
    info = {
        "path": relative,
        "folder": relative.rsplit("/", 1)[0] if "/" in relative else "",
        "title": AUTO_FILES.get(relative) if auto else title_of(body, path.stem),
        "auto": auto,
        "chars": len(body),
        "mtime": stat.st_mtime,
        "verantwortlich": meta.get("verantwortlich", ""),
        "pruefen_bis": meta.get("pruefen_bis", ""),
        "quelle": source_url(body),
        "behavior": False,
    }
    if auto:
        info["status"] = "auto-aktuell" if auto_is_fresh(path) else "auto-veraltet"
    else:
        info["status"] = review_status(meta, today)
    return info
