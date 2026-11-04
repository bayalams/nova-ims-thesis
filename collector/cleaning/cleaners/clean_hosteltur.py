
import re
from .utils import remove_inline_noise


def clean_hosteltur(text, meta):
    """
    Cleaner for Hosteltur (Spanish B2B Travel News).
    Strategy:
    1. Trim Header: Remove long navigation block (5000+ chars) before article title.
    2. Trim Footer: 'Noticias relacionadas', 'Los más leídos', Premium banners, cookie consent.
    3. Inline: Remove image captions, "Escucha la noticia", tags block.
    
    Fixed 2026-02-02: Hosteltur has ~5000 chars of trending topics navigation before
    the actual article content. The standard trim_header_by_title only checks first
    2000 chars, so we need a custom approach.
    """
    
    # 00a. Tag Extraction (before cleaning removes them)
    # Tags appear in "Más sobre" section: * [Tag](url)
    extracted_tags = []
    if "Más sobre" in text:
        mas_sobre_match = re.search(r'\*\*Más sobre\*\*\s*((?:\* \[[^\]]+\]\([^)]+\)\s*)+)', text, re.DOTALL)
        if mas_sobre_match:
            tag_block = mas_sobre_match.group(1)
            # Extract tag names from [Tag](url) format
            extracted_tags = re.findall(r'\* \[([^\]]+)\]', tag_block)
    
    # Store extracted tags in meta (for downstream use)
    if extracted_tags and not meta.get('tags'):
        meta['tags'] = extracted_tags
    
    # 0. Header Trim - CUSTOM for Hosteltur
    # Hosteltur has ~5000 chars of navigation before article title
    # Search the ENTIRE text for the title, not just first 2000 chars
    title = meta.get('title', '')
    if title and len(title) >= 15:
        # Clean title for matching (remove CDATA noise if present)
        clean_title = re.sub(r'<!\[CDATA\[|\]\]>', '', title).strip()
        # Search full text for title
        idx = text.lower().find(clean_title[:50].lower())
        if idx != -1:
            text = text[idx:]


    lines = text.split('\n')
    clean_lines = []
    
    # Footer Triggers (Hard Stop)
    footer_triggers = [
        "Noticias relacionadas",
        "Los más leídos",
        "Revistas",
        "Comunidad Hosteltur",
        "Últimas noticias",
        "Las noticias más leídas",
        "Comentar",
        "Hazte Premium",
        "Para comentar, así como para ver ciertos contenidos",
        "¿Ya eres usuario?",
        "Acceso Gratuito con Cookies",
        "Navegación Personalizada",
        "Usted permite:",
    ]
    
    skip_patterns = [
        "Escucha la noticia",
        "Más artículos",
        "Más sobre",
        "Inicia sesión",
        "Esta noticia no tiene comentarios",
    ]
    
    for line in lines:
        sline = line.strip()
        
        # Footer Check
        if any(trig in sline for trig in footer_triggers):
            break
            
        # Skip noise lines
        if any(pat in sline for pat in skip_patterns):
            continue
            
        # Skip empty image markdown
        if sline.startswith('![') and sline.endswith(')'):
            continue
            
        # Skip lines that are just links (navigation remnants)
        if sline.startswith('[') and sline.endswith(')') and '](' in sline:
            continue
            
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    
    # Post-processing inline noise
    text = remove_inline_noise(text)
    
    # Strip Markdown Links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Strip image markdown that leaked: Title](url) -> Title
    text = re.sub(r'\]\(https?://[^\)]+\)', '', text)
    
    # Remove horizontal rule markers (---) and heading underlines (===)
    text = re.sub(r'^[=\-]{3,}$', '', text, flags=re.MULTILINE)
    
    # Remove trailing ### markers
    text = re.sub(r'^#{1,3}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove trailing "Hosteltur" signature
    text = re.sub(r'^Hosteltur\s*$', '', text, flags=re.MULTILINE)
    
    # Remove image caption lines (Fuente: ...)
    text = re.sub(r'^[^\n]*Fuente:[^\n]*$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
