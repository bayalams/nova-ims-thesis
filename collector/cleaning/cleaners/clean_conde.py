
import re
from .utils import trim_header_by_title, remove_inline_noise

def clean_conde_nast(text, meta):
    """
    Cleaner for Conde Nast Traveler.
    Removes massive GDPR/Cookie consent blocks, navigation menus, and affiliate disclaimers.
    """
    
    # 1. Header Trimming by Title (Best bet if title is accurate)
    text = trim_header_by_title(text, meta.get('title'))

    # 2. Aggressive Header/Junk Block Removal
    # Patterns for the huge privacy/consent blocks
    
    # Pattern A: "Privacy Center ... OK"
    # This block often spans many lines with "Social Media\nOn\n...\nOK"
    if "Privacy Center" in text and "Confirm My Choices" in text:
         # This is the "Manage your consent" style
         # Remove from start to "Confirm My ChoicesReject AllAccept All"
         text = re.sub(r'Manage your consent preferences.*?Confirm My ChoicesReject AllAccept All', '', text, flags=re.DOTALL)
         
    # Pattern B: "Privacy Center... OK" 
    # This block often ends with "OK" followed by language selector
    text = re.sub(r'Privacy Center.*?OK', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove "About Your Privacy" / "Manage Consent" blocks
    # Flexible match for start, and multiple potential ends
    privacy_starts = [
        r'Manage your consent preferences',
        r'About Your Privacy',
        r'If you are a resident of Colorado',
        r'We Care About Your Privacy',
        r'Privacy Center'
    ]
    
    privacy_ends = [
        r'Confirm My ChoicesReject AllAccept All',
        r'SaveI Accept',
        r'SaveReject AllI Accept',
        r'Confirm My Choices',
        r'Accept All',
        r'Reject All'
    ]
    
    # Combined regex is risky if too broad, so let's target specific known chunks
    
    # 1. The "Resident of..." block (Generalizing for California/Colorado etc)
    # Ends with "Confirm My Choices" OR just falls through to "Allow Sale... On"
    text = re.sub(r'Your Privacy Choices.*?privacy notice\.', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'If you are a resident of.*?Confirm My Choices', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. "About Your Privacy" Block (Massive GDPR/Vendor List)
    # Previous regex failed because it matched "acceptance" inside the text.
    # Matches: Start "About Your Privacy" ... content ... End "EnglishDeutsch..."
    text = re.sub(r'About Your Privacy.*?EnglishDeutsch\w*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    text = re.sub(r'We Care About Your Privacy.*?Your Privacy Choices', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Standard "Privacy Center... OK"
    text = re.sub(r'Privacy Center.*?OK', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove Language Selector line string
    text = re.sub(r'EnglishDeutschEspañolFrançaisItaliano.*', '', text, flags=re.IGNORECASE)

    # Remove repeated "Social Media... On" blocks
    # Remove repeated "Social Media... On/Off" blocks
    # Handle "Social Media Cookies" or other variants followed by On/Off
    text = re.sub(r'(Social Media|Targeted|Essential|Performance|Functional|Audience Measurement).*?\n\s*(On|Off)', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^---\s*$', '', text, flags=re.MULTILINE) # Remove empty separator lines left behind
    
    # Remove Navigation / UI Noise
    # Robust Strategy: Identify the END of the header block and slice it off.
    # The header consistently ends with "Sign In" variations in the first few KB.
    header_end_markers = [
        r'Sign In\s*Sign In',
        r'\[Sign In\]\([^\)]+\)\s*\[Sign In\]\([^\)]+\)', # Markdown version double
        r'\[Sign In\]\([^\)]+\)', # Markdown version single
        r'Newsletters\s*Sign In',
        r'\[Newsletters\]\([^\)]+\)\s*\[Sign In\]\([^\)]+\)', # Markdown version
        r'Skip to main content', # Fallback
    ]
    
    for marker in header_end_markers:
        # Search the first 6000 chars (privacy block is usually ~4000 chars)
        match = re.search(marker, text[:6000], flags=re.IGNORECASE | re.DOTALL)
        if match:
            # Keep everything AFTER the match
            text = text[match.end():].lstrip()
            # Remove potential residual "Sign In" text (sometimes appears as plain text after the link)
            text = re.sub(r'^Sign In\s*', '', text, flags=re.IGNORECASE).lstrip()
            break
    
    ui_patterns = [
        r'^\s*Menu\s*$',
        r'^\s*Search\s*$',
        r'^\s*Close\s*$',
        r'^\s*Save Story\s*$',
        r'^\s*Save this story\s*$',
        r'^\s*Save to wishlist\s*$', # User requested removal
        r'^\s*\[Search\s*Search\]\(/search\)\s*$',
        r'confirm my choices',
        r'reject all',
        r'accept all',
        r'Allow Sale/Targeted Advertising\?', # User specific report
    ]
    for pat in ui_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # 4. Remove the standard Affiliate Disclaimer
    text = re.sub(r'All products and listings featured.*?through these links\.?', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 5. Remove persistent noise patterns (User Feedback & Generalized)
    # Photo credits (Generic "Name / Agency" detection)
    # Catches: "Patrick Dolande/Gotham Burger Social Club", "AGB Photo Library / Getty Images"
    # Pattern: Start of line, Capitalized Words, forward slash, Capitalized Words, End of line.
    text = re.sub(r'(?m)^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*/\s*[A-Z].*$', '', text)
    # Known Agencies (Getty, etc) if they appear without the slash structure
    text = re.sub(r'(?i)^.*(?:Getty\s*Images|Photo\s*Library).*$', '', text, flags=re.MULTILINE)
    
    # Social media artifacts (e.g., Pinterest links/filenames)
    text = re.sub(r'(?i)^.*Pinterest\.(?:jpg|png|svg).*$', '', text, flags=re.MULTILINE)
    
    # Recurring Headers/Sections to strip (flexible whitespace)
    text = re.sub(r'(?i)^.*(?:Editor-recommended\s+hotels|Frequently\s+asked\s+questions).*$', '', text, flags=re.MULTILINE)
    
    # Broken image/link artifacts (lines starting with ! or + ending in image ext or link syntax)
    text = re.sub(r'(?m)^\s*[!+].*\.(?:jpg|png|svg|jpeg|gif).*$', '', text)
    
    # Footer SVG links
    text = re.sub(r'(?m)^.*!\[\].*$', '', text)

    # Remove all Markdown images (User reported "massive links")
    # Matches: ![Alt Text](URL)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text, flags=re.DOTALL)
    
    # Residual "Sign In" text (Force removal at start of string and standalone lines)
    text = re.sub(r'(?i)\A\s*Sign\s+In\s*', '', text) # Start of text
    text = re.sub(r'(?i)^\s*Sign\s+In\s*$', '', text, flags=re.MULTILINE) # Standalone lines





    # 5. Remove Breadcrumbs and UI Buttons
    # [North America](/destinations/north-america)Chevron
    text = re.sub(r'\[.*?\]\(/.*?\)\s*Chevron', '', text)
    
    # Remove UI artifacts seen in verification
    ui_artifacts = [
        r'AccordionItemContainerButton',
        r'LargeChevron',
        r'Arrow',
        r'en\s*We Care\s*en',
        r'^\s*en\s*$',
    ]
    for pat in ui_artifacts:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # 6. Remove specific footer/cookie anomalies if they survived
    text = re.sub(r'Manage your consent preferences', '', text, flags=re.IGNORECASE)

    # 7. Flatten all remaining inline links: [Text](URL) -> Text
    # This addresses the user complaint about "links in the middle of text"
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # 8. Standard Inline Cleanup
    text = remove_inline_noise(text)
    
    return text
