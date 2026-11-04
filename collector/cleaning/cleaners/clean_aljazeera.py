import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_aljazeera(text, meta):
    """
    Specific cleaner for Al Jazeera articles.
    Removes navigation menus, 'Recommended Stories' lists, and standard header noise.
    """
    
    # 1. Header Trimming
    # Al Jazeera scrapingbee output has a huge header block ending with "Save" usually.
    # Pattern: Published On ... -> Share -> links -> Save
    
    # Remove "Save" line first so it doesn't interfere
    text = re.sub(r'^\s*Save\s*$', '', text, flags=re.MULTILINE)

    # Look for "Published On" line to potentially trim header
    pub_match = re.search(r'^\s*Published On .*?$', text, flags=re.MULTILINE)
    
    if pub_match:
        # Only cut if it's near the TOP (first 50 lines)
        if text[:pub_match.start()].count('\n') < 50:
            text = text[pub_match.end():]

    # 1.5 Tag/Topic Extraction
    # Tags often appear in the top Navigation menu as links: * [**Tag**](/tag/tag/)
    
    # regex for navigation item: * [**Tag**](/tag/...)
    # or just * [Tag](/tag/...)
    
    # Regex for navigation item: matches [Tag Text](/tag/...)
    nav_tags = re.findall(r'\[([^\]]+)\]\(/tag/[^)]+\)', text[:2000])
    
    extracted_tags = []
    for raw_tag in nav_tags:
        # Clean ** or other markdown noise
        clean_tag = raw_tag.replace('**', '').replace('__', '').strip()
        if clean_tag and "no result" not in clean_tag.lower():
            extracted_tags.append(clean_tag)

            
    if extracted_tags:
        current_tags = meta.get('tags', [])
        for t in extracted_tags:
             if t not in current_tags:
                 current_tags.append(t)
        meta['tags'] = current_tags

    # 1.6 Fix "Save" cutting issue
    # "Save" often appears at the END of the article in the share block.
    # The previous logic was: text = text[save_match.end():] which deletes the article if Save is at bottom.
    
    text = re.sub(r'^\s*Save\s*$', '', text, flags=re.MULTILINE)



    # 1.5 Tag/Topic Extraction
    # Al Jazeera often has:
    # "Topics"
    # "Tag1"
    # "Tag2"
    # ...
    # "Share"
    
    topics_pattern = re.compile(r'(?m)^(?:Topics|Related topics)\s*$')
    # This block was for "Topics" at bottom - keep it just in case, but top nav is more reliable for tags.
    pass 


    # 2. Remove "Recommended Stories" / "More from the same show" lists
    # Structure:
    # Recommended Stories
    # -------------------
    # list of X items
    # ...
    # end of list
    
    list_block_pattern = r'(?:Recommended Stories|More from the same show)\s*\n\s*-+\s*\n\s*list of \d+ items.*?end of list'
    text = re.sub(list_block_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Remove "Navigation menu" if it survived header trimming
    text = re.sub(r'Navigation menucaret-left.*?caret-right', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 4. Remove Social Media Junk that might appear elsewhere
    social_patterns = [
        r'Click here to share on social media',
        r'^\s*share\d*\s*$', # "share2"
        r'^\s*Share\s*$',
        r'^\s*Save\s*$', # In case multiple appear
        r'Toggle Play',
    ]
    for pat in social_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # 5. Remove Inline Links and Markdown Images
    # Remove images: ![...](...)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Remove lines that are just links (often related widgets)
    text = re.sub(r'^\s*>?\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)

    # Flatten remaining inline links: [Text](URL) -> Text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove specific Cookie Consent Footer found in verification
    # Header: "You rely on Al Jazeera for truth and transparency"
    cookie_footer_pattern = r'You rely on Al Jazeera for truth and transparency.*$'
    text = re.sub(cookie_footer_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove long separator lines (dashes OR equals OR underscores) often found under headers
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # 6. Universal Cleanup (extra whitespace, etc)
    text = remove_inline_noise(text)
    
    return text.strip()
