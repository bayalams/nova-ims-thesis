
import re

def clean_cnbc(text, meta):
    # 1. Header Cleaning
    # --------------------------------------------------------------------------
    # CNBC often has a "Menu", "Key Points", "VIDEO", "watch now" at the top.
    
    # Heuristic: Cut before "Key Points" if present
    if "Key Points" in text:
        # Keep "Key Points" and everything after? usually key points are good content.
        # But "Menu" and navigation are before it.
        parts = text.split("Key Points", 1)
        if len(parts) > 1:
            text = "Key Points" + parts[1]
    
    # Additional header noise removal (iterative)
    # Remove lines that are just navigation links or common header words
    header_noise = [
        "Skip Navigation", "Markets", "Business", "Investing", "Tech", "Politics",
        "Video", "Watchlist", "Investing Club", "Join IC", "Join Pro", "Livestream",
        "Menu", "watch now", "PRO"
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    
    
    # Filter out lines that match header noise patterns exactly or closely.
    
    for i, line in enumerate(lines):
        sline = line.strip()
        if not sline:
            cleaned_lines.append(line)
            continue
            
        is_noise = False
        # Exact match or starts with noise
        for noise in header_noise:
            # Check for exact match or [Noise] or "Noise" followed by nothing important
            regex = r'^\[?' + re.escape(noise) + r'\]?(\s|$)'
            if re.match(regex, sline, re.IGNORECASE):
                is_noise = True
                break
        
        # Specific regex for "VIDEO\d:\d\d"
        if re.match(r'^VIDEO\d+:\d+', sline):
             is_noise = True

        if not is_noise:
             cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)

    # 2. Footer Cleaning
    # --------------------------------------------------------------------------
    # Truncate at common footer markers
    footer_markers = [
        "This site is now part of", 
        "Cookie Notice",
        "Subscribe to CNBC",
        "Sign up for free",
        "Recommended Video",
        "Fed Notes" # Appears at end as a link often
    ]
    
    for marker in footer_markers:
        if marker in text:
             text = text.split(marker)[0]

    # 3. Inline Cleaning
    # --------------------------------------------------------------------------
    # Remove Images: ![...](...) and links that are just images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove "Getty Images" lines (often isolated)
    text = re.sub(r'(?m)^.*Getty Images.*$', '', text)
    
    # Remove "Zoom In Icon", "Arrows pointing outwards"
    text = re.sub(r'(?m)^Zoom In Icon\s*$', '', text)
    text = re.sub(r'(?m)^Arrows pointing outwards\s*$', '', text)
    
    # Remove "Money Movers" (program name often in captions)
    text = re.sub(r'(?m)^Money Movers\s*$', '', text)

    # Remove separator lines
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Flatten Links [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Collapse Whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    # Final strip
    text = text.strip()
    
    return text
