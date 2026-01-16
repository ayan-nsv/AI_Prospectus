import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)

def get_social_media_links(soup, base_url):
    
    # Define social media patterns
    social_patterns = {
        'facebook': [
            r'facebook\.com/(?:pages/)?(?:[\w\-\.]+/)*[\w\-\.]+/?',
            r'fb\.com/[\w\-\.]+/?',
            r'fb\.me/[\w\-\.]+/?'
        ],
        'twitter': [
            r'twitter\.com/[\w]+/?',
            r'x\.com/[\w]+/?'
        ],
        'linkedin': [
            r'linkedin\.com/company/[\w\-]+/?',
            r'linkedin\.com/in/[\w\-]+/?'
        ],
        'instagram': [
            r'instagram\.com/[\w\.\-]+/?',
            r'instagr\.am/[\w\.\-]+/?'
        ],
        'youtube': [
            r'youtube\.com/c/[\w\-]+/?',
            r'youtube\.com/channel/[\w\-]+/?',
            r'youtube\.com/user/[\w\-]+/?',
            r'youtube\.com/@[\w\-]+/?',
            r'youtu\.be/[\w\-]+/?'
        ],
        'tiktok': [
            r'tiktok\.com/@[\w\.\-]+/?'
        ],
        'github': [
            r'github\.com/[\w\-\.]+/?'
        ],
        'pinterest': [
            r'pinterest\.com/[\w\-]+/?'
        ],
        'discord': [
            r'discord\.gg/[\w\-]+/?',
            r'discord\.com/invite/[\w\-]+/?'
        ],
        'telegram': [
            r't\.me/[\w\-]+/?'
        ],
        'whatsapp': [
            r'wa\.me/[\d]+/?'
        ],
        'reddit': [
            r'reddit\.com/r/[\w\-]+/?',
            r'reddit\.com/u/[\w\-]+/?'
        ]
    }
    
    social_links = {}
    
    print("        Extracting social media links...")
    
    try:
        # Method 1: Extract from all anchor tags
        links = soup.find_all('a')
        for link in links:
            href = link.get('href', '').strip()
            if not href:
                continue
                
            # Convert relative URLs to absolute
            if href.startswith('/'):
                href = urljoin(base_url, href)
            elif not href.startswith(('http://', 'https://')):
                # Skip javascript: and mailto: links
                if href.startswith(('javascript:', 'mailto:', 'tel:')):
                    continue
                href = 'https://' + href
            
            # Check against all patterns
            for platform, patterns in social_patterns.items():
                for pattern in patterns:
                    try:
                        if re.search(pattern, href, re.IGNORECASE):
                            if _is_valid_social_url(href, platform):
                                if platform not in social_links:
                                    social_links[platform] = []
                                if href not in social_links[platform]:
                                    social_links[platform].append(href)
                                break
                    except Exception as e:
                        continue
        
        # Method 2: Extract from text content (simple approach)
        try:
            page_text = soup.get_text()
            for platform, patterns in social_patterns.items():
                for pattern in patterns:
                    # Look for URLs in text
                    text_pattern = r'(?:https?://)?(?:www\.)?' + pattern
                    matches = re.findall(text_pattern, page_text, re.IGNORECASE)
                    
                    for match in matches:
                        # Ensure proper protocol
                        if not match.startswith(('http://', 'https://')):
                            match = 'https://' + match
                        
                        if _is_valid_social_url(match, platform):
                            if platform not in social_links:
                                social_links[platform] = []
                            if match not in social_links[platform]:
                                social_links[platform].append(match)
        except Exception as e:
            logger.warning(f"Error extracting from text: {e}")
        
        # Method 3: Check meta tags safely
        try:
            # Get all meta tags
            meta_tags = soup.find_all('meta')
            for tag in meta_tags:
                # Check content attribute
                content = tag.get('content', '')
                if content:
                    for platform, patterns in social_patterns.items():
                        for pattern in patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                if _is_valid_social_url(content, platform):
                                    if platform not in social_links:
                                        social_links[platform] = []
                                    if content not in social_links[platform]:
                                        social_links[platform].append(content)
        except Exception as e:
            logger.warning(f"Error extracting from meta tags: {e}")
        
        # Clean and deduplicate
        cleaned_links = {}
        for platform, urls in social_links.items():
            cleaned_urls = []
            for url in urls:
                cleaned_url = _clean_url(url)
                if cleaned_url and cleaned_url not in cleaned_urls:
                    cleaned_urls.append(cleaned_url)
            
            if cleaned_urls:
                cleaned_links[platform] = cleaned_urls
        
        total_links = sum(len(urls) for urls in cleaned_links.values())
        print(f"        Found {total_links} social media links across {len(cleaned_links)} platforms")
        
        return cleaned_links
        
    except Exception as e:
        logger.error(f"Error in social media extraction: {e}")
        print(f"        Error extracting social media: {e}")
        return {}

def _is_valid_social_url(url, platform):
    """Validate that the URL is actually a valid social media profile"""
    if not url or len(url) < 10:
        return False
    
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        
        # Platform-specific validation
        if platform == 'facebook':
            # Skip generic Facebook pages
            invalid_paths = ['/login', '/signup', '/home', '/pages/create', '/help']
            return not any(path in parsed.path.lower() for path in invalid_paths)
        
        elif platform == 'twitter':
            # Skip generic Twitter pages
            invalid_paths = ['/login', '/signup', '/home', '/explore', '/notifications']
            return not any(path in parsed.path.lower() for path in invalid_paths)
        
        elif platform == 'linkedin':
            # Must be a company or individual profile
            return '/company/' in parsed.path or '/in/' in parsed.path
        
        return True
        
    except Exception:
        return False

def _clean_url(url):
    """Clean URLs and remove tracking parameters"""
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        # Basic cleaning
        url = url.strip().rstrip('/')
        
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Remove tracking parameters
        tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
            'fbclid', 'gclid', 'msclkid', 'ref', 'referrer', 'source',
            '_ga', '_gac', '_gid', 'igshid', 'feature'
        ]
        
        cleaned_params = {k: v for k, v in query_params.items() 
                         if k not in tracking_params}
        
        # Rebuild URL
        new_query = urlencode(cleaned_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
        
    except Exception:
        return url.strip().rstrip('/')

# Integration function for your existing scraper
def get_enhanced_social_media_simple(soup, base_url):
    """
    Simple integration function for your existing scraper
    """
    try:
        social_links = get_social_media_links(soup, base_url)
        return social_links
    except Exception as e:
        logger.error(f"Error in social media extraction: {e}")
        print(f"        Error extracting social media: {e}")
        return {}

