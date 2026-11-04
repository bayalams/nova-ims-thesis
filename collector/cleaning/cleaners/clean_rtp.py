import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_rtp(text, meta):
    """
    Cleaner for RTP Notícias.
    Strategy:
    1. Header Trim: Use title to cut extensive navigation menu.
    2. Footer Trim: Cut "PUB", "Tópicos", and table artifacts.
    """
    if not text:
        return ""

    # 0. Video/Audio Article Filtering
    # If the text contains video player controls like "10s Retroceder (j)", discard it.
    video_triggers = [
        "10s Retroceder (j)",
        "Entrar em tela cheia (f)",
        "Reproduzir (k)"
    ]
    if any(trigger in text for trigger in video_triggers):
        return ""

    # 1. Header Trim
    # RTP typically has a huge menu, then copyright, then Section, then Title.
    # trim_header_by_title should handle this if the title matches exactly.
    title = meta.get('title', '')
    if title:
        # The raw text often has the title followed by dashes, e.g.
        # "Title\n-------"
        text = trim_header_by_title(text, title)
        
    # Fallback: If title mismatch, look for Copyright line which is consistent
    copyright_marker = "© RTP, Rádio e Televisão de Portugal"
    if copyright_marker in text:
        parts = text.split(copyright_marker)
        if len(parts) > 1:
            # Take the last part, but be careful if it appears multiple times? 
            # Usually only once in header.
            # But sometimes "Economia" (Section) follows immediately.
            text = parts[-1]

    # Remove potential leading section names (e.g. "Economia\n", "Mundo\n")
    # Pattern: Start of string, uppercase or Capitalized word, newline
    # This might be risky if article starts with a location date line. 
    
    # 2. Footer Trimming
    footer_triggers = [
        "Tópicos\n",
        "PUB\n",
        "\n|  |  |",
        "Instale a app RTP Notícias", # in case it appears at bottom
        "Como alternativa, pode configurar",
        "Qualidade\nBaixa qualidade\nReproduzir", # Video player footer artifacts
    ]
    
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
            
    text = text[:best_cutoff]

    # 3. Clean Inline
    text = remove_inline_noise(text)
    
    
    # Remove specific RTP date/agency lines
    # e.g. "8 Janeiro 2026, 11:02" or "atualizado 9 Janeiro 2026, 09:38"
    # or "45 min."
    # Also removes "Lusa" or "RTP" on their own lines followed by "/"
    
    date_patterns = [
        r'^\d{1,2}\s+[LJMAOSND][a-zç]+\s+\d{4},?\s+\d{1,2}:\d{2}.*?$', # Date matcher Portuguese months
        r'^atualizado\s+\d{1,2}.*?$',
        r'^\d+\s+min\.$',
        r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s+-\s+[A-Z]{2,4}$', # e.g. "Rodrigo Antunes - Lusa"
        r'^Lusa\s*/?$',
        r'^RTP\s*/?$',
        r'^/$',
        # Remove the [Title... ===](link) artifacts
        r'\[.*?\n?={3,}\]\(http.*?\)',
        # Remove isolated years e.g. "2026" at start
        r'^\d{4}$'
    ]
    
    for pat in date_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)

    # Remove underline separators (---)
    text = re.sub(r'^-+$', '', text, flags=re.MULTILINE)
    
    return text.strip()
