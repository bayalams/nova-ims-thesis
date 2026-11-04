
import re

def clean_cnn(text, meta):
    # 1. Header Cleaning
    # --------------------------------------------------------------------------
    # Locate H1 pattern typically used in these conversions:
    # Title Line
    # ==========
    
    lines = text.split('\n')
    title_idx = -1
    
    # Try to find the H1 underline of "====="
    for i, line in enumerate(lines):
        if re.match(r'^={3,}$', line.strip()):
            title_idx = i - 1 # Title is the line before
            break
            
    # If found, skip everything before the title (and the title underlining itself?)
    # The dispatcher usually prepends TITLE: ...
    
    body_lines = []
    
    if title_idx > -1:
        # Start looking from AFTER the underline
        # And skip immediate metadata lines
        body_lines = lines[title_idx+2:] 
    else:
        # Fallback: Process all lines, maybe just skip known top noise
        body_lines = lines

    # 2. Line-by-Line Filtering (Inline & Metadata)
    # --------------------------------------------------------------------------
    # Keywords indicating noise lines to drop
    noise_keywords = [
        "Ad Feedback",
        "Video Ad Feedback",
        "Now playing",
        "• Source:",
        "Link Copied!",
        "Scan the QR code",
        "Unlocking the World",
        "CNN’s Jan Camenzind", # Contributor lines often at end, but can catch via footer
        "Legal Terms and Privacy",
        "Click here to subscribe",
        "See more videos",
        "Most Read",
        "Stories worth watching"
    ]
    
    cleaned_lines = []
    
    # Metadata Regexes
    
    for i, line in enumerate(body_lines):
        sline = line.strip()
        if not sline:
            cleaned_lines.append(line)
            continue
            
        is_noise = False
        
        # Check Keywords
        for kw in noise_keywords:
             if kw in sline:
                 is_noise = True
                 break
        
        if is_noise:
            continue
            
        # Check specific patterns
        
        # Author line: "By Name, CNN"
        if sline.startswith("By ") and "CNN" in sline and len(sline) < 100:
            continue
            
        # Top Metadata heuristic (first few non-empty lines)
        if i < 10:
             # "[Name](URL), CNN"
             if "CNN" in sline and "[" in sline and "]" in sline:
                 continue
             # "Published" on its own
             if sline.lower() == "published":
                 continue
            
        # Read time: "X min read"
        if re.match(r'^\d+ min read$', sline):
            continue
            
        # Updated timestamp: "Updated", "12:53 PM EDT..."
        if sline == "Updated":
            continue
        if re.match(r'^\d{1,2}:\d{2} [AP]M [A-Z]+,?', sline): # e.g. 10:59 AM EDT
             continue
             
        # Video timestamps or short durations: "02:23", "1:50"
        if re.match(r'^\d{1,2}:\d{2}$', sline):
            continue
            
        # "Best of Travel" or "X videos" (playlist counters)
        if sline == "Best of Travel" or re.match(r'^\d+ videos?$', sline):
            continue
            
        # "Trending Now" header for video lists
        if sline == "Trending Now":
            continue

        cleaned_lines.append(line)
        
    text = '\n'.join(cleaned_lines)

    # 2.5 Tag Extraction (Before Footer)
    # CNBC often has "Key Points" at top (handled) and no specific "Tags" list visible in text usually?
    # If not, checks for "Trend:" or similar?
    # But let's check for a "Keywords" or "Tags" line just in case.
    
    # Common pattern: "WATCH:" ... or "Related:"
    # Not strictly tags.
    pass

    # 2.5 Tag/Topic Extraction (Before Footer Cut)
    # --------------------------------------------------------------------------
    # CNN often has a line "Topics" followed by a list or "Topics: Tag1, Tag2..." near the bottom.
    
    # Heuristic: Search for a line starting with "Topics" in the last 20 lines (or whole text)
    
    scan_lines = text.split('\n')
    found_tags = []
    
    # Look in the last chunk of lines for efficiency, but "Topics" might be before "Related content"
    for line in scan_lines[-50:]: 
        sline = line.strip()
        if not sline: continue
        
        # Pattern: "Topics" on its own line, or "Topics: ..."
        if re.match(r'^Topics\s*:?$', sline, re.IGNORECASE):
            # The NEXT line(s) might be the tags
            # But often it's just "Topics" and then tags follow.
            # Topic tags often follow on the next lines.
            pass
            
        # "Topics: Italy, Travel, ... "
        if re.match(r'^Topics\s*:(.+)$', sline, re.IGNORECASE):
            match = re.match(r'^Topics\s*:(.+)$', sline, re.IGNORECASE)
            content = match.group(1).strip()
            # CNN tags are often just a list of links in HTML, which become text.
            # "Topics: \n Tag1 \n Tag2"
            pass

    # Better approach: Regex over the whole text for "Topics" block
    # CNN Topics usually appear as:
    # "Topics"
    # [Tag1]
    # [Tag2]
    # ...
    # "Scan the QR code..."
    
    topics_match = re.search(r'(?m)^Topics\s*:?\s*$', text)
    if topics_match:
        start = topics_match.end()
        # Scan forward
        potential_tags = []
        rest = text[start:].split('\n')
        for tline in rest:
            t = tline.strip()
            if not t: continue
            
            if any(m in t for m in footer_markers) or "ad feedback" in t.lower():
                break
                
            # Stop if line is too long to be a tag (e.g. > 50 chars) or looks like a sentence
            if len(t) > 60:
                break
                
            potential_tags.append(t)
            
        if potential_tags:
            # Add to meta
            current = meta.get('tags', [])
            # Avoid duplicates
            for tag in potential_tags:
                if tag not in current:
                    current.append(tag)
            meta['tags'] = current

    # 3. Footer Cleaning
    # --------------------------------------------------------------------------
    # Truncate at common footer markers
    footer_markers = [
        "Scan the QR code to download",
        "Legal Terms and Privacy",
        "See more videos", # Often starts the footer playlist
        "Standard Footer Marker",
        "Most Read",
        "Stories worth watching",
        "Sign up to CNN Travel",
    ]
    
    for marker in footer_markers:
        if marker in text:
             text = text.split(marker)[0]

    # 4. Inline Cleanup
    # --------------------------------------------------------------------------
    
    # Remove "Video playlist" residues that are hard to catch line-by-line due to variability
    # Pattern: Digit:Digit followed by "Now playing" or "• Source:"
    
    # Remove specific residual phrases
    text = re.sub(r'(?m)^\s*Now playing\s*$', '', text)
    text = re.sub(r'(?m)^\s*• Source:\s*$', '', text)
    text = re.sub(r'(?m)^.*?Video Ad Feedback.*?$', '', text)
    text = re.sub(r'(?m)^\s*CNN\s*$', '', text) # "CNN" on its own line often appears in video blocks
    text = re.sub(r'(?m)^\s*Trending Now\s*$', '', text)
    
    # Remove Timestamps "02:23" on their own line (aggressively)
    text = re.sub(r'(?m)^\s*\d{1,2}:\d{2}\s*$', '', text)

    # Remove Carousel/Pagination artifacts
    text = re.sub(r'(?m)^\s*\d+\s+of\s+\d+\s*$', '', text) # "1 of 6"
    text = re.sub(r'(?m)^\s*(Prev|Next)\s*$', '', text)


    # Remove Images: ![...](...) 
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove Separators
    text = re.sub(r'^[-=_]{3,}$', '', text, flags=re.MULTILINE)
    
    # Remove empty/malformed links: [](url) - must come BEFORE link flattening
    text = re.sub(r'\[\s*\]\([^\)]*\)', '', text)
    
    # Flatten Links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove any bare URLs that might remain
    text = re.sub(r'https?://\S+', '', text)
    
    # Dedup Repetitive Blocks (Gallery Artifacts)
    # Strategy: If a line > 40 chars is seen > 1 time, skip duplicates.
    
    final_lines = []
    seen_lines = set()
    for line in text.split('\n'):
        sline = line.strip()
        if not sline:
            final_lines.append(line)
            continue
            
        if len(sline) > 40 and sline in seen_lines:
            continue
            
        final_lines.append(line)
        if len(sline) > 40:
            seen_lines.add(sline)
            
    text = '\n'.join(final_lines)
    
    # Collapse Whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()
