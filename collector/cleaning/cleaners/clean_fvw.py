"""
FVW Cleaner
============

Cleans articles from FVW source.
German travel trade publication (fvw|TravelTalk) with massive navigation menus,
login/registration prompts, paywall blocks, and related article sections.
"""

import re


def clean_fvw(text, meta):
    """
    Cleaner for FVW articles.
    """
    if not text:
        return ""
    
    # 0. Pre-processing: Remove known garbage lines
    lines = text.split('\n')
    filtered_lines = []
    skip_until_content = True  # Skip header noise until real content
    
    for line in lines:
        sline = line.strip()
        
        # Skip empty lines at the start
        if skip_until_content and not sline:
            continue
        
        # Skip navigation menu items (German)
        if sline in ["Touristik", "Vertrieb", "Veranstalter", "Destination",
                      "Hotellerie", "Kreuzfahrt", "Verkehr", "Datenanalyse",
                      "Personalien", "Counter", "Themenwelten", "Akademie",
                      "Karriere", "Videos+Live", "Biz Travel", "Traveltech",
                      "Travel Management", "MICE", "News", "Login",
                      "Media", "Newsletter", "Jobs", "E-Paper", "Abo",
                      "Unsere Werte", "Unsere Counterwelt", "Expi-Welt",
                      "Distribution+Systeme", "KI+Daten", "Payment+Sicherheit",
                      "Travel News", "Data Analysis", "Reiseservice",
                      "Registrieren", "Passwort vergessen", "Verkauf",
                      "fvw.com"]:
            continue
            
        # Skip login prompts
        if sline in ["Passwort vergessen", "Registrieren"]:
            continue
        if "Jetzt registrieren" in sline:
            continue
        if "Jetzt anmelden" in sline:
            continue
        if "Jetzt Abo buchen" in sline:
            continue
            
        # Skip paywall/subscription blocks
        if "fvw|TravelTalk-Abo" in sline:
            continue
        if "Dieser Artikel ist exklusiv" in sline:
            continue
        if "Bereits Abonnent?" in sline:
            continue
            
        # Skip separator lines
        if re.match(r'^-{3,}$', sline):
            continue
            
        if skip_until_content and len(sline) > 50:
            skip_until_content = False
            
        if not skip_until_content:
            filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # 1. Footer Cleaning - cut at footer sections
    footer_markers = [
        "\nMehr zum Thema",
        "\n### Mehr zum Thema",
        "\nLesen Sie auch",
        "\n### Lesen Sie auch",
        "\nWeitere Artikel",
        "\n### Weitere Artikel",
        "\nDas könnte Sie auch interessieren",
        "\nMeistgelesen",
        "\n### Meistgelesen",
        "\nKommentare",
        "\n### Kommentare",
        "\nNewsletter",
        "\n### Newsletter",
        "\nUnsere Newsletter",
        "\nAnzeige",
        "\n© fvw",
        "\n© Alle Rechte",
        "\nImpressum",
        "\nDatenschutz",
        "\n1 Monat",  # Subscription pricing block
        "\nAbo buchen",
        "\n### Abo",
    ]
    
    first_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < first_idx:
            first_idx = idx
    
    text = text[:first_idx]
    
    # 2. Post-processing cleanup
    
    # Remove markdown images ![...](...) 
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    
    # Flatten links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove remaining navigation link lists (lines that are just [Text](fvw.de/...))
    text = re.sub(r'^\s*\[.*?\]\(https?://www\.fvw\.de/.*?\)\s*$', '', text, flags=re.MULTILINE)
    
    # Remove "Foto:" credit lines
    text = re.sub(r'^Foto:.*$', '', text, flags=re.MULTILINE)
    
    # Remove header separator lines (------ or ======)
    text = re.sub(r'^[-=]{3,}$', '', text, flags=re.MULTILINE)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()
