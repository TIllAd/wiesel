# Für nicht-technische Mitarbeitende

Hier erklären wir, wie ihr zum Projekt beitragt — **ohne Git-Kenntnisse, ohne Terminal, keine Sorge.**

## FAQ aktualisieren / hinzufügen

### Option 1: Direkt im Browser (einfachste Methode)

1. Gehe zu: https://github.com/TIllAd/wiesel/tree/main/knowledge_base
2. Klick auf `faqs.json`
3. Klick auf das Bearbeiten-Symbol (Stift-Icon)
4. Füge einen neuen FAQ-Eintrag ein oder modifiziere einen bestehenden:

```json
{
  "id": "wiso-001",
  "kategorie": "Wirtschaft",
  "frage": "Was ist Marginalanalyse?",
  "antwort": "Die Marginalanalyse untersucht die Auswirkung kleinster Änderungen...",
  "quelle": "VWL-Vorlesung WS 2025",
  "schwierigkeit": "1",
  "tags": ["Wirtschaft", "Mikroökonomie"]
}
```

5. Unten: Klick „Commit changes"
6. Gib eine kurze Nachricht ein: z.B. „FAQ: Marginalanalyse hinzugefügt"
7. Klick „Commit changes"

**Fertig!** Der wiesel-Bot nutzt die neuen FAQs sofort.

### Option 2: GitHub Issue erstellen (wenn unsicher)

Wenn du unsicher bist, ob dein Text passt, erstelle stattdessen ein Issue:

1. Gehe zu: https://github.com/TIllAd/wiesel/issues
2. Klick: „New issue"
3. Wähle Template: „FAQ Update"
4. Füll die Felder aus:
   - **Kategorie**: z.B. Wirtschaft, Marketing, Recht, ...
   - **Frage**: Die Frage, die Erstsemester stellen
   - **Antwort**: Deine Antwort (gerne Links & Quellen)
   - **Quelle**: Aus welcher Vorlesung / Material kommt das?

5. Klick „Submit new issue"

**Dann kümmert sich Hermes oder das Team darum, es ins Wissenssystem zu übernehmen.**

## Einen Bug melden

Wenn etwas nicht funktioniert (falsche Antwort, Crash, etc.):

1. https://github.com/TIllAd/wiesel/issues/new?template=bug_report.md
2. Beschreib was du getan hast und was schiefging
3. Klick „Submit"

Das Team wird sich kümmern.

## Feature-Wünsche

Habt ihr Ideen, was wiesel besser machen könnte?

1. https://github.com/TIllAd/wiesel/issues/new?template=feature_request.md
2. Erklärt die Idee
3. Klick „Submit"

---

**Fragen?** Schreib an Till (til.adelmann@fau.de) oder erstelle einfach ein Issue.

Danke für eure Mitarbeit! 🙌
