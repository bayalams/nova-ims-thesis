
import re
from .utils import trim_header_by_title, remove_inline_noise

def extract_zeit_tags(text):
    """
    Extracts tags from the footer list in Die Zeit articles.
    Pattern: Lines starting with '* ' inside the footer area.
    Example: 
    * Oberbayern,
    * Mittelfranken,
    """
    tags = []
    # Look for the tag block, usually usually near "Aktuelle Themen" or just lists at the end.
    
    # Strategy: Find lines starting with '* ' followed by text and an optional comma
    
    footer_text = text[-3000:]
    
    # Pattern: * TagName,
    matches = re.findall(r'^\*\s+(.+?)(?:,)?\s*$', footer_text, flags=re.MULTILINE)
    
    for m in matches:
        # Filter out UI links usually present in these lists
        tag = m.strip()
        if 'Aktuelle Themen' in tag or 'Facebook' in tag or 'WhatsApp' in tag or 'http' in tag:
            continue
        
        # Filter out GDPR/Cookie consent garbage often formatted as list items
        # Real tags are usually short keywords. GDPR text is long sentences.
        if len(tag) > 60:
            continue
            
        if 'Informationen' in tag or 'Zustimmen' in tag or 'Verarbeitung' in tag:
            continue

        # Filter out Emoji-only tags or tags starting with emojis
        if not re.search(r'[a-zA-ZäöüÄÖÜß0-9]', tag):
            continue

        # Remove trailing comma if captured
        if tag.endswith(','):
            tag = tag[:-1]
        
        if tag:
            tags.append(tag)
            
    return list(set(tags))

def clean_die_zeit(text, meta):
    """
    Cleaner for Die Zeit (DIE_ZEIT).
    Removes German UI elements, cookie banners, newsletters, and agency credits.
    """
    
    # 1. Header Cleaning
    # Remove standard UI keywords often found at the very top
    header_noise = [
        r'^Benachrichtigung\s*$',
        r'^Pfeil nach links\s*$',
        r'^Pfeil nach rechts\s*$',
        r'^Merkliste\s*$',
        r'^Aufklappen\s*$',
        r'^Kommentare\s*$',
        r'^Abspielen\s*$',
        r'^Pause\s*$',
        r'^Wiederholen\s*$',
        r'^Zum Inhalt springen.*',
        r'^\[Zum Inhalt springen\].*'
    ]
    
    for pat in header_noise:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.MULTILINE)
        
    # Remove "Aktuelles" navigation block often appearing before title
    # [Schlagzeilen](...) \n ---------------- \n Aktuelles
    text = re.sub(r'\[Schlagzeilen\].*?^-+\s*\n\s*Aktuelles', '', text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r'^Aktuelles\s*$', '', text, flags=re.MULTILINE)

    # 2. Slice Header by Title
    title = meta.get('title', '').strip()
    text = trim_header_by_title(text, title)

    # 3. Footer Slicing
    footer_markers = [
        r'Welcome to zeit\.de', # Cookie banner
        r'Read with advertising',
        r'Newsletter\s*\n', 
        r'Drucken\s*\n',
        r'###\s*Seitennavigation', 
        r'###\s*Jetzt teilen auf',
        r'Seitennavigation',
        r'Haben Sie Fragen\? Schreiben Sie uns!',
        r'Was jetzt\? – Der tägliche Morgenüberblick',
        r'Antwort schreiben',
        r'Beitrag melden',
        r'Mehr laden',
        r'Link kopieren',
        r'Startseite',
        r'0\.5x\s+0\.75x', # Audio speed controls
        r'\*\s*⭐️\s*\*\s*❤️' # Emoji reactions line
    ]
    
    earliest_match_idx = -1
    
    for marker in footer_markers:
        match = re.search(marker, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            start = match.start()
            if earliest_match_idx == -1 or start < earliest_match_idx:
                earliest_match_idx = start
                
    if earliest_match_idx != -1:
        text = text[:earliest_match_idx]

    # 4. Inline Cleaning
    # Remove agency credits
    text = re.sub(r'©\s*dpa-infocom.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'©\s*AFP.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Quelle:\s*dpa.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Quelle:\s*AFP.*', '', text, flags=re.IGNORECASE)

    # Remove generic markdown separators and noise
    text = re.sub(r'^-{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^={3,}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove audio player artifacts (X at end)
    text = re.sub(r'\s+X\s*$', '', text)
    
    # Remove markdown links, keeping only the text: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # 5. Final whitespace cleanup
    text = remove_inline_noise(text)
    
    return text
