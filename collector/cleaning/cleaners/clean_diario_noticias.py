import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_diario_noticias(text, meta):
    """
    Cleaner for Diário de Notícias (Portuguese news).
    Strategy:
    1. Filter out Opinion, Podcasts, Multimedia
    2. Remove title repetition and date blocks
    3. Remove social buttons and image artifacts
    4. Clean footer sections
    """
    
    # 0. Filtering: Opinion and Multimedia
    tags = meta.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    
    exclude_keywords = [
        'opinião', 'opiniao', 'podcast', 'multimédia', 'multimedia', 
        'vídeo', 'video', 'fotogaleria'
    ]
    
    url = meta.get('link', '').lower()
    if any(k in url for k in ['/opiniao/', '/multimedia/', '/podcasts/', '/videos/']):
        return ""

    if tags:
        tags_lower = [t.lower() for t in tags]
        for t in tags_lower:
            if any(k in t for k in exclude_keywords):
                return ""
                 
    title = meta.get('title', '').strip().lower()
    if title.startswith('opinião') or 'podcast' in title:
        return ""

    # Tag Enrichment (Keyword-based fallback)
    if not tags:
        new_tags = []
        text_lower = text.lower()
        title_lower = meta.get('title', '').lower()
        content_sample = title_lower + " " + text_lower[:2000]
        
        keywords_map = {
            'Economia': ['pib', 'inflação', 'bce', 'juros', 'taxa', 'orçamento', 'fisco', 'impostos'],
            'Política': ['governo', 'ministro', 'parlamento', 'eleições', 'partido', 'deputado'],
            'Sociedade': ['polícia', 'tribunal', 'crime', 'acidente', 'hospital', 'saúde'],
            'Desporto': ['futebol', 'benfica', 'sporting', 'porto', 'liga', 'jogador'],
            'Internacional': ['guerra', 'ucrânia', 'trump', 'eua', 'europa', 'ue'],
            'Cultura': ['cinema', 'música', 'teatro', 'exposição', 'livro', 'arte'],
        }
        
        for category, keywords in keywords_map.items():
            for kw in keywords:
                if kw in content_sample:
                    new_tags.append(category)
                    break
        
        if new_tags:
            meta['tags'] = new_tags

    # 1. Remove DN Brasil boilerplate (appears in all articles from that section)
    dn_brasil_boilerplate = [
        "Este texto está publicado na edição impressa do Diário de Notícias",
        "O DN Brasil é uma seção do Diário de Notícias dedicada à comunidade brasileira",
        "Os textos são escritos em português do Brasil",
        "@dn.pt",
    ]
    for boilerplate in dn_brasil_boilerplate:
        text = text.replace(boilerplate, '')
    
    # Remove email patterns like "amanda.lima@dn.pt*"
    text = re.sub(r'[a-zA-Z0-9_.+-]+@dn\.pt\*?', '', text)
    
    # 2. Cut at foreign language content using character detection
    # Slovak distinctive chars: ľ, ť, ž, ô, ň, ď, ĺ, ä, ŕ
    # Norwegian distinctive chars: ø, å, æ
    # Also check for common ad patterns
    
    foreign_chars_slovak = set('ľťžôňďĺäŕ')
    foreign_chars_norwegian = set('øåæ')
    
    # Simple ad triggers that are always ads
    ad_triggers = [
        'Desfazer',           # Portuguese "undo" - appears after every ad
        'Read More',          # English CTA
        'Learn More',         # English CTA
        'Watch Now',          # English CTA
        '.com |',             # Ad format: domain | 
        '.shop |',            # Ad format
    ]
    
    best_cutoff = len(text)
    
    # First check simple triggers
    for trigger in ad_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
    
    # Then check for lines with foreign characters
    lines = text.split('\n')
    current_pos = 0
    for line in lines:
        # Check if line contains Slovak or Norwegian chars
        line_chars = set(line.lower())
        has_slovak = bool(line_chars & foreign_chars_slovak)
        has_norwegian = bool(line_chars & foreign_chars_norwegian)
        
        if has_slovak or has_norwegian:
            if current_pos < best_cutoff:
                best_cutoff = current_pos
            break
        
        current_pos += len(line) + 1  # +1 for newline
    
    text = text[:best_cutoff]
    
    # 3. Cut at image markers (![) - usually footer junk after this
    if '![' in text:
        text = text[:text.find('![')]
    
    # 2. Pre-process: Remove Markdown Images and broken image refs
    text = re.sub(r'!\[.*?\]\([^\)]+\)', '', text)
    text = re.sub(r'\]\(//media\.assettype\.com[^\)]+\)', '', text)  # Broken image refs
    
    # 3. Remove ALL links completely (not just keep text)
    # First remove the full markdown link syntax
    text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    # Then remove any remaining raw URLs
    text = re.sub(r'https?://[^\s\)\]]+', '', text)
    text = re.sub(r'www\.[^\s\)\]]+', '', text)
    
    # 4. Remove non-Portuguese content (lines with mostly non-Portuguese chars)
    # Simple heuristic: remove lines that look like URLs, codes, or have too many special chars
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        sline = line.strip()
        if not sline:
            cleaned_lines.append(line)
            continue
        # Skip lines that are mostly non-letter characters (URLs, codes, etc.)
        letter_count = sum(1 for c in sline if c.isalpha())
        if len(sline) > 10 and letter_count / len(sline) < 0.5:
            continue
        # Skip lines with suspicious patterns (tracking codes, etc.)
        if re.match(r'^[a-f0-9\-]{20,}$', sline, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    
    # 5. Remove header junk
    lines = text.split('\n')
    cleaned_lines = []
    
    noise_patterns = [
        r'^\* Copied$',
        r'^Siga-nos$',
        r'^Publicado a:$',
        r'^Atualizado a:$',
        r'^\d{1,2} \w{3} \d{4}, \d{2}:\d{2}$',  # Date pattern: 23 Jan 2026, 08:01
        r'^={3,}$',  # Separator lines
        r'^-{3,}$',
        r'^Marine Traffic',  # Image credits
    ]
    
    for line in lines:
        sline = line.strip()
        if not sline:
            cleaned_lines.append(line)
            continue
            
        is_noise = False
        for pattern in noise_patterns:
            if re.match(pattern, sline, re.IGNORECASE):
                is_noise = True
                break
        
        if is_noise:
            continue
            
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # 3. Remove title from start (it's in metadata)
    title = meta.get('title', '')
    if title and text.startswith(title):
        text = text[len(title):].lstrip()
    
    # 4. Footer Trimming - More aggressive patterns
    footer_triggers = [
        "Artigos Relacionados",
        "Leia também",
        "Leia Também",
        "Relacionado:",
        "Mais lidas",
        "Mais Lidas",
        "Newsletter",
        "Comentários",
        "Partilhar no Facebook",
        "Partilhar no Twitter",
        "dnoticias.pt",
        "Subscreva a newsletter",
        "Assine o DN",
        "Aceda a todos os conteúdos",
        "Já é assinante?",
        "Ver mais artigos",
        "Receba as notícias",
    ]
    
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)
        if idx != -1 and idx < best_cutoff:
            best_cutoff = idx
    
    # Also detect patterns like "[Title of another article]" which are related links
    # After stripping links, they appear as just the title text
    # Look for lines that look like article titles (start with capital, end without period)
    
    lines = text.split('\n')
    content_threshold = int(len(lines) * 0.6)  # Only check last 40% of lines
    
    for i, line in enumerate(lines):
        if i < content_threshold:
            continue
        sline = line.strip()
        # Skip empty lines
        if not sline:
            continue
        # Detect lines that look like article titles (often related articles)
        # Pattern: Starts with capital or "[", ends without sentence punctuation, 30-150 chars
        if (len(sline) > 30 and len(sline) < 150 and 
            (sline[0].isupper() or sline.startswith('[')) and
            not sline.endswith('.') and not sline.endswith('?') and not sline.endswith('!')):
            # Check if this line has keywords suggesting it's a related article
            related_hints = ['propõe', 'anuncia', 'revela', 'diz que', 'afirma', 'defende']
            if any(hint in sline.lower() for hint in related_hints):
                line_pos = text.find(sline)
                if line_pos != -1 and line_pos < best_cutoff:
                    best_cutoff = line_pos
                break
            
    text = text[:best_cutoff]
    
    # 5. Clean Inline
    text = remove_inline_noise(text)
    
    # 6. Final cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
