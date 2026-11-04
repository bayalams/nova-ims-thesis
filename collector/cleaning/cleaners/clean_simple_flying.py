import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

def extract_simple_flying_date(text, scraped_at=None):
    """
    Extract publication date from Simple Flying raw content.
    Looks for patterns like "Published 1 day ago", "Published 4 hours ago", etc.
    Converts relative time to an actual date string (YYYY-MM-DD).
    
    Args:
        text: The raw article content
        scraped_at: ISO format timestamp of when the article was scraped (e.g., "2026-01-12T11:41:13.651694")
                   If provided, used as the base for relative time calculation.
                   If not provided, uses current time.
    """
    match = re.search(r'Published (\d+) (hours?|days?|minutes?|weeks?) ago', text, re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        
        # Use scraped_at as base time if available, otherwise use current time
        if scraped_at:
            try:
                # Handle ISO format with or without microseconds
                if '.' in scraped_at:
                    base_time = datetime.fromisoformat(scraped_at)
                else:
                    base_time = datetime.fromisoformat(scraped_at)
            except ValueError:
                base_time = datetime.now()
        else:
            base_time = datetime.now()
        
        if 'minute' in unit:
            delta = timedelta(minutes=amount)
        elif 'hour' in unit:
            delta = timedelta(hours=amount)
        elif 'day' in unit:
            delta = timedelta(days=amount)
        elif 'week' in unit:
            delta = timedelta(weeks=amount)
        else:
            return None
        
        pub_date = base_time - delta
        return pub_date.strftime('%Y-%m-%d')
    
    return None

def clean_simple_flying(text, meta, scraped_at=None):
    """
    Cleaner for Simple Flying aviation news articles.
    
    Args:
        text: Raw article content
        meta: Article metadata dict (will be modified to add pubDate if extracted)
        scraped_at: ISO timestamp of when article was scraped (for accurate date calculation)
    
    Key Noise Patterns:
    - Header: "Close", "Menu", "Follow", "Followed", "Like", "[Threads X]", author bios
    - AI Summary prompts: "Here is a fact-based summary...", "Try something different:", "Show me the facts"
    - Footer: "Trending Now", related article links
    - Inline: Markdown links, tag links
    """
    
    # 0. Extract Date BEFORE cleaning (from raw text)
    if not meta.get('pubDate'):
        extracted_date = extract_simple_flying_date(text, scraped_at)
        if extracted_date:
            meta['pubDate'] = extracted_date
    
    # 1. Header Trimming (Title Based)
    text = trim_header_by_title(text, meta.get('title'))
    
    # 2. Remove AI Summary / Interactive Prompts
    # These appear at the top of articles after the author bio
    summary_triggers = [
        "Here is a fact-based summary of the story contents:",
        "Try something different:",
        "Show me the facts",
        "Explain it like I'm 5",
        "Give me a lighthearted recap",
        "Generate a summary of this story",
    ]
    for trigger in summary_triggers:
        idx = text.find(trigger)
        if idx != -1:
            # Cut after the trigger block (usually 2-3 lines)
            end_idx = text.find('\n', idx + len(trigger) + 50)
            if end_idx != -1 and end_idx < idx + 200:
                text = text[end_idx:].strip()
            else:
                text = text[idx + len(trigger):].strip()
    
    # 3. Aggressive Header Removal
    header_patterns = [
        r'^Close\s*$',
        r'^\* \+ \[AIRLINES\].*?$',
        r'^\* \+ \[THREADS\].*?$',
        r'^Menu\s*$',
        r'^Follow\s*$',
        r'^Followed\s*$',
        r'^Like\s*$',
        r'^\[Threads?\s*\n?\d+\].*?$',
        r'^More Action\s*$',
        r'^Sign in now\s*$',
        r'^Sign in to your Simple Flying account\s*$',
        r'^follow\s*$',
        r'^followed\s*$',
        r'^\d+\s*$',  # Isolated numbers (thread counts, likes)
        # Author bio patterns (typically multi-line)
        r'^By\s*$',
        r'^Published \d+ (hours?|days?|minutes?) ago\s*$',
        r'^Based in .*$',
    ]
    for pat in header_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove author bio blocks (long descriptions)
    # These typically start with a name and describe the author
    text = re.sub(r'^[A-Z][a-z]+ (comes to|joins|is an?) .*?aviation.*?\..*?$', '', text, flags=re.MULTILINE | re.DOTALL)
    
    # 4. Footer Trimming
    footer_triggers = [
        "Trending Now",
        "##### [",  # Related article links
        "Copy link",
        "Close\nTrending",
        "Share\nCopy link",
    ]
    
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.rfind(trigger)  # Use rfind to find the last occurrence
        if idx != -1 and idx < best_cutoff and idx > len(text) * 0.5:  # Only cut if in last half
            best_cutoff = idx
            
    text = text[:best_cutoff]
    
    # 5. Inline Noise Removal
    text = remove_inline_noise(text)
    
    # Remove image credits: "Credit: Shutterstock", "Photo: Getty Images", etc.
    credit_patterns = [
        r'^Credit:\s*[A-Za-z]+.*?$',  # Credit: Shutterstock
        r'^Photo:\s*[A-Za-z]+.*?$',   # Photo: Getty Images
        r'^Image:\s*[A-Za-z]+.*?$',   # Image: Reuters
        r'^Source:\s*(Shutterstock|Getty|Reuters|AP|AFP).*?$',  # Source: Shutterstock
        r'^\(Photo by.*?\)$',         # (Photo by John Doe)
        r'^Photo credit:.*?$',        # Photo credit: ...
    ]
    for pat in credit_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove stray "Follow" / "Followed" / "Like" / "Share" in the middle
    text = re.sub(r'\n(Follow|Followed|Like|Share)\n', '\n', text, flags=re.IGNORECASE)
    
    # Remove trailing tag links: "Military](/tag/military/ "Military")" at end of article
    # Also matches inline ones like "Delta Air Lines](/tag/delta-air-lines/ "Delta Air Lines")"
    text = re.sub(r'\n[A-Za-z ]+\]\(/tag/[^\)]+/[^\)]*\)\s*$', '', text)
    
    # Remove any remaining tag markdown: "TagName](/tag/tag-name/ "TagName")"
    text = re.sub(r'[A-Za-z ]+\]\(/tag/[a-z\-]+/[^\)]*\)', '', text)
    
    # Remove trailing "Share" at end
    text = re.sub(r'\nShare\s*$', '', text)
    
    # Remove inline image markdown tags: "[![](image url)Text](link)"
    text = re.sub(r'\[!\[\]\([^\)]+\)[^\]]*\]\([^\)]+\)', '', text)
    
    # Remove newsletter signup prompts
    text = re.sub(r"Soar through captivating aviation stories with our newsletter's engaging roundup\.", '', text)
    
    # 6. Remove ALL markdown links: [text](/path/) → text
    # This preserves the link text but removes the URL
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Also handle links that might span lines or have complex content
    # Pattern: [any text](any url) - looser matching
    text = re.sub(r'\[([^\[\]]{1,200})\]\([^)]+\)', r'\1', text)
    
    # Remove orphaned [ that start a link but never close properly
    # Example: "[supposed low capabilities" → "supposed low capabilities"
    text = re.sub(r'\[([a-zA-Z][^\[\]]{0,60})(,|\.)', r'\1\2', text)
    
    # Remove separation markers
    text = re.sub(r'^-+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^=+$', '', text, flags=re.MULTILINE)
    
    # Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

