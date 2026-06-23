# Karpathy Wiki – LLM-Grundlagen

> Auszug aus https://github.com/karpathy/llm.c – Essenzielle Konzepte für das Verständnis von Sprachmodellen

## Was sind Sprachmodelle?

Ein Sprachmodell ist ein System, das lernt, Wahrscheinlichkeitsverteilungen über Sequenzen von Worten/Tokens zu modellieren.

**Mathematik:**
```
P(w₁, w₂, w₃, ..., wₙ) = P(w₁) × P(w₂|w₁) × P(w₃|w₁,w₂) × ...
```

Das heißt: Die Wahrscheinlichkeit einer Sequenz ist das Produkt aus **bedingten Wahrscheinlichkeiten**. Ein gutes Sprachmodell lernt, P(wᵢ|w₁...wᵢ₋₁) gut zu schätzen.

## Transformer & Attention

Transformer sind die Grundlage moderner LLMs. Statt RNNs (sequenziell, langsam) nutzen sie **Self-Attention**:

**Attention-Formel:**
```
Attention(Q, K, V) = softmax(Q·Kᵀ/√dₖ) · V
```

- **Q (Query)**: Was soll ich aufmerksam machen?
- **K (Key)**: Wo sind die wichtigen Informationen?
- **V (Value)**: Welche Informationen extrahiere ich?

Das ermöglicht **Parallelisierung**: Alle Tokens gleichzeitig verarbeiten, nicht sequenziell.

## Training & Loss

Sprachmodelle werden mit **Cross-Entropy Loss** trainiert:

```
L = -Σ log P(wᵢ|w₁...wᵢ₋₁)
```

Der Loss ist einfach: Für jede Position vorherzusagen, welches Token kommt. Das Netzwerk lernt dabei implizit Grammatik, Wissen, Logik.

## Tokens & Tokenisierung

Text wird in **Tokens** zerlegt (nicht einfach Wörter!):

- "Hello" → [72, 101, 108, 108, 111] (Character-level)
- "Hello" → [18435] (Subword, z.B. BPE)

Subword-Tokenizer (BPE, WordPiece, SentencePiece) sind Standard — sie balancieren Vocab-Größe mit Effizienz.

## Embedding Space

Tokens werden zu Vektoren (Embeddings) transformiert:

```
token_id → embedding (z.B. 768-dimensional)
```

Im Embedding Space liegen semantisch ähnliche Wörter nah beieinander. Das ermöglicht Transfer Learning.

## Decoding Strategien

Nach dem Training muss das Modell **generieren**. Strategien:

1. **Greedy Decoding**: Wähle immer das wahrscheinlichste Token
   - Schnell, aber wiederholend

2. **Temperature Sampling**: Stochastisch samplen, Temperatur regelt Kreativität
   - Temp = 0.1 → eher vorhersehbar
   - Temp = 1.0 → normal
   - Temp = 2.0 → chaotisch/kreativ

3. **Top-K Sampling**: Sample nur aus Top-K wahrscheinlichsten Tokens
   - Verhindert sehr unwahrscheinliche Token

4. **Nucleus (Top-P) Sampling**: Sample aus den wahrscheinlichsten Tokens, bis P% der Wahrscheinlichkeit erreicht
   - Beste Praxis derzeit

## Skalierung & Scaling Laws

Empirisch gilt (Chinchilla, Kaplan et al.):

```
Loss ∝ (1/N^α) + (1/C^β)
```

- **N**: Trainingstoken
- **C**: Modellparameter (Größe)
- **α ≈ 0.07, β ≈ 0.8**

Das bedeutet: Größere Modelle mit mehr Daten trainieren ist fast immer besser. Optimal ist **gleich viele Token wie Parameter** (≈ 20 Token pro Parameter).

## Context Window & Positional Encoding

Sprachmodelle können nur eine begrenzte Länge auf einmal verarbeiten (**Context Window**). Größere = teurer, aber flexibler.

**Positional Encoding**: Tokens ihre Position mitteilen. Frühe Ansätze:
- Sinusoidale Funktionen (Transformer Original)
- Gelernte Embeddings
- RoPE (Rotary Position Embeddings) — Modern, zoombar

## RAG & Retrieval-Augmented Generation

Sprachmodelle haben **keine** persistent updatbaren Speicher. Daher RAG:

1. **Retrieval**: Gegeben Query, finde relevante Dokumente
2. **Augmentation**: Hänge diese Dokumente an die Query
3. **Generation**: Modell generiert Antwort basierend auf diesen Kontextdokumenten

Das ist genau das, was **wiesel** tut!

## In-Context Learning

Sprachmodelle können aus Beispielen **im Prompt** lernen, ohne neu trainiert zu werden:

```
Translate English to German:
English: Hello
German: Hallo

English: Good morning
German: Guten Morgen

English: How are you?
German:
```

Das Modell schließt: "Ah, ich soll übersetzen" und gibt "Wie geht es dir?" aus.

Die Fähigkeit ist abhängig von Modellgröße und Prompt-Design.

## Zusammenfassung für wiesel

Für einen Studienbegleiter-Bot sind die wichtigsten Konzepte:

1. **Tokenisierung**: Text richtig zerlegen
2. **Embedding Space**: Ähnliche FAQs im Vektorraum nah beieinander
3. **RAG**: Mit lokalen FAQs + Karpathy Wiki augmentieren
4. **In-Context Learning**: User-Query + relevante Docs = bessere Antwort
5. **Decoding**: Top-P Sampling für konsistente, aber nicht-robotische Antworten

---

**Für tieferes Verständnis:**
- https://github.com/karpathy/llm.c – Minimale LLM-Implementierung
- https://transformer-circuits.pub/ – Interpretability
- https://arxiv.org/abs/2005.14165 – Original Transformer-Paper
