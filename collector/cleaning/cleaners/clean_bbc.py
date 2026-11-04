import re

def clean_bbc(text, meta):
    # 1. Header Cleaning
    
    # Remove top navigation noise (Skip to content, Home, etc)
    # The scrapingbee content starts with a huge menu.
    # A good heuristic is to look for the Title (H1) which usually appears after the menu.
    # The Generic cleaner does this via `trim_header_by_title`, but the BBC menu is so large it might confuse things 
    # However, let's use the explicit markers seen in verification.
    
    # Pattern: [Skip to content] ... [Live] ... [Home] ... [News] ... [Weather] ... [Newsletters]
    
    title = meta.get('title', '').strip()
    clean_title = re.sub(r'<!\[CDATA\[|\]\]>', '', title).strip()
    
    # Locate title in text using H1 underline pattern characteristic of this source
    # The scrapingbee markdown usually looks like:
    # [Skip to content]...
    # Title
    # =====
    # metadata...
    
    # 1. Try to find the H1 underline "====="
    h1_match = re.search(r'\n([^\n]+)\n={3,}\n', text)
    
    if h1_match:
        # found the header. matching group 1 is the title line.
        start_pos = h1_match.end()
        text = text[start_pos:]
    else:
        # Fallback: Try title Match
        if clean_title:
             idx = text.lower().find(clean_title.lower())
             if idx != -1:
                 text = text[idx+len(clean_title):]

    # Now clean the immediate post-header metadata
    lines = text.split('\n')
    
    # Remove "=====" line if it somehow survived (e.g. from fallback)
    if lines and re.match(r'^=+$', lines[0].strip()):
        lines.pop(0)
        
    # Metadata filtering loop
    # Known noise: "1 day ago", "Share", "Save", "Author Name", "Region"
    
    while lines:
        line = lines[0].strip()
        if not line: 
            lines.pop(0)
            continue
            
        # Check for specific keywords
        if line in ["Share", "Save"]:
            lines.pop(0)
            continue
            
        # Time ago patterns: "1 day ago", "9 hours ago", "26 mins ago"
        if re.search(r'\d+\s+(day|hour|min|sec)s?\s+ago', line):
            lines.pop(0)
            continue
            
        # Author lines: "Faisal IslamEconomics editor", "Juna Moon,BBC Korean", "By Name"
        # Often contain "BBC", "Editor", "Correspondent" or just names.
        # Heuristic: Short line, looks like a name?
        # Risky if first sentence is short.
        if len(line) < 80 and ("BBC" in line or "Editor" in line or "Correspondent" in line or "," in line):
             lines.pop(0)
             continue
             
        if line.startswith("!["): # Lead image
            lines.pop(0) 
            continue
            
        break
    
    text = '\n'.join(lines)

    # 2. Footer Cleaning & Tag Extraction
    
    # "More from the BBC" is the strong marker.
    footer_triggers = [
        r'^More from the BBC$', 
        r'^Related$', 
        r'^Copyright \d{4} BBC', 
        r'^If it is safe to do so, you can get in touch',
    ]
    
    footer_idx = len(text)
    for trigger in footer_triggers:
        match = re.search(trigger, text, re.MULTILINE | re.IGNORECASE)
        if match and match.start() < footer_idx:
            footer_idx = match.start()
            
    # Extract Tags before cutting footer
    # Strategy: Look at the text strictly ABOVE the footer cut.
    # The tags usually appear as a block of short lines at the very end of this section.
    # e.g.
    # Body text...
    # 
    # Tag1
    # Tag2
    # Tag3
    # (Footer Trigger)
    
    pre_footer_text = text[:footer_idx].strip()
    lines_up = pre_footer_text.split('\n')
    
    extracted_tags = []
    # Scan backwards from the end
    
    scan_limit = 10 # Check last 10 lines max
    count = 0
    tags_found = []
    
    for i in range(len(lines_up) - 1, -1, -1):
        line = lines_up[i].strip()
        if not line:
            continue
            
        count += 1
        if count > scan_limit:
            break
            
        # Heuristic for a Tag line:
        # - Short
        # - Not a sentence (no ending period, though sometimes tags have?)
        # - Usually Capitalized words
        if len(line) < 50 and not line.endswith('.') and not line.startswith('!['):
            # It's a candidate.
            # But avoid "Getty Images" or "BBC Verify" or separators
            if "Getty Images" in line or re.match(r'^[-=]+$', line):
                continue
            
            # Clean the tag: [Tag Name](URL) -> Tag Name
            clean_tag = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line).strip()
            tags_found.insert(0, clean_tag)
        else:
            # Hit a body line, stop tag collection
            break
            
    if tags_found:
        # Update metadata tags
        existing_tags = meta.get('tags', []) or []
        # merge
        new_tags = list(set(existing_tags + tags_found))
        meta['tags'] = new_tags
        
        # Remove tags from text
        # finding the index of the first tag
        first_tag = tags_found[0]
        # scan from bottom of pre_footer_text
        idx_tag = pre_footer_text.rfind(first_tag)
        if idx_tag != -1:
             pre_footer_text = pre_footer_text[:idx_tag]

    text = pre_footer_text

    # 3. Inline Cleaning
    
    # Remove Images: ![...](...)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove "Share" and "Save" repeating lines
    text = re.sub(r'^\s*Share\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*Save\s*$', '', text, flags=re.MULTILINE)

    # Remove "Follow live updates" blocks and other multiline link blocks
    # [Text
    # -----](Link)
    # logic: [ followed by distinct content including dashes, ](link)
    # Remove "Follow live updates" blocks and other multiline link blocks
    # [Text
    # -----](Link)
    text = re.sub(r'\[[^\]]*?[-=]{3,}[^\]]*?\]\([^\)]+?\)', '', text, flags=re.DOTALL)
    # Also catch cases where the ](link) is separated by newline or space
    text = re.sub(r'\[[^\]]*?[-=]{3,}[^\]]*?\]\s*\([^\)]+?\)', '', text, flags=re.DOTALL)
    
    # Remove "Getty Images" lines (common caption artifact)
    # Be more aggressive: lines containing only Getty Images or starting with !Getty
    text = re.sub(r'^\s*!?(Getty Images.*?)\s*$', '', text, flags=re.MULTILINE)
    
    # Remove Separator lines (stray ---- or ====)
    text = re.sub(r'^\s*[-=]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Flatten Links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove stray single brackets that might remain from partial link removals
    text = re.sub(r'^\s*\[\s*$', '', text, flags=re.MULTILINE)

    # Collapse Whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()
