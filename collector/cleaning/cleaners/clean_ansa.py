import re

def clean_ansa(text, meta):
    """
    Cleaner for ANSA_VIAGGI articles.
    """
    
    lines = text.split('\n')
    original_line_count = len(lines)
    
    # 0. KEYWORD/TAG EXTRACTION (Temi caldi)
    # Look for "Temi caldi" and extract the following bullet points as tags.
    # Usually appears as:
    # Temi caldi
    # * [Tag1](...)
    # * [Tag2](...)
    
    tags = []
    temi_caldi_idx = -1
    for i, line in enumerate(lines):
        if "Temi caldi" in line:
            temi_caldi_idx = i
            break
            
    if temi_caldi_idx != -1:
        # Scan following lines for bullet points
        for i in range(temi_caldi_idx + 1, min(temi_caldi_idx + 20, len(lines))):
            line = lines[i].strip()
            if not line:
                continue
            if line.startswith('*') and '[' in line:
                # Extract text between [ and ]
                # e.g. * [Capodanno](/ricerca...) -> Capodanno
                match = re.search(r'\[(.*?)\]', line)
                if match:
                    tags.append(match.group(1))
            else:
                # If it looks like a new section header or plain text, stop.
                if len(line) > 1 and not line.startswith('*'):
                     break
    
    if tags:
        meta['tags'] = tags
    
    # 1. REMOVE HEADER NOISE
    
    # Find start marker
    start_marker_idx = -1
    
    # Priority 1: RIPRODUZIONE RISERVATA (Most definitive)
    for i, line in enumerate(lines[:400]): # Increased range to 400 to skip large paywall blocks
        if "RIPRODUZIONE RISERVATA" in line:
            start_marker_idx = i
            break
    
    # Priority 2: Redazione ANSA (Fallback)
    if start_marker_idx == -1:
        for i, line in enumerate(lines[:400]):
            if "Redazione ANSA" in line:
                start_marker_idx = i
                break

    if start_marker_idx != -1:
        lines = lines[start_marker_idx+1:]
        
        # Additional cleanup: Skip immediate junk lines after marker
        while lines and (
            not lines[0].strip() or 
            "Condividi" in lines[0] or 
            "Link copiato" in lines[0] or
            lines[0].strip() == "*"
        ):
            lines.pop(0)

    else:
        # Fallback: remove specific junk lines
        header_noise_patterns = [
            r'^\* Link copiato',
            r'^/ricerca/ansait/',
            r'^Mostra meno',
            r'^In evidenza',
            r'^\*\*ANSA\*\*com',
            r'^in collaborazione con:',
            r'^Kia',
            r'^Temi caldi',
            r'^Naviga',
            r'^Vai a',
            r'^={5,}',
            r'^\d{1,2} [a-z]+ \d{4}, \d{2}:\d{2}',
            r'^\*\*[A-Z]+\*\*,$', # "**ROMA**,"
            r'^Più di un mese di vacanza con appena 8 giorni di ferie',
            r'^Sei già abbonato ad ANSA\.it',
            r'^Se hai scelto di non accettare i cookie',
            r'^Ti invitiamo a leggere le',
            r'^\[ABBONAMENTO CONSENTLESS',
            r'^\*\*Puoi leggere tutti i titoli',
            r'^a €\d+,\d+/anno\*\*',
            r'^\* Servizio equivalente a quello accessibile',
            r'^\* Durata annuale',
            r'^\* Un pop-up ti avvertirà',
            r'^\* Pubblicità presente',
            r'^\* Iscrizione alle Newsletter',
            r'^\[ALTRI ABBONAMENTI',
            r'^\*\*Per accedere senza limiti',
            r'^Scegli il piano di abbonamento',
            r'^Se accetti tutti i cookie',
            r'^Per maggiori informazioni sui servizi',
            r'^\[ACCETTA I COOKIE E CONTINUA',
        ]
        
        filtered_top = []
        body_started = False
        for line in lines:
            if not body_started:
                # remove known noise
                is_noise = False
                for p in header_noise_patterns:
                    if re.search(p, line):
                        is_noise = True
                        break
                if meta.get('title') and line.strip() == meta['title'].strip():
                    is_noise = True
                
                if not is_noise and line.strip():
                    body_started = True
                    filtered_top.append(line)
            else:
                filtered_top.append(line)
        lines = filtered_top

    text = '\n'.join(lines)

    # 2. REMOVE FOOTER NOISE
    
    footer_triggers = [
        r'^Ultima ora\s*-+\s*\d{2}:\d{2}',
        r'^Ultima ora$',
        r'^Condividi articolo$',
        r'^Condividi$', # Aggressive, but usually safe at bottom
        r'^Sei già abbonato ad ANSA\.it\?',
        r'^Ansa\.it\s*Newsletter ANSA',
    ]

    footer_pos = len(text)
    
    for trigger in footer_triggers:
        match = re.search(trigger, text, re.MULTILINE)
        if match:
            # Only trigger footer cut if the match is NOT at the very beginning (unless text is huge)
            if match.start() < footer_pos:
                footer_pos = match.start()
                
    text = text[:footer_pos]

    # 3. INLINE CLEANING
    text = re.sub(r'^\* Link copiato', '', text, flags=re.MULTILINE)
    text = re.sub(r'^={5,}', '', text, flags=re.MULTILINE)
    
    # Explicitly remove "RIPRODUZIONE RISERVATA" lines if they survived slicing
    text = re.sub(r'^.*RIPRODUZIONE RISERVATA.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^.*Redazione ANSA.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # 4. COLLAPSE WHITESPACE
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()


