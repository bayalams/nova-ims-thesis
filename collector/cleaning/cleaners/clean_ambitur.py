import re

def clean_ambitur(text, meta):
    """
    Cleaning logic for AMBITUR articles.
    
    Issues identified:
    1. Header noise: Repeated title, image artifacts, metrics (PARTILHAS, VISUALIZAÇÕES).
    2. Footer noise: Massive lists of "Artigos Relacionados", "Notícias Populares", and login widgets.
    3. Inline noise: "Sem resultado", "Ver todos os resultados".
    """
    
    # 1. Remove lines that are just Markdown headers with links (Navigation/Sidebar junk)
    # Pattern: ### [Title](URL) or similar
    # This catches the massive lists of related articles
    text = re.sub(r'^###\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*\s*###\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE) # Indented bullet list version

    # 2. Remove Specific Header/Footer Markers
    noise_lines = [
        r'^Sem resultado\s*$',
        r'^Ver todos os resultados\s*$',
        r'^Tempo de leitura:.*$',
        r'^\d+\s*PARTILHAS\s*$',
        r'^\d+\s*VISUALIZAÇÕES\s*$',
        r'^PARTILHAS\s*$',
        r'^VISUALIZAÇÕES\s*$',
        r'^0\s*partilhas\s*$',
        r'^Por favor deixe este campo em branco\s*$',
        r'^Enviámos-lhe um e-mail!.*$',
        r'^### Welcome Back!\s*$',
        r'^Login to your account below\s*$',
        r'^Remember Me\s*$',
        r'^### Retrieve your password\s*$',
        r'^### Add New Playlist\s*$',
        r'^- Select Visibility -\s*$',
        r'^Public\s*$',
        r'^Private\s*$',
        r'^© \d{4}.*Ambitur.*$',
        r'^###\s*$', # Empty headers
        r'^em\s*$'   # Often appears alone before reading time
    ]
    
    for pattern in noise_lines:
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.IGNORECASE)

    # 1.1 Remove Repeated Title + Separator
    # Pattern: Title \n ====...
    text = re.sub(r'^.*?\n=+\s*$', '', text, flags=re.MULTILINE)

    # 1.2 Remove Dates in Body (09/01/2026)
    text = re.sub(r'^\s*\d{2}/\d{2}/\d{4}\s*$', '', text, flags=re.MULTILINE)

    # 1.3 Remove Social Share Links
    # [Share on Facebook](...) ...
    text = re.sub(r'^\[Share on .*?\]\(.*?\).*$', '', text, flags=re.MULTILINE)

    # 1.4 Remove Sidebar Links like "Ambiente Magazine"
    text = re.sub(r'^\s*\*\s*\[Ambiente Magazine\].*$', '', text, flags=re.MULTILINE)
    
    # Remove markdown images that might be left over
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # 1.5 Remove empty links [](...) or > [](...)
    # These often appear at the top as residues
    text = re.sub(r'^\s*>?\s*\[\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)

    # 3. Footer Trimming
    
    # 2.5 Extract Tags if present (before cutting)
    # Search for "Tags:" line.
    # Format: Tags: [Tag1](url)[Tag2](url)...
    tags_match = re.search(r'(?m)^Tags:\s*(.+)$', text)
    if tags_match:
        tag_line = tags_match.group(1).strip()
        # Parse all [Tag](url) occurrences
        # Regular expression to find content inside []
        found_tags = re.findall(r'\[([^\]]+)\]\(', tag_line)
        
        if found_tags:
            current = meta.get('tags', [])
            for t in found_tags:
                t = t.strip()
                if t and t not in current:
                    current.append(t)
            meta['tags'] = current

    # Now cut footer
    footer_triggers = [
        r'^\[Artigo anterior',
        r'^\[Próximo artigo',
        r'^### Artigos \*\*Relacionados\*\*',
        r'^### Notícias \*\*Populares\*\*',
        r'^### Noticias by\*\*Ambiente Magazine\*\*',
        r'^Tags:' # Also cut from Tags onwards as it's the start of footer metadata
    ]

    
    for trigger in footer_triggers:
        match = re.search(trigger, text, flags=re.MULTILINE)
        if match:
            text = text[:match.start()]

    # 4. Header Trimming (The repeated title + artifacts)
    # Often the text starts with:
    # Title ](image_url)](link)]
    # ### [Title](link)
    # ...
    # separator
    # em
    # Tempo de leitura...
    #
    # Real text starts after the separator or the metrics.
    
    
    # Better approach for the weird title artifact:
    # "Title...](...)"
    text = re.sub(r'^.*?\]\(https://www\.ambitur\.pt.*?\)\s*$', '', text, flags=re.MULTILINE)

    text = re.sub(r'^.*?\]\(https://www\.ambitur\.pt.*?\)\s*$', '', text, flags=re.MULTILINE)

    # 5. Collapse multiple newlines (to fix the huge gaps)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()
