
import re
from datetime import datetime
from .utils import trim_header_by_title, remove_inline_noise

def clean_spiegel(text, meta):
    """
    Cleaner for Spiegel Reise articles (Markdown input).
    Removes massive navigation menus, paywall banners, and images (Markdown & HTML).
    """
    
    # 0. DATE FIX
    # -------------------------------------------------------------------------
    # Parse "Sat, 29 Nov 2025 07:41:00 +0100" manually if needed
    if 'published' in meta:
        pub = meta['published']
        if isinstance(pub, str) and ',' in pub and '+' in pub:
            try:
                # Remove day name "Sat, "
                clean_pub = pub.split(',', 1)[1].strip() # "29 Nov 2025 07:41:00 +0100"
                # Try the full timestamp first, including timezone.
                dt = datetime.strptime(clean_pub, "%d %b %Y %H:%M:%S %z")
                meta['published'] = dt.isoformat() 
                # get_best_date handles iso format well
            except Exception as e:
                pass

    # 0.1 TEXT-BASED TAG EXTRACTION
    # -------------------------------------------------------------------------
    # Spiegel metadata often missing tags, but they are present in footer: "### Mehr lesen über"
    if "### Mehr lesen über" in text:
        try:
            # Split and look at the part AFTER the marker
            parts = text.split("### Mehr lesen über", 1)
            if len(parts) > 1:
                tag_section = parts[1]
                extracted_tags = []
                
                # Regex for markdown link: [Text](URL...)
                for line in tag_section.split('\n'):
                    sline = line.strip()
                    if not sline: 
                        continue
                        
                    if sline.startswith("###") or sline.startswith("Menü") or sline.startswith("AUDIO_Player"):
                        break
                        
                    # Check for link
                    # [Text](...)
                    match = re.match(r'^\s*\[(.*?)\]\(.*?\)', sline)
                    if match:
                        t = match.group(1).strip()
                        if t and t not in extracted_tags:
                            extracted_tags.append(t)
                    else:
                        # Sometimes there's noise or plain text. 
                        # Spiegel tags are usually a list of links.
                        pass
                        
                if extracted_tags:
                    current_tags = meta.get('tags') or []
                    for t in extracted_tags:
                        if t not in current_tags:
                            current_tags.append(t)
                    meta['tags'] = current_tags
        except Exception:
            pass

    # 1. REMOVE IMAGES (Markdown & HTML)
    # -------------------------------------------------------------------------
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Use DOTALL to match multiline tags
    text = re.sub(r'<img.*?>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # 2. FILTER ALL LINES (Aggressive Noise Removal)
    # -------------------------------------------------------------------------
    # Scan every line and drop it if it matches known noise.
    
    lines = text.split('\n')
    cleaned_lines = []
    
    noise_patterns = [
        r'^\[Zum Inhalt springen\]',
        r'^\* \[.*?\]\(.*?\)', # List items with links (Nav menu)
        r'^\[.*?\]\(.*?\)$',   # Isolated links
        r'^\s*Menü\s*$',
        r'^\s*Menü .* aufklappen$', # Footer menus
        r'^\s*\+ \[.*?\]\(.*?\)$', # Footer menu items (+ [Link])
        r'^\s*Suche (starten|öffnen)\s*$',
        r'^\s*-\s*EILMELDUNG\s*—\s*$',
        r'^\s*[\* ]*Link kopieren\s*$',
        r'^\s*[\* ]*Zur Merkliste hinzufügen\s*$',
        r'^\s*[\* ]*Weitere Optionen zum Teilen\s*$',
        r'^\s*\\_\\_proto\\_.*\\_\\_$', # Escaped proto
        r'^\s*__proto_.*__$',
        r'^\s*•\s*$',
        r'^\s*Foto:.*$',
        r'^Bild vergrößern$',
        r'^\s*[\* ]*\[Facebook\]',
        r'^\s*[\* ]*\[E-Mail\]',
        r'^\s*[\* ]*\[X\.com\]',
        r'^\s*[\* ]*\[Messenger\]',
        r'^\s*[\* ]*\[WhatsApp\]',
        r'^\d+ (Sekunden|Minuten) (zurück|vor)$',
        r'^Stummschalten$',
        r'^Stummschaltung aufheben$',
        r'^Dialog schließen$',
        r'^Hinweis schließen$',
        r'^Audio Player.*$',
        r'^Wiedergabegeschwindigkeit ändern$',
        r'^Wiedergabe.*$',
        r'^SPIEGEL plus$',
        r'^Nur für Neukunden$',
        r'^€ \d+.*$',
        r'^danach € \d+.*$',
        r'^Freier Zugriff auf alle S\+-Artikel.*$',
        r'^Jederzeit kündigen$',
        r'^52 Wochen.*$',
        r'^Sie haben bereits ein Print-Abo\?$',
        r'^Sie haben bereits ein Digital-Abo\?$',
        r'^### Jetzt Artikel freischalten:$',
        r'^Zum Login$',
        r'^Monatsabo Preis wird geladen\.*$',
        r'^Jahresabo Preis wird geladen\.*$',
        r'^Jetzt abonnieren$',
        r'^iTunes-Abo wiederherstellen$',
        r'^\d+ % sparen$',
        r'^einen Monat zum Preis von.*$',
        r'^ein Jahr zum Preis von.*$',
        r'^dieser App zu nutzen, müssen Sie.*$',
        r'^von \d+ Artikeln verfügbar$',
        r'^Artikel freischalten$',
    ]
    
    paywall_triggers = [
        "In Ihrem SPIEGEL+ Starter-Abo stehen Ihnen",
        "Die nächsten 4 freien Artikel stehen Ihnen",
        "Trotzdem weiterlesen?",
        "Jetzt zum Premium-Abo upgraden!",
        "### Premium-Abo Exklusiv für Sie!",
        "### Diesen Artikel weiterlesen mit SPIEGEL+",
        "Vierwöchentlich abgerechnet und kündbar.",
        "Starter-Abonnent:innen sparen",
        "Alle Artikel auf SPIEGEL.de und App lesen",
        "Wöchentlich die digitale Ausgabe des SPIEGEL",
        "Artikel freischalten?",
        "Sie unsere Allgemeinen Geschäftsbedingungen",
        "[Allgemeinen Geschäftsbedingungen]",
        "[Zu meinen Artikeln]",
        "[Datenschutzerklärung]",
        "Eine Zusammenfassung dieses Artikels wurde mit Hilfe von künstlicher Intelligenz erstellt",
        "Helfen Sie uns, besser zu werden",
        "Haben Sie einen Fehler im Text gefunden",
        "Sie haben weiteres inhaltliches Feedback",
        "Mehrfachnutzung erkannt",
        "Die gleichzeitige Nutzung von SPIEGEL",
        "Auf diesem Gerät weiterlesen",
        "Sie möchten SPIEGEL+ auf mehreren Geräten",
        "Sie haben bereits ein Digital-Abo?",
        "© ", # Copyright lines
        "Menü Services aufklappen",
        "Monatsabo Preis wird geladen",
        "Jahresabo Preis wird geladen",
        "Zugang zu allen Artikeln in der App",
        "Wöchentliche Ausgabe des SPIEGEL",
        "Jederzeit kündbar",
        "Jetzt abonnieren",
        "iTunes-Abo wiederherstellen",
        "SPIEGEL+ wird über Ihren iTunes-Account",
        "Sie können den Artikel leider nicht mehr aufrufen",
    ]
    
    # 3. Footer Cut-off
    # -------------------------------------------------------------------------
    footer_markers = [
        "### Mehr lesen über",
        "### Verwandte Artikel",
        "Menü Politik aufklappen", # Usually the start of big footer
        "Menü Services aufklappen",
    ]
    
    # 3. Footer Cut-off
    # -------------------------------------------------------------------------
    footer_markers = [
        "### Mehr lesen über",
        "### Verwandte Artikel",
        "Menü Politik aufklappen", # Usually the start of big footer
        "Menü Services aufklappen",
    ]
    
    # Pre-compile regexes for speed
    noise_regexes = [re.compile(p, re.IGNORECASE) for p in noise_patterns]
    
    # Stubborn strings to check via simple substring (more robust than regex anchors)
    bad_substrings = [
        "einen Monat zum Preis von",
        "ein Jahr zum Preis von",
        "dieser App zu nutzen, müssen Sie",
        "von 4 Artikeln verfügbar", # Dynamic number
        "freischalten", # risky? "Artikel freischalten" is the button.
        "Zum Inhalt springen",
        "Hier rabattiert Digital-Zugang bestellen",
        "Allgemeinen Geschäftsbedingungen und Datenschutzerklärung",
        "Zu meinen Artikeln",
        "Jetzt upgraden",
    ]
    
    # Specific Intro Navigation Items (Plain text or Linked)
    # These often appear at the very top.
    nav_items = [
        "News", "Ticker", "Magazin", "Audio", "Account",
        "Startseite", "Reise", "Fernweh", "Messenger", "WhatsApp", 
        "Facebook", "X.com", "E-Mail", "TUI", "A3M"
    ]
    
    # 4. LINE SCAN (Filter Noise)
    # -------------------------------------------------------------------------
    # Although mixed approaches work best.
    
    # a. Remove horizontal rules
    text = re.sub(r'^\s*[*_-]{3,}\s*$', '', text, flags=re.MULTILINE)

    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        sline = line.strip()
        
        # Check Footer markers
        hit_footer = False
        for marker in footer_markers:
            if marker in sline:
                hit_footer = True
                break
        if hit_footer:
            break # STOP collecting lines
            
        if not sline:
            cleaned_lines.append(line)
            continue
            
        # Check Regex Noise
        is_noise = False
        for regex in noise_regexes:
            if regex.match(sline):
                is_noise = True
                break
        
        # Special case: "Artikel anhören"
        if "Artikel anhören" in sline or "Audio Player" in sline:
            is_noise = True
            
        # Special case: Repetitive Headers ====
        if re.match(r'^=+$', sline):
             is_noise = True

        # Remove list item title if it matches metadata title
        title = meta.get('title', '')
        if title and sline.startswith('* ') and title in sline:
            is_noise = True
        
        # Explicit Nav Items (handling both "* Item" and "* [Item](url)")
        for item in nav_items:
            # Check "* Item"
            if sline == f"* {item}":
                is_noise = True
                break
            # Check "* [Item" (start of link)
            if sline.startswith(f"* [{item}"):
                is_noise = True
                break
            
        if is_noise:
            continue
            
        # Check String Triggers (Paywall/Footer)
        for trigger in paywall_triggers:
            if trigger in sline:
                is_noise = True
                break
        if is_noise:
            continue
            
        # Check bad substrings
        for bad in bad_substrings:
            if bad in sline:
                is_noise = True
                break
        if is_noise:
            continue
            
        # Twitter/Social specific
        if "* X.com" in sline or "* Facebook" in sline or "* E-Mail" in sline:
            continue
            
        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)

    # 5. GLOBAL FORMATTING (Post-Filter)
    # -------------------------------------------------------------------------
    text = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', text)

    # Final whitespace cleanup
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    
    # 5. SUMMARY FALLBACK
    # -------------------------------------------------------------------------
    # Spiegel Paywall often leaves 0-200 chars.
    if len(text) < 400: # Heuristic threshold
        summary = meta.get('description', '') or ''
        if summary and len(summary) > len(text):
             # (Sometimes summary is just "Description"?)
             # Return just summary is cleaner for RAG.
             return f"{summary}\n\n[Content Paywalled - Summary Used]"
    
    return text
