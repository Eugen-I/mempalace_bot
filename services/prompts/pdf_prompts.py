PDF_CHUNK_PROMPT = """Du analysierst einen Teil eines Dokuments.

WICHTIGE PRÄZISIONSREGELN:
- Gib ALLE Zahlen, Beträge, Daten, Prozentangaben exakt wieder
- Bei medizinischen Werten: Diagnosen, Medikamente, Dosierungen, Laborwerte originalgetreu
- Bei Finanzdokumenten: Euro-Beträge, Kontostände, Zinsen, Gebühren genau notieren
- Keine Rundung, keine Schätzung, keine Approximation
- Deutsche Fachbegriffe und Eigennamen im Original lassen
- Strukturierte Auflistung der wichtigsten Fakten aus diesem Abschnitt"""

PDF_COMBINE_PROMPT = """Du fasst mehrere Teilanalysen eines Dokuments zu einer einzigen Analyse zusammen.  # noqa: E501

KRITISCHE REGELN FÜR GENAUIGKEIT:
1. Alle Zahlen, Beträge, Prozentsätze, Daten MÜSSEN exakt aus den Teilanalysen übernommen werden
2. Medizinische Diagnosen, Medikamente, Dosierungen, Laborwerte — kein Detail darf fehlen
3. Finanzielle Angaben (Kontostände, Überweisungen, Zinsen, Gebühren) originalgetreu
4. Keine Informationen hinzufügen oder weglassen
5. Bei Widersprüchen zwischen Teilanalysen: beide Versionen nebeneinander nennen
6. Deutsche Begriffe beibehalten

Teilanalysen:
{chunks}

Erstelle eine vollständige, sauber strukturierte Gesamtanalyse."""
