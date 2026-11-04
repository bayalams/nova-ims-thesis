import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_elmundo(text, meta):
    """
    Cleaner for EL_MUNDO articles.
    """
    
    # 1. Standard Title-based Trim
    # El Mundo often puts the title, then a summary, then the body.
    # But often there is a massive menu BEFORE the title.
    text = trim_header_by_title(text, meta.get('title'))
    
    # 2. Aggressive Header Cleaning (Post-Title)
    # After the title/summary, there is often an author block and "Actualizado <Date>"
    # Example: "[Luis Núñez-Villaveirán](...) Madrid Madrid Actualizado Lunes, 12 enero 2026 - 13:15"
    
    # It usually ends with a time like " - 13:15" or just the date.
    
    lines = text.split('\n')
    start_idx = 0
    
    # Heuristic: Scan first 20 lines (normalized) for "Actualizado" or "Enviado especial"
    
    # Regex to find the "Actualizado ... - HH:MM" line
    # Matches: "Actualizado  Lunes, 12 enero 2026 -\n13:15" (sometimes split across lines or spaces)
    
    # But sometimes "Actualizado" is inside the content? Unlikely for this news style.
    
    # A safer marker might be removing specific blocks.
    
    # Remove "Audio generado automáticamente con IA *"
    text = re.sub(r'Audio generado automáticamente con IA\s*\*?', '', text, flags=re.IGNORECASE)
    
    # Remove the share block: "* [Facebook]... [Enviar por email]..."
    text = re.sub(r'(?s)\* \[Facebook\].*?enviar por email"\)', '', text)
    
    # Remove comment counts in header
    text = re.sub(r'\* \d+ comentarios', '', text)
    
    # Remove Author/Location block match
    match = re.search(r'Actualizado\s+.*?\d{4}.*?-\s*\d{1,2}:\d{2}', text[:5000], re.DOTALL | re.IGNORECASE)
    if match:
        text = text[match.end():]

    # Post-processing: Remove leading unrelated bullet points
    # El Mundo often starts with "* Category: News Title" or just "* News Title"
    sentences = text.split('\n')
    start_offset = 0
    for line in sentences:
        sline = line.strip()
        if not sline:
            start_offset += 1
            continue
            
        # If line starts with * and is likely a navigation item (short-ish or has Link)
        # heuristic: if it starts with * and (has link or len < 150)
        is_bullet = sline.startswith('*') or sline.startswith('-')
        if is_bullet and (len(sline) < 200 or 'http' in sline or ']' in sline):
             start_offset += 1
        else:
            # Check for "Actualizado" debris that might have been missed
            if "Actualizado" in sline and len(sline) < 100:
                 start_offset += 1
                 continue
            break
            
    text = "\n".join(sentences[start_offset:])
        
    # 3. Footer Cleaning
    # "Ver enlaces de interés"
    # "Comentarios ------------------"
    # "Cargando siguiente contenido"
    
    footer_markers = [
        "Ver enlaces de interés",
        "Comentarios -----------------",
        "Cargando siguiente contenido",
        "### * Ver anteriores",
        "Secciones Servicios"
    ]
    
    # Find the earliest occurrence
    best_idx = len(text)
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1 and idx < best_idx:
            best_idx = idx
            
    if best_idx != len(text):
        text = text[:best_idx]
        
    # 4. Inline Noise
    # Remove "Ver enlaces de interés" (redundant check)
    # Remove internal "Te puede interesar" blocks if any (standard seems to be "Ver enlaces...")
    
    text = remove_inline_noise(text)
    
    # Flatten links
    # El Mundo has many internal links: [Text](URL)
    # Regex: \[([^\]]+)\]\(http[^)]+\)
    text = re.sub(r'\[([^\]]+)\]\(http[^)]+\)', r'\1', text)
    
    return text.strip()
