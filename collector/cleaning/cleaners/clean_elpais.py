
import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_elpais(text, meta):
    """
    Cleaner for EL_PAIS variations.
    Removes subscription banners, share links, and footer noise.
    """
    
    # 1. First, strip known garbage from the very top to clean up potentialTitle matches
    # remove "Ir al contenido" and share links immediately
    text = re.sub(r'^\s*Ir al contenido\s*', '', text, flags=re.MULTILINE|re.IGNORECASE)
    text = re.sub(r'^\s*!.*$', '', text, flags=re.MULTILINE) # "!Author Name"
    
    # 2. Header Trim (Standard)
    # If title is found, this does the heavy lifting.
    if meta.get('title'):
        text = trim_header_by_title(text, meta.get('title'))
        
    # 2b. Fallback Block Cut:
    # If title trim failed (or didn't catch everything), look for "Copiar enlace" or "Ir a los comentarios"
    # These are definitive end-of-header markers in El Pais.
    search_limit = 3000
    head_region = text[:search_limit]
    
    # Markers that signify the END of the header block
    header_end_markers = ['Copiar enlace', 'Ir a los comentarios']
    
    headers_end_idx = -1
    for marker in header_end_markers:
        idx = head_region.rfind(marker)
        if idx != -1:
            candidate_idx = idx + len(marker)
            if candidate_idx > headers_end_idx:
                headers_end_idx = candidate_idx
                
    if headers_end_idx != -1:
        text = text[headers_end_idx:]
        
    # Explicitly clean up residues from block cuts (broken validation links)
    # Using regex to be robust against spacing
    text = re.sub(r'\]\(#comments_container\)', '', text)
    # Also clean generically if text starts with a broken link end
    text = re.sub(r'^\s*\]\([^\)]+\)\s*', '', text, flags=re.MULTILINE)
    
    # 3. Aggressive Header Scrubbing (Post-Trim)
    lines = text.split('\n')
    cleaned_lines = []
    header_done = False
    
    # Regex for El Pais Date Line: "12 ENE 2026 - 06:30 CET" or "JAN 12..."
    date_pattern_es = re.compile(r'^\d{1,2}\s+[A-Z]{3}\s+\d{4}\s*-\s*\d{2}:\d{2}', re.IGNORECASE)
    date_pattern_en = re.compile(r'^[A-Z]{3}\s+\d{1,2},?\s+\d{4}', re.IGNORECASE)
    
    for line in lines:
        stripped = line.strip()
        
        # Always remove specific noise lines regardless of position (header vs body)
        if stripped.startswith('Compartir en') or 'Compartir en' in stripped:
            continue
        if stripped.startswith('Copiar enlace'):
            continue
        if 'Ir a los comentarios' in stripped:
            continue
            
        # Clean up leftover artifacts from block cut (e.g. closing markdown link parts)
        # This explicitly removes '](#comments_container)' which was a reported issue
        if stripped.startswith('](#') or stripped == ')' or stripped == '].':
            continue
        
        # Remove lines that are purely author names often prefixed with ! or just loose names?
        # The "!Daniel Muela" was likely a markdown image alt text or similar artifact?
        
        # Remove Date Line explicitly if found (sometimes it survives the block cut if formatted differently)
        if date_pattern_es.search(stripped) or date_pattern_en.search(stripped):
            continue
        
        if stripped.upper().startswith('ACTUALIZADO:'):
            continue

        if not header_done:
            # Skip empty lines, underscores
            if not stripped:
                continue
            if re.match(r'^\\_(\s*\\_)+', stripped): # "_ _ _ _"
                continue
            
            if stripped.startswith('Ir al contenido'):
                 continue
            
            header_done = True
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
            
    text = '\n'.join(cleaned_lines)

    # 3. Footer Slicing
    footer_markers = [
        "Tu suscripción se está usando en otro dispositivo",
        "¿Quieres añadir otro usuario a tu suscripción?",
        "Más información\n---------------",
        "Archivado En\n------------",
        "Comentarios\nIr a los comentarios", # Regex might be better for "Comentarios[N]"
        "Mis comentarios", # Often distinct from "Ir a los comentarios"
        "Recomendaciones EL PAÍS",
        "[Lo más visto](/lo-mas-visto/)",
        "Se adhiere a los criterios de",
        "Si está interesado en licenciar este contenido",
        "***¿Tiene algo que contar?"
    ]
    
    # Simple substrings
    for marker in footer_markers:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            
    # Regex markers for dynamic footers
    regex_footers = [
        r'Comentarios\d+\s+Ir a los comentarios',
        r'Archivado En\s*-+',
        r'Más información\s*-+',
        r'Tu suscripción se está usando'
    ]
    
    for pat in regex_footers:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]

    # 4. Inline Cleaning
    # Remove location/date prefix from start of body: "Urgente Madrid - [04 ENE 2026..."
    # Pattern: ^(Urgente\s+)?[\w\s]+\s+-\s+\[.*?\]\s*(\(http.*?\))?
    text = re.sub(r'^(Urgente\s+)?[\w\s]+\s+-\s+\[\d+ [A-Z]{3} \d{4}.*?\](\(http.*?\))?\s*', '', text, flags=re.MULTILINE)
    
    # Remove remaining underscores lines
    text = re.sub(r'^\\_(\s*\\_)+', '', text, flags=re.MULTILINE)

    # Flatten markdown links (optional, but cleaner)
    # [Text](URL "Title") -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    return text.strip()
