import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_eco(text, meta):
    # 1. Header Trim
    # Strategy A: Try to find the summary text in the body
    summary = meta.get('summary', '')
    # Strip HTML from summary to get text
    summary_text = re.sub(r'<[^>]+>', '', summary).strip()
    
    if summary_text:
        # Split by whitespace to preserve compound words like "lava-louças"
        raw_words = summary_text.split()[:10]
        # Strip leading/trailing punctuation from each word, but keep internal chars (hyphens, etc.)
        # and filter out any resulting empty strings
        words = [w.strip('.,;:"\'()[]{}!?*') for w in raw_words]
        words = [w for w in words if w]
        
        if words:
            # Create pattern: word + (any non-word chars)+ + word...
            # Escape words first
            escaped_words = [re.escape(w) for w in words]
            # Pattern allows for any non-word characters (spaces, punctuation, markdown) between words
            pattern = r'[\W_]+'.join(escaped_words)
            # Add optional start chars
            pattern = r'[\W_]*' + pattern
            
            match = re.search(pattern, text)
            if match:
                text = text[match.start():]
    
    # Strategy B: If A fails (or summary is empty), fall back to known header end markers
    # ECO often has a "premium" block ending with "Assinar" headers
    if not summary_text or (summary_text and not match):
        # Common end markers for header noise in ECO:
        # - "Assinar" button text (appears multiple times in pricing cards)
        # - "Inicie sessão"
        # - "Ligue-se por rede social" 
        
        # heuristic: The header shouldn't be larger than 5000 chars.
        # UPDATE: Some headers are massive (Article 20), so increasing to 15000.
        
        search_region = text[:15000]
        
        # Find all "Assinar" matches
        assinar_matches = list(re.finditer(r'\nAssinar\s*\n', search_region))
        
        if assinar_matches:
            # Cut after the LAST "Assinar" found
            last_match = assinar_matches[-1]
            text = text[last_match.end():]
        else:
            # Try "Inicie sessão" or "Ligue-se por rede social"
            other_markers = [
                r'Ligue-se por rede social:.*?\n',
                r'### Inicie sessão.*?\n'
            ]
            for m in other_markers:
                match = re.search(m, search_region, flags=re.DOTALL)
                if match:
                    # But they are usually followed by login fields.
                    # Article 4 has "Assinar".
                    pass


    # 2. Footer Slicing
    footer_markers = [
        r'Assine o ECO Premium\s*-+', # Strong footer marker
        r'\[Últimas\]', # Link to latest news
        r'Comentários \(\d+\)',
        r'Sem comentários',
        r'Precisa fazer \[login\]', 
        r'###### O seu browser está desatualizado!',
        r'TAMBÉM PODE GOSTAR',
        r'Populares\s*-+\s*\*',
        r'Notificações Google LinkedIn',
        r'Secured by OneAll',
        r'Para si\s*\n',
        r'\[Eventos\]',
        r'\[Assine já\]',
        r'Veja todos os planos'
    ]
    
    # Find the EARLIEST footer marker
    earliest_idx = len(text)
    found_footer = False
    
    for marker in footer_markers:
        match = re.search(marker, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            if match.start() < earliest_idx:
                earliest_idx = match.start()
                found_footer = True
                
    if found_footer:
        text = text[:earliest_idx]

    # 3. Inline Cleaning
    
    # 3.1 Remove "Ler Mais" / "Ver Mais" blocks often structured as:
    # ### [Title](URL) ... Copiar
    # or just loose links with "Copiar" at end
    
    # Remove "Copiar" artifacts commonly found at end of inline link blocks
    text = re.sub(r'\nhttps?://\S+\s+Copiar', '', text)
    
    # Remove the inline related article blocks which often look like:
    # ### [Title](URL) \n Source, Time \n URL
    
    # Pattern: ### [Title](Link) ... (heuristic: usually at end of paragraphs)
    text = re.sub(r'^###\s*\[.*?\]\(.*?\).*?$', '', text, flags=re.MULTILINE)
    
    # Remove "Para si" blocks if they appear inline (already handled in footer if at end)
    text = re.sub(r'^Para si\s*$', '', text, flags=re.MULTILINE)
    
    # Remove "Faça download da nossa app" or similar if present (common in ECO)
    
    # 4. Flatten Markdown Links [Text](URL) -> Text
    # (Matches [Text](URL) but ignores images ![...])
    text = re.sub(r'(?<!!)\[(.*?)\]\(.*?\)', r'\1', text)

    # 5. General whitespace cleanup
    text = remove_inline_noise(text)
    
    return text
