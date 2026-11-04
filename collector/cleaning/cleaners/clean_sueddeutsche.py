import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_sueddeutsche(text, meta):
    """
    Cleaner for Sueddeutsche Reise articles.
    Removes breadcrumbs, audio player artifacts, and paywall footers.
    """
    
    # 1. TRIM HEADER (Standard)
    text = trim_header_by_title(text, meta.get('title'))
    
    # 2. REMOVE BREADCRUMBS
    # Pattern: "1. [Home](...) 2. [Reise](...) ..."
    lines = text.split('\n')
    cleaned_lines = []
    
    # Footer markers to stop early
    footer_markers = [
        "Weiter mit SZ Plus-Abo",
        "Das unbegrenzte Erlebnis auf SZ.de",
        "Bereits Abonnent der digitalen SZ?",
        "Jetzt testenJetzt kostenlos testen",
        "Verarbeitungszwecke",
        "Informationen auf einem Gerät speichern",
        "[Cookie-Policy]",
        "[Widerrufsbelehrung]",
        "Rechte am Artikel können Sie hier erwerben",
        "### Partnerangebote",
        "Sie haben die Wahl.",
        "Weiter mit Werbung",
        "Ich bin einverstanden",
        "Wir stellen Ihnen frei verfügbare",
        "Möchten Sie in unseren Produkten",
        "Ressorts",
        "Lokalteile",
        "Mehr von der SZ",
        "Anzeigenlinks",
        "Kontakt & Hilfe",
        "Lesen Sie mehr zum Thema",
        "Menü schließen",
        "Unsere Kernprodukte",
        "© SZ - Rechte am Artikel",
    ]
    
    skip_next = False
    
    for line in lines:
        sline = line.strip()
        
        if not sline:
            cleaned_lines.append(line)
            continue
            
        # Check Footer
        is_footer = False
        for marker in footer_markers:
             # Check if marker corresponds to the start of the line or significant part?
             # Simple substring check is usually safer for noisy HTML-to-text
            if marker in sline:
                is_footer = True
                break
        if is_footer:
            break # Stop processing lines
            
        # Breadcrumbs: "1. [Home](..."
        if re.match(r'^\d+\.\s*\[Home\]', sline) or re.match(r'^\d+\.\s*\[Reise\]', sline):
             continue
             
        # Breadcrumbs continued (2. ..., 3. ...)
        if re.match(r'^\d+\.\s*\[.*?\]\(.*?\)', sline):
             # Heuristic: if previous line was breadcrumb or this looks like nav
             continue
             
        # "Artikel anhören" block
        if "Artikel anhören" in sline or sline == "Anhören":
            continue
        if "Artikel merken" in sline or sline == "Merken":
            continue
        if "Artikel teilen" in sline or sline == "Teilen":
            continue
        if "Feedback" in sline or "Feeback" in sline: # Handle typo
            continue
        if "Artikel drucken" in sline or sline == "Drucken":
            continue
            
        # Header artifacts
        # Title usually repeats? 
        # "4. Von Après-Ski bis Wandern..." 
        if re.match(r'^\d+\.\s.*', sline) and len(sline) < 100:
             # Likely a numbered header/breadcrumb part
             continue
             
        # Repetitive Equal Signs for Title
        if re.match(r'^=+$', sline):
            continue
            
        # Clean inline noise
        if "Foto:" in sline:
            # Report shows: "Foto: SZ/Grafik"
            if len(sline) < 100:
                 continue
                 
        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)
    
    # 3. GENERAL CLEANUP
    text = remove_inline_noise(text)
    
    # 4. REMOVE MARKDOWN LINKS: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    
    # 5. REMOVE TITLE FROM BODY (if it appears)
    title = meta.get('title', '')
    if title:
        # Remove exact title match (with optional surrounding whitespace/newlines)
        text = re.sub(re.escape(title) + r'\s*\n?', '', text, count=2)  # Remove up to 2 occurrences
    
    # 6. REMOVE INLINE DATE PATTERNS (German format)
    # e.g., "18. Dezember 2025" or "15. Januar 2026"
    text = re.sub(r'\d{1,2}\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*\d{4}\s*\n?', '', text)
    
    return text.strip()
