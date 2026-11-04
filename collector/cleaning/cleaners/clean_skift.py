import re
from datetime import datetime, timedelta
from .utils import trim_header_by_title, remove_inline_noise

def extract_skift_date(text, scraped_at=None):
    """
    Extract publication date from Skift raw content.
    Looks for pattern: Author Name | 1 day ago
    """
    # Look for relative time patterns often found near author bylines
    # Examples: "| 8 hours ago", "| 1 day ago", "| 23 hours ago"
    match = re.search(r'\|\s*(\d+)\s*(hours?|days?|minutes?|weeks?|months?)\s*ago', text, re.IGNORECASE)
    
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
        elif 'month' in unit:
            delta = timedelta(days=amount * 30) # Approx
        else:
            return None
        
        pub_date = base_time - delta
        return pub_date.strftime('%Y-%m-%d')
    
    return None

def clean_skift(text, meta, scraped_at=None):
    """
    Cleaner for Skift travel industry news articles.
    
    Key Noise Patterns:
    - Cookie consent: "If you decline..."
    - Header: "* Sectors", "* Events", "* Skift Forum Videos"
    - Paywall: "Get unlimited access...", "First read is on us"
    - Podcast player: "Forward 15 seconds", "Back 15 seconds"
    - Social links: "LinkedIn", "* X", "* Email"
    - AI questions: "* What...?"
    - Footer gibberish: "mmMwWLli..."
    """
    
    # 0. Extract Date BEFORE cleaning (from raw text)
    if not meta.get('pubDate'):
        extracted_date = extract_skift_date(text, scraped_at)
        if extracted_date:
            meta['pubDate'] = extracted_date

    # 0. Formatting normalization
    # Remove markdown images first (they are noise)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
    # Convert markdown links to text (e.g. [text](url) -> text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 1. Remove cookie consent banner
    text = re.sub(r'^×\s*\n.*?Accept\s*\nDecline\s*\n', '', text, flags=re.DOTALL)
    text = re.sub(r'If you decline, your information won\'t be tracked.*?Decline\s*\n', '', text, flags=re.DOTALL)
    
    # 2. Remove entire header menu block (match beginning up to article content)
    # Look for the pattern where the menu ends and content starts
    # The menu typically ends with "Register" or similar, then article begins
    
    # Remove individual menu items with flexible whitespace
    menu_items = [
        r'\* Latest News',
        r'\* Ask Skift Search',
        r'\* Travel Megatrends',
        r'\* Travel Stock Index',
        r'\* Advertise',
        r'\* Skift Newsletters',
        r'\* Skift Travel Podcasts',
        r'\* Sectors',
        r'\* Events',
        r'\* Skift Forum Videos',
        r'\* Leer en Español',
        r'\+ Airlines',
        r'\+ Business Travel',
        r'\+ Hotels',
        r'\+ Online Travel',
        r'\+ Short-Term Rentals',
        r'\+ Cruises',
        r'\+ Startups',
        r'\+ Tourism',
        r'\+ Meetings',
        r'\+ Travel Technology',
        r'\+ All Sectors',
        r'\+ All Events',
        r'\+ Megatrends.*',
        r'\+ Skift.*Forum.*',
        r'\+ Skift.*Summit.*',
        r'\+ Skift.*Awards.*',
        r'\+ Women Leading Travel Forum',
        r'Read in English',
        r'Account',
        r'Register',
        r'Login',
        r'Summarize Story',
        r'!Play',  # Audio player button
    ]
    for item in menu_items:
        text = re.sub(r'^\s*' + item + r'\s*$', '', text, flags=re.MULTILINE)
        
    # Remove specific residual characters
    text = re.sub(r'[\ue602]', '', text)  #  character
    
    # 3. Remove paywall / subscription prompts
    paywall_patterns = [
        r'^First read is on us\.\s*$',
        r'^-+\s*$',  # Separator lines
        r'^Get unlimited access with Skift Pro\.\s*$',
        r'^Unlock your next read\s*$',
        r'^Enter your email for one more complimentary article.*?$',
        r'^New users get\s*$',
        r'^\*\*20% off\*\*\s*$',
        r'^their first year of Skift Pro\s*$',
        r'^Please ensure Javascript is enabled.*?accessibility.*?$',
        r'^This website requires JavaScript to run\.\s*$',
        # Pricing table / Subscription block
        r'^BEST VALUE\s*$',
        r'^### BILLED (ANNUALLY|MONTHLY)\s*$',
        r'^\$\d+ per (year|month)\s*$',
        r'^\(\$\d+/year\)\s*$',
        r'^CONTINUE\s*$',
        r'^Up Next\s*$',
        r'^Industry Insights: \d+ Questions With.*$',
    ]
    for pat in paywall_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE)
        
    # Remove block for subscription pricing if multiple lines match
    text = re.sub(r'BEST VALUE.*?CONTINUE\s*\nCONTINUE', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Header Trimming (Title Based) 
    text = trim_header_by_title(text, meta.get('title'))
    
    # 5. Remove "Skift Take" section header
    text = re.sub(r'^Skift Take\s*$', '', text, flags=re.MULTILINE)
    
    # 6. Remove social share / AI questions block
    # These appear as "* LinkedIn\n* X\n* Email" and "* What...?\n* How...?"
    text = re.sub(r'^\* LinkedIn\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\* X\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\* Facebook\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\* WhatsApp\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\* Email\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\* (What|How|Why|When|Which|Who|Where|Are there|Is the|Can|Will|Does|Did).*?\?\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^Select a question above.*?$', '', text, flags=re.MULTILINE)
    
    # 7. Remove podcast player elements
    podcast_patterns = [
        r'^play_circle_filled\s*$',
        r'^play\\_circle\\_filled\s*$',
        r'^Listen to Story\s*$',
        r'^Share\s*$',
        r'^-+\s*$',
        r'^00:00:00\s*$',
        r'^Forward 15 seconds\s*$',
        r'^Back 15 seconds\s*$',
        r'^Description\s*$',
        r'^Share this episode with your friends\s*$',
        r'^Keep up to date by subscribing to this podcast\s*$',
        r'^In This Playlist\s*$',
        r'^\d+ (of \d+ )?Episodes?\s*$',
        r'^\d+ (min|hr)(\s+\d+ min)?\s*$',  # Duration like "42 min", "1 hr 3 min"
        r'^Load more\s*$',
        r'^Save to Spotify\s*$',
        r'^Airline Weekly Lounge( Podcast)?\s*$',
        r'^Share Airline Weekly Lounge( Podcast)?\s*$',
        r'^Follow the Hosts:.*$',
        r'^Connect with (Airline Weekly|Skift).*$',
        r'^Recorded on-stage at.*$',  # Common intro for podcast transcripts
    ]
    for pat in podcast_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # 8. Remove episode titles and podcast descriptions from playlists
    text = re.sub(r'^(Inside|The|In Conversation|What|Why|How|Is|Even|Airlines in|America\'s).*?(Interview|Playbook|2026|Profitable|Laurels|Squeeze|Sunrise|All-Stars)\s*$', '', text, flags=re.MULTILINE)
    
    # Remove podcast host info blocks
    text = re.sub(r'^Gordon Smith.*?LinkedIn.*?$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^Jay Shabat.*?LinkedIn.*?$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Remove "Summary" section header (handle bold, whitespace, underlines)
    text = re.sub(r'^\s*(\*\*)?Summary(\*\*)?\s*\n-+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*(\*\*)?Summary(\*\*)?\s*$', '', text, flags=re.MULTILINE)
    
    # Remove "Articles Referenced" block (and the list that follows)
    # Match header and subsequent bullet points
    text = re.sub(r'^\s*(\*\*)?Articles Referenced:(\*\*)?.*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    
    # Remove Podcast/Newsletter bold headers AND the content following them
    # "Follow the Hosts:" usually followed by "Gordon Smith..." lines
    # "Connect with..." usually followed by social links
    text = re.sub(r'^\s*\*\*Follow the Hosts:.*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r'^\s*\*\*Connect with (Airline Weekly|Skift).*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r'^\s*\*\*Your daily travel podcast:.*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    
    # Remove Newsletter specific footers
    text = re.sub(r'^\s*Curated by \*\*.*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r'^\s*\*\*Early Check-In\*\* helps y.*?(?=\n\n|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
    
    # 9. Remove footer gibberish
    text = re.sub(r'^mmMwWLliI0fiflO&1\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^(word\s+){10,}word\s*$', '', text, flags=re.MULTILINE)  # "word word word..."
    
    # 10. Remove social media links (clean up any stragglers)
    # Also handle "Threads:", "Bluesky:", "@skiftnews"
    text = re.sub(r'^(LinkedIn|X|Instagram|Threads|Bluesky):.*?$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^@skiftnews.*?$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # [Markdown link removal moved to step 0]
    
    # 12. Aggressive footer/section trimming
    # These signals indicate the main article content has ended
    # Use FIRST occurrence (find, not rfind) to cut aggressively
    footer_triggers = [
        # Skift-specific navigation and promotional content
        "Key Points\n",           # Summary section that repeats content
        "Key Points:",
        "\nOnline Travel\n",       # Related articles section header
        "\nAirlines\n",           # Related articles section header  
        "\nTourism\n",            # Related articles section header
        "\nHotels\n",             # Related articles section header
        "\nBusiness Travel\n",    # Related articles section header
        "Skift Daily Briefing",   # Podcast content
        "Your daily travel podcast",
        "In This Playlist",
        "Share Skift Daily",
        "First read is on us",
        "New users get",
        "Subscribe today to keep up",
        "Please ensure Javascript",
        "Get unlimited access",
        "Load more",
    ]
    
    # Find the FIRST occurrence of any footer trigger (not the last)
    best_cutoff = len(text)
    for trigger in footer_triggers:
        idx = text.find(trigger)  # Use find() not rfind()
        if idx != -1 and idx < best_cutoff and idx > len(text) * 0.3:
            best_cutoff = idx
            
    text = text[:best_cutoff]
    
    # 13. Remove any remaining related article blocks
    # Pattern: "### Title\nDescription...\nAuthor | X hours ago"
    text = re.sub(r'###\s+.+\n.+\n.+\|\s*\d+\s*(hours?|days?)\s*ago', '', text, flags=re.IGNORECASE)
    
    # Remove stray author bylines that got orphaned
    text = re.sub(r'^[A-Z][a-z]+\s+[A-Z][a-z]+\s+\|\s+\d+\s+(hours?|days?|months?)\s+ago\s*$', '', text, flags=re.MULTILINE)
    
    # Remove "Sponsored" tags
    text = re.sub(r'^Sponsored\s*$', '', text, flags=re.MULTILINE)
    
    # 14. Inline noise
    text = remove_inline_noise(text)
    
    # 15. Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 16. Remove separation markers (lines of -, =, or _) using flexible cleaning
    # Must be done cautiously to not remove markdown headers that were actually content
    # But Skift uses them mostly for noise separation
    text = re.sub(r'^\s*[-=_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    return text.strip()
