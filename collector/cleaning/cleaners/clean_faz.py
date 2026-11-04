import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_faz(text, meta):
    """
    Basic cleaner for FAZ (Frankfurter Allgemeine Zeitung).
    """
    if not text:
        return ""
        
    # 1. Stripping Links (General cleanup)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', text) # Remove images
    text = re.sub(r'(?<!\!)\[([^\]]*)\]\([^\)]*\)', r'\1', text) # Remove links but keep text
    text = re.sub(r'https?://\S+', '', text) # Remove naked URLs

    # 2. Aggressive Header Trim
    # Strategy: Find the TITLE. If found, cut everything before it.
    # If not found, use known "End of Menu" markers.
    
    lines = text.split('\n')
    start_idx = 0
    title = meta.get('title', '').strip()
    
    # A. Search for Title (Best Method)
    if title:
        norm_title = title.lower().replace(' ', '')
        
        for i, line in enumerate(lines[:300]):
            norm_line = line.strip().lower().replace(' ', '')
            # Check meaningful match
            if norm_title in norm_line and len(norm_line) < len(norm_title) + 50:
                start_idx = i
                # But sometimes there is an author line right after.
                break
                
    # B. Fallback: Structural Markers (If Title not found)
    if start_idx == 0:
        end_of_nav_markers = [
            "Sonntagszeitung E-Paper",
            "Direkt zum Hauptinhalt",
            "F.A.Z. Kiosk App",
            "Zeitung Edition",
            "Zuletzt gelesen Ihre gelesenen Beiträge im", # From user feedback
            "Überblick" # End of the user menu
        ]
        
        last_marker_idx = -1
        # Scan deeper for massive menus
        for i, line in enumerate(lines[:400]): 
            sline = line.strip()
            # Check for exact match or suffix match for high confidence markers
            if sline == "Überblick" and i > 0 and "Zuletzt gelesen" in lines[i-1]:
                last_marker_idx = i
            elif any(m in line for m in end_of_nav_markers):
                last_marker_idx = i
        
        if last_marker_idx != -1:
            start_idx = last_marker_idx + 1
            
    # Apply trim
    text = '\n'.join(lines[start_idx:])

    # Remove top functional links often found after the title
    lines = text.split('\n')
    clean_lines = []
    
    # Specific interactive menu items to skip
    skip_exact = {
        "- Anhören", "- Merken", "- Teilen", "- Verschenken", "- Drucken", 
        "- Zur App", "- Zusammenfassung", "Verlagsangebot", "Zum Stellenmarkt\")", 
        "Zurück", "Vor"
    }

    # Footer/Paywall Triggers (Hard Stop)
    # Simplify triggers to avoid Markdown mismatches (e.g. ignore * or ###)
    footer_triggers = [
        "Mehr zum Thema",
        "© Frankfurter Allgemeine Zeitung",
        "Alle Rechte vorbehalten",
        "Stellenmarkt",
        "Frankfurter Allgemeine Zeitung", # Often appears in footer block
        "Zugang zu allen FAZ+ Beiträgen", # Simplified
        "Gesünder kochen",
        "Mit einem Klick online kündbar", # Simplified
        "Das Beste von FAZ+",
        "WEITER",
        "Login"
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Check Footer Triggers
        # If it appears as a full line "Frankfurter Allgemeine Zeitung", it's footer.
        if any(trig in sline for trig in footer_triggers):
            # HIT: The article ended. Stop everything.
            break
            
        # Hard stop on FAZ+ line if it looks like a separator
        if sline == "FAZ+" or sline == "#### FAZ+":
             break
        
        # Also catch the "#### FAZ+ Title" pattern which is cross-promotion
        if "#### FAZ+" in sline:
            break

        if sline in skip_exact:
            continue
            
        clean_lines.append(line)
        
    text = '\n'.join(clean_lines)
    
    # 4. Inline Noise
    text = remove_inline_noise(text)
    
    return text.strip()
