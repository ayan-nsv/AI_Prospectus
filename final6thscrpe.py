import requests
from bs4 import BeautifulSoup
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
import time
import urllib3
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, quote
import logging
from enhanced_contact_scraper import ContactInfoScraper

from get_company_openai import clean_phone_numbers, get_correct_url

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

def find_company_website(company_name):
    """
    Find the official website for a company name using multiple search engines
    """
    print(f"🔍 Searching for website: {company_name}")
    
    search_engines = [
        ("Google", f"https://www.google.com/search?q={quote(f'{company_name} official website')}"),
        ("Bing", f"https://www.bing.com/search?q={quote(f'{company_name} official website')}"),
        ("DuckDuckGo", f"https://duckduckgo.com/?q={quote(f'{company_name} official website')}")
    ]
    
    for x in range(3):
        for engine_name, search_url in search_engines:
            try:
                print(f"  🔄 Trying {engine_name}...")
                website = search_website_with_selenium(search_url, engine_name)
                if website:
                    print(f"  ✅ Found website via {engine_name}: {website}")
                    return website
            except Exception as e:
                print(f"  ❌ {engine_name} failed: {str(e)}")
                continue
    
    print(f"  ❌ No website found for {company_name}")
    return None

def search_website_with_selenium(search_url, engine_name):
    """Search for website using Selenium"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(30)
        driver.get(search_url)
        time.sleep(3)
        

        if engine_name == "Google":
            selectors = [
                "div.g a[href^='http']",
                "div.yuRUbf a[href^='http']",
                "h3 a[href^='http']"
            ]
        elif engine_name == "Bing":
            selectors = [
                "li.b_algo h2 a[href^='http']",
                "div.b_title a[href^='http']"
            ]
        else:  # DuckDuckGo
            selectors = [
                "article a[href^='http']",
                "h2 a[href^='http']"
            ]
        
        for selector in selectors:
            try:
                links = driver.find_elements(By.CSS_SELECTOR, selector)
                for link in links[:5]:  # Check first 5 results
                    href = link.get_attribute('href')
                    if href and is_valid_website(href):
                        return href
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"    Error with {engine_name}: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return None

def is_valid_website(url):
    """Check if URL looks like a valid company website"""

    skip_domains = [
        'linkedin.com', 'facebook.com', 'twitter.com', 'instagram.com',
        'crunchbase.com', 'yellowpages.com', 'whitepages.com', 'manta.com',
        'zoominfo.com', 'spoke.com', 'superpages.com', 'foursquare.com',
        'yelp.com', 'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
        'wikipedia.org', 'bloomberg.com', 'reuters.com', 'forbes.com'
    ]
    
    domain = urlparse(url).netloc.lower()
    return not any(skip in domain for skip in skip_domains)

def get_company_name(soup):
    """Enhanced company name extraction"""
    # Try meta tags first
    meta_title = soup.find('meta', property='og:title')
    if meta_title and meta_title.get('content'):
        return meta_title['content'].strip()
        
    # Then try title tag
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        return re.sub(r'\s*[-|]\s*(?:Home|Official Website|Welcome).*$', '', title)
    
    # Finally try h1
    h1 = soup.find('h1')
    if h1:
        return h1.text.strip()
    
    return None




def get_emails(soup):
    print(f"        DEBUG: Starting email extraction...")
    
    all_text = soup.text + ' '.join(link.get('href', '') for link in soup.find_all('a'))
    
    print(f"        DEBUG: Text length for email search: {len(all_text)} characters")
    

    raw_emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", all_text)
    
    print(f"        DEBUG: Raw emails found: {len(raw_emails)} - {raw_emails[:5]}")
    
    valid_emails = [
        email for email in raw_emails 
        if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email)
        and not any(fake in email.lower() for fake in ['example.com', 'domain.com', 'email@'])
    ]
    
    print(f"        DEBUG: Valid emails after filtering: {len(valid_emails)} - {valid_emails}")
    
    return list(set(valid_emails))


def get_phone_numbers(soup):
    print(f"        DEBUG: Starting phone extraction...")
    
    # Get all text including href attributes
    all_text = soup.text + ' '.join(link.get('href', '') for link in soup.find_all('a'))
    
    print(f"        DEBUG: Text length for phone search: {len(all_text)} characters")
    

    patterns = [
        r'\+\d[\d\s().-]{7,}\d',  # International format
        r'\(\d{3}\)\s*\d{3}[-.]?\d{4}',  # (123) 456-7890
        r'\d{3}[-.]?\d{3}[-.]?\d{4}'  # 123-456-7890
    ]
    
    phones = []
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, all_text)
        print(f"        DEBUG: Pattern {i+1} found {len(matches)} matches: {matches[:3]}")
        phones.extend(matches)
    
    # Clean and standardize
    cleaned_phones = []
    for phone in set(phones):
       
        cleaned = re.sub(r'[^\d+]', '', phone)
        if len(cleaned) >= 10: 
            cleaned_phones.append(phone.strip())
    
    print(f"        DEBUG: Final cleaned phones: {len(cleaned_phones)} - {cleaned_phones}")
    
    return list(set(cleaned_phones))


def get_address(soup):
    """Enhanced address extraction"""
    possible_keywords = ['address', 'location', 'visit us', 'office', 'headquarters', 'hq', 'contact']
    candidates = soup.find_all(['p', 'div', 'span', 'li', 'address'], string=True)
    
    addresses = []
    for tag in candidates:
        text = tag.get_text(separator=' ', strip=True)
        lower_text = text.lower()
        
        # Check if it's likely an address
        if (any(keyword in lower_text for keyword in possible_keywords) and
            10 < len(text) < 200 and  # Reasonable length
            re.search(r'\d', text) and  # Has numbers
            re.search(r'[A-Za-z]', text) and  # Has letters
            not re.search(r'@', text)):  # Not an email
            addresses.append(text)
    
    # Return the most likely address (longest that meets criteria)
    return max(addresses, key=len) if addresses else None




def get_social_media(soup):
    """Enhanced social media extraction"""
    social_links = {}
    social_patterns = {
        'facebook': r'facebook\.com/[\w.]+',
        'twitter': r'twitter\.com/[\w]+',
        'linkedin': r'linkedin\.com/(?:company/[\w-]+|in/[\w-]+)',
        'github': r'github\.com/[\w-]+',
    }
    
    # Look in both href attributes and text content
    all_text = soup.text + ' '.join(link.get('href', '') for link in soup.find_all('a'))
    
    for platform, pattern in social_patterns.items():
        matches = re.findall(pattern, all_text, re.I)
        if matches:
            # Get the first match and ensure it has https://
            url = matches[0]
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            social_links[platform] = url
    
    return social_links

def get_description(soup):
    """Enhanced description extraction with better filtering and organization"""
    description = None
    
    # 1. Try meta tags first with expanded search
    meta_tags = [
        ('meta', {'name': 'description'}),
        ('meta', {'property': 'og:description'}),
        ('meta', {'name': 'twitter:description'}),
        ('meta', {'name': 'abstract'}),
        ('meta', {'name': 'summary'}),
    ]
    
    for tag, attrs in meta_tags:
        meta = soup.find(tag, attrs=attrs)
        if meta and meta.get('content'):
            desc = meta['content'].strip()
            if len(desc) > 20 and not any(x in desc.lower() for x in ['cookie', 'privacy', 'terms']):
                description = desc
                break
    
    # 2. If no meta description, try to find a concise about section with improved selectors
    if not description:
        # Look for common about section identifiers
        about_selectors = [
            'section.about', 'div.about', 'article.about',
            'section.company', 'div.company', 'article.company',
            'section.overview', 'div.overview', 'article.overview',
            'section.who-we-are', 'div.who-we-are', 'article.who-we-are',
            'section.mission', 'div.mission', 'article.mission',
            'section.vision', 'div.vision', 'article.vision'
        ]
        
        for selector in about_selectors:
            about_section = soup.select_one(selector)
            if about_section:
                # Get all paragraphs and combine them intelligently
                paragraphs = about_section.find_all(['p', 'div'])
                meaningful_texts = []
                
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if (50 < len(text) < 500 and  # Increased max length
                        not any(x in text.lower() for x in ['cookie', 'privacy', '@', 'email']) and
                        not text.startswith(('©', 'All rights reserved', 'Privacy Policy')) and
                        not text.endswith(('©', 'All rights reserved', 'Privacy Policy'))):
                        meaningful_texts.append(text)
                
                if meaningful_texts:
                    # Combine the most meaningful paragraphs
                    description = ' '.join(meaningful_texts[:2])  # Take first two meaningful paragraphs
                    break
    
    # 3. If still no description, try to find the main content area
    if not description:
        main_content = soup.find(['main', 'article', 'section'], 
            class_=lambda x: x and any(word in str(x).lower() for word in ['main', 'content', 'primary']))
        
        if main_content:
            paragraphs = main_content.find_all(['p', 'div'])
            meaningful_texts = []
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                if (50 < len(text) < 500 and
                    not any(x in text.lower() for x in ['cookie', 'privacy', '@', 'email']) and
                    not text.startswith(('©', 'All rights reserved', 'Privacy Policy'))):
                    meaningful_texts.append(text)
            
            if meaningful_texts:
                description = ' '.join(meaningful_texts[:2])
    
    return description

def get_company_overview(soup):
    """Extract well-organized and concise company information"""
    overview_sections = {
        'about': [],
        'services': [],
        'expertise': [],
        'achievements': [],
        'mission': [],
        'vision': [],
        'values': []
    }
    
    # Common section identifiers for each category
    section_identifiers = {
        'about': ['about', 'company', 'overview', 'who-we-are', 'our-story'],
        'services': ['service', 'solution', 'offering', 'product', 'what-we-do'],
        'expertise': ['expertise', 'specialization', 'capability', 'technology', 'industry'],
        'achievements': ['achievement', 'award', 'recognition', 'milestone', 'success'],
        'mission': ['mission', 'purpose', 'goal'],
        'vision': ['vision', 'future', 'aspiration'],
        'values': ['value', 'principle', 'ethic', 'culture']
    }
    
    # Process each section type
    for section_type, identifiers in section_identifiers.items():
        # Try multiple selectors for each section type
        for identifier in identifiers:
            selectors = [
                f'section.{identifier}',
                f'div.{identifier}',
                f'article.{identifier}',
                f'div[class*="{identifier}"]',
                f'section[class*="{identifier}"]',
                f'article[class*="{identifier}"]'
            ]
            
            for selector in selectors:
                section = soup.select_one(selector)
                if section:
                    # Extract content based on section type
                    if section_type in ['about', 'mission', 'vision']:
                        # For longer text sections, combine meaningful paragraphs
                        paragraphs = section.find_all(['p', 'div'])
                        meaningful_texts = []
                        for p in paragraphs:
                            text = p.get_text(strip=True)
                            if (50 < len(text) < 500 and
                                not any(x in text.lower() for x in ['cookie', 'privacy', '@', 'email']) and
                                not text.startswith(('©', 'All rights reserved', 'Privacy Policy'))):
                                meaningful_texts.append(text)
                        if meaningful_texts:
                            overview_sections[section_type].extend(meaningful_texts[:2])
                    
                    else:
                        # For list-type sections, extract individual items
                        items = section.find_all(['li', 'h3', 'h4', 'p', 'div'])
                        for item in items:
                            text = item.get_text(strip=True)
                            if (20 < len(text) < 200 and
                                not any(x in text.lower() for x in ['cookie', 'privacy', '@', 'email']) and
                                not text.startswith(('©', 'All rights reserved', 'Privacy Policy'))):
                                overview_sections[section_type].append(text)
    
    # Format the overview in a clear, structured way
    formatted_overview = []
    
    # Add each section if it has content
    for section_type, content in overview_sections.items():
        if content:
            # Format section title
            title = section_type.replace('_', ' ').title()
            formatted_overview.append(f"\n{title}:")
            
            # Format content based on section type
            if section_type in ['about', 'mission', 'vision']:
                formatted_overview.append(content[0])  # Use the first (usually best) text
            else:
                # For list-type sections, format as bullet points
                for item in content[:5]:  # Limit to top 5 items
                    formatted_overview.append(f"• {item}")
    
    return '\n'.join(formatted_overview) if formatted_overview else None

def get_html(url):
    """Get HTML content using multiple methods"""
    print(f"      🌐 Attempting to scrape website: {url}")

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url.strip()

    # Try Simple Requests first
    try:
        print(f"        🔄 Trying requests method...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        response = requests.get(url, headers=headers, verify=False, timeout=20)
        if response.status_code == 200 and len(response.text) > 500:
            print(f"        ✅ Requests method successful")
            return response.text, "requests"
        else:
            print(f"        ❌ Requests failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"        ❌ Requests failed: {str(e)}")

    # Try Selenium
    try:
        print(f"        🔄 Trying Selenium method...")
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        driver.quit()
        
        if html and len(html) > 500:
            print(f"        ✅ Selenium method successful")
            return html, "selenium"
        else:
            print(f"        ❌ Selenium returned empty content")
    except Exception as e:
        print(f"        ❌ Selenium failed: {str(e)}")
        if 'driver' in locals():
            driver.quit()

    print(f"        ❌ All methods failed")
    return None, None

def extract_content(soup):
    """Extract essential content from the page"""
    content = {
        'headings': [],
        'paragraphs': [],
        'sections': {}
    }
    
    # Remove only the most unnecessary elements
    for element in soup.find_all(['script', 'style']):
        element.decompose()
    
    # Get headings with less restrictive filtering
    seen_headings = set()
    for heading in soup.find_all(['h1', 'h2', 'h3']):
        text = heading.get_text(strip=True)
        if (text and len(text) > 5 and  # Reduced minimum length
            text not in seen_headings and 
            not any(x in text.lower() for x in ['cookie', 'privacy', 'terms'])):  # Reduced filter terms
            content['headings'].append(text)
            seen_headings.add(text)
    
    # Get paragraphs with less restrictive filtering
    seen_paragraphs = set()
    for p in soup.find_all(['p', 'div', 'article', 'section']):
        text = p.get_text(strip=True)
        if (text and len(text) > 30 and  # Reduced minimum length
            text not in seen_paragraphs and 
            not any(x in text.lower() for x in ['cookie', 'privacy', 'terms']) and
            not text.startswith(('©', 'All rights reserved'))):
            # Clean the text
            text = ' '.join(text.split())  # Remove extra whitespace
            content['paragraphs'].append(text)
            seen_paragraphs.add(text)
    
    # Get content from specific sections with expanded identifiers
    section_identifiers = {
        'about': ['about', 'company', 'overview', 'who-we-are', 'our-story', 'mission', 'vision'],
        'services': ['service', 'solution', 'offering', 'product', 'what-we-do', 'capabilities'],
        'expertise': ['expertise', 'specialization', 'capability', 'technology', 'industry'],
        'achievements': ['achievement', 'award', 'recognition', 'milestone', 'success']
    }
    
    for section_type, identifiers in section_identifiers.items():
        content['sections'][section_type] = []
        for identifier in identifiers:
            selectors = [
                f'section.{identifier}',
                f'div.{identifier}',
                f'article.{identifier}',
                f'div[class*="{identifier}"]',
                f'section[class*="{identifier}"]',
                f'article[class*="{identifier}"]'
            ]
            
            for selector in selectors:
                section = soup.select_one(selector)
                if section:
                    paragraphs = section.find_all(['p', 'div'])
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if (30 < len(text) < 1000 and  # Increased max length
                            not any(x in text.lower() for x in ['cookie', 'privacy', 'terms']) and
                            not text.startswith(('©', 'All rights reserved'))):
                            # Clean the text
                            text = ' '.join(text.split())  # Remove extra whitespace
                            content['sections'][section_type].append(text)
    
    # Clean and limit the content with higher limits
    content['headings'] = list(set(content['headings']))[:30]  # Increased to 30 headings
    content['paragraphs'] = list(set(content['paragraphs']))[:50]  # Increased to 50 paragraphs
    
    # Clean sections with higher limits
    for section_type in content['sections']:
        content['sections'][section_type] = list(set(content['sections'][section_type]))[:10]  # Increased to 10 items per section
    
    # Remove empty sections
    content['sections'] = {k: v for k, v in content['sections'].items() if v}
    
    return content

def clean_content(content: Dict) -> Dict:
    """Clean and organize the scraped content with improved filtering"""
    cleaned = {
        'headings': [],
        'paragraphs': [],
        'sections': {},
        'contact_info': {},
        'services': [],
        'locations': []
    }
    
    # Keywords to filter out
    filter_keywords = [
        'cookie', 'privacy', 'terms', '©', 'all rights reserved',
        'follow us', 'subscribe', 'click here', 'close', 'online',
        'first name', 'last name', 'your email', 'phone number',
        'your message', 'submit'
    ]
    
    # Clean headings
    seen_headings = set()
    for heading in content['headings']:
        # Remove extra whitespace and normalize
        heading = ' '.join(heading.split())
        # Filter out unwanted headings
        if (heading and 
            heading not in seen_headings and 
            len(heading) > 3 and
            not any(keyword in heading.lower() for keyword in filter_keywords)):
            cleaned['headings'].append(heading)
            seen_headings.add(heading)
    
    # Clean paragraphs
    seen_paragraphs = set()
    for paragraph in content['paragraphs']:
        # Remove extra whitespace and normalize
        paragraph = ' '.join(paragraph.split())
        # Filter out unwanted paragraphs
        if (len(paragraph) > 30 and 
            paragraph not in seen_paragraphs and
            not any(keyword in paragraph.lower() for keyword in filter_keywords)):
            # Check if it's contact information
            if any(x in paragraph.lower() for x in ['email', 'phone', 'address', 'contact']):
                cleaned['contact_info'][paragraph] = True
            # Check if it's a location
            elif any(x in paragraph.lower() for x in ['floor', 'tower', 'sector', 'street', 'road']):
                cleaned['locations'].append(paragraph)
            # Check if it's a service
            elif any(x in paragraph.lower() for x in ['service', 'development', 'marketing', 'design']):
                cleaned['services'].append(paragraph)
            else:
                cleaned['paragraphs'].append(paragraph)
            seen_paragraphs.add(paragraph)
    
    # Clean sections
    for section_type, items in content['sections'].items():
        cleaned['sections'][section_type] = []
        seen_items = set()
        for item in items:
            # Remove extra whitespace and normalize
            item = ' '.join(item.split())
            # Filter out unwanted items
            if (len(item) > 20 and 
                item not in seen_items and
                not any(keyword in item.lower() for keyword in filter_keywords)):
                cleaned['sections'][section_type].append(item)
                seen_items.add(item)
    
    # Remove empty sections
    cleaned['sections'] = {k: v for k, v in cleaned['sections'].items() if v}
    
    # Convert contact_info set to list
    cleaned['contact_info'] = list(cleaned['contact_info'].keys())
    
    # Remove duplicates from services and locations
    cleaned['services'] = list(set(cleaned['services']))
    cleaned['locations'] = list(set(cleaned['locations']))
    
    return cleaned

    
    

def is_meaningful_scrape(info: Optional[Dict]) -> bool:
    """
    Heuristic to decide whether a scraped 'info' object is meaningful.
    Returns True if info looks usable, False if it's obviously broken/empty.
    """
    if not info:
        return False

    # Check company name for obvious errors
    name = (info.get('company_name') or "").strip().lower()
    if not name:
        # no name is suspicious but not definitive
        pass
    else:
        if any(bad in name for bad in ['privacy', 'certificate', 'error', 'blocked', 'privacy error']):
            return False

    # Check contact richness
    emails = info.get('emails') or []
    phones = info.get('phones') or []
    if emails or phones:
        return True

    # Check content richness
    content = info.get('content') or {}
    paragraphs = content.get('paragraphs', []) or []
    headings = content.get('headings', []) or []

    # If we have at least a few paragraphs or headings it's probably OK
    if len(paragraphs) >= 5 or len(headings) >= 3:
        return True

    # Otherwise treat it as insufficient
    return False


def scrape_website(url: str, cached_html: Optional[str] = None, cached_method: Optional[str] = None) -> Optional[Dict]:
    """
    Main scraping function with enhanced contact page targeting.
    Accepts optional cached_html and cached_method to avoid fetching twice.
    Returns parsed info dict or None.
    """
    # If caller supplied HTML, use it; otherwise fetch it.
    if cached_html is None:
        html, method = get_html(url)
    else:
        html, method = cached_html, cached_method

    if not html:
        print(f"      Failed to retrieve content from the website: {url}")
        return None

    try:
        print(f"      Parsing HTML content...")
        soup = BeautifulSoup(html, 'html.parser')

        # Extract basic information
        print(f"       Extracting company information...")
        info = {
            'company_name': get_company_name(soup),
            'description': get_description(soup),
            'address': get_address(soup),
            'overview': get_company_overview(soup),
            'content': extract_content(soup)
        }

        # ENHANCED: Use the ContactInfoScraper if available
        print(f"       Enhanced contact information extraction...")
        try:
            from enhanced_contact_scraper import ContactInfoScraper
            contact_scraper = ContactInfoScraper()
            enhanced_contact_info = contact_scraper.scrape_all_contact_info(url, soup)

            print(f"       Enhanced scraper results:")
            print(f"         - Emails: {len(enhanced_contact_info.get('emails', []))}")
            print(f"         - Phones: {len(enhanced_contact_info.get('phones', []))}")

            info['detailed_contact_info'] = enhanced_contact_info
            info['emails'] = []
            info['phones'] = []

            for email_item in enhanced_contact_info.get('emails', []):
                if isinstance(email_item, dict) and 'email' in email_item:
                    info['emails'].append(email_item['email'])
                else:
                    info['emails'].append(str(email_item))

            for phone_item in enhanced_contact_info.get('phones', []):
                if isinstance(phone_item, dict) and 'phone' in phone_item:
                    info['phones'].append(phone_item['phone'])
                else:
                    info['phones'].append(str(phone_item))

            print(f"       Final extraction results:")
            print(f"         - Simple emails list: {len(info['emails'])}")
            print(f"         - Simple phones list: {len(info['phones'])}")

        except ImportError as e:
            print(f"       ImportError: Enhanced contact scraper not available: {e}")
            print(f"       Falling back to original contact extraction methods...")

            info['emails'] = get_emails(soup)
            info['phones'] = get_phone_numbers(soup)
            info['detailed_contact_info'] = None

        except Exception as e:
            print(f"       Warning: Enhanced contact extraction failed with error: {e}")
            print(f"       Falling back to original contact extraction methods...")

            info['emails'] = get_emails(soup)
            info['phones'] = clean_phone_numbers(get_phone_numbers(soup))
            info['detailed_contact_info'] = None

        # Social media extraction
        print(f"       Extracting social media links...")
        try:
            from simplified_social_scraper import get_enhanced_social_media_simple
            social_media_links = get_enhanced_social_media_simple(soup, url)
            info['social_media'] = social_media_links
        except ImportError:
            print("       Warning: Simplified social scraper not found, skipping social media")
            info['social_media'] = {}
        except Exception as e:
            print(f"       Warning: Error in social media extraction: {e}")
            info['social_media'] = {}

        # Clean the content
        print(f"      Cleaning and organizing content...")
        cleaned_content = clean_content(info['content'])
        info['content'] = cleaned_content

        # Enhanced print summary
        total_social_platforms = len(info['social_media'])
        total_social_links = sum(len(urls) for urls in info['social_media'].values())

        print(f"      Extracted data summary:")
        print(f"        - Company name: {info['company_name']}")
        print(f"        - Emails found: {len(info['emails'])}")
        print(f"        - Phone numbers: {len(info['phones'])}")
        print(f"        - Addresses found: {len(info.get('addresses_detailed', []))}")
        print(f"        - Social media platforms: {total_social_platforms}")
        print(f"        - Social media links: {total_social_links}")
        print(f"        - Headings: {len(cleaned_content['headings'])}")
        print(f"        - Paragraphs: {len(cleaned_content['paragraphs'])}")

        return info

    except Exception as e:
        print(f"      Error processing content: {str(e)}")
        import traceback
        print(f"      Full error: {traceback.format_exc()}")
        return None

def print_content(content):
    """Print the scraped content with enhanced social media information"""
    if not content:
        return
    
    print("\nWebsite Content:")
    print("=" * 50)
    
    # Print basic information
    if content.get('company_name'):
        print(f"\nCompany Name: {content['company_name']}")
    if content.get('description'):
        print(f"\nDescription: {content['description']}")
    
    # Print contact information
    if any([content.get('emails'), content.get('phones'), content.get('address')]):
        print("\nContact Information:")
        print("-" * 20)
        if content.get('emails'):
            print("\nEmails:")
            for email in content['emails']:
                print(f"- {email}")
        if content.get('phones'):
            print("\nPhone Numbers:")
            for phone in content['phones']:
                print(f"- {phone}")
        if content.get('address'):
            print(f"\nAddress: {content['address']}")
    
    # Enhanced social media display (UPDATED to match your format)
    if content.get('social_media'):
        print("\n🌐 Social Media Presence:")
        print("-" * 20)
        
        total_platforms = len(content['social_media'])
        total_links = sum(len(urls) for urls in content['social_media'].values())
        print(f"Total Platforms: {total_platforms}")
        print(f"Total Links: {total_links}\n")
        
        # Show platforms and links in your preferred format
        for platform, urls in content['social_media'].items():
            print(f"📱 {platform}:")
            for url in urls:
                print(f"   - {url}")
            print()
    
    # Print overview
    if content.get('overview'):
        print("\nCompany Overview:")
        print("-" * 20)
        print(content['overview'])
    
    # Print content sections (existing code continues...)
    if content.get('content'):
        print("\nDetailed Content:")
        print("-" * 20)
        
        # Print contact information
        if content['content'].get('contact_info'):
            print("\nContact Information:")
            for info in content['content']['contact_info']:
                print(f"- {info}")
        
        # Print locations
        if content['content'].get('locations'):
            print("\nOffice Locations:")
            for location in content['content']['locations']:
                print(f"- {location}")
        
        # Print services
        if content['content'].get('services'):
            print("\nServices Offered:")
            for service in content['content']['services']:
                print(f"- {service}")
        
        # Print headings
        if content['content'].get('headings'):
            print("\nKey Headings:")
            for heading in content['content']['headings']:
                print(f"- {heading}")
        
        # Print main content paragraphs
        if content['content'].get('paragraphs'):
            print("\nMain Content:")
            for paragraph in content['content']['paragraphs']:
                print(f"\n{paragraph}")
        
        # Print sections
        if content['content'].get('sections'):
            print("\nDetailed Sections:")
            for section_type, items in content['content']['sections'].items():
                if items:
                    print(f"\n{section_type.title()}:")
                    for item in items:
                        print(f"- {item}")



def scrape_company_by_name(company_name: str) -> Optional[Dict]:
    """
    Main function to scrape company data by company name.

    Flow:
      1) Use search engines to get a scraped_url (find_company_website).
      2) Ask GPT to validate and possibly provide a different URL (get_correct_url).
      3) Try GPT URL first (if present). If fetching fails (both requests & selenium fail) OR parsed result
         is clearly empty/garbage, retry with the original scraped_url.
      4) If both fail, return None.
    """
    print(f"\n{'='*60}")
    print(f" COMPANY SCRAPER: {company_name}")
    print(f"{'='*60}")

    # Step 1: Find the company website (search engine scraped URL)
    scraped_url = find_company_website(company_name)
    if not scraped_url:
        print(f"❌ Could not find website for {company_name}")
        return None
    print(f"  Scraped URL (from search engines): {scraped_url}")

    # Step 2: Ask GPT to validate / correct the scraped URL
    try:
        suggest = get_correct_url(company_name, scraped_url)
        gpt_url = (suggest.get("url") if isinstance(suggest, dict) else None)
    except Exception as e:
        print(f"⚠️ Error calling get_correct_url(): {e}")
        gpt_url = None

    # Normalize and decide which URL(s) to try
    def normalize(u: Optional[str]) -> Optional[str]:
        if not u:
            return None
        u = u.strip()
        if not u.startswith(('http://', 'https://')):
            u = 'https://' + u
        return u

    gpt_url = normalize(gpt_url)
    scraped_url = normalize(scraped_url)

    tried_urls = []

    # Helper to attempt a URL: first get_html() to detect whether requests & selenium succeed,
    # then parse via scrape_website (using cached HTML to avoid double fetch).
    def attempt_url(url_to_try: str) -> Optional[Dict]:
        print(f"\n🌐 Attempting to scrape candidate URL: {url_to_try}")
        tried_urls.append(url_to_try)

        html, method = get_html(url_to_try)
        if not html:
            print(f"    ❌ Both requests and Selenium failed for {url_to_try}")
            return None

        print(f"    ✅ Fetch succeeded via '{method}' for {url_to_try} (parsing...)")
        parsed_info = scrape_website(url_to_try, cached_html=html, cached_method=method)

        # If parse returns something but it's not meaningful, mark as failed
        if parsed_info and is_meaningful_scrape(parsed_info):
            print(f"    ✅ Parsed content looks meaningful for {url_to_try}")
            return parsed_info
        else:
            print(f"    ⚠️ Parsed content looks insufficient or suspicious for {url_to_try}")
            return None

    # Try GPT URL first (if available and different); otherwise try scraped_url first
    if gpt_url and gpt_url != scraped_url:
        print(f"  GPT suggested URL: {gpt_url}")
        result = attempt_url(gpt_url)
        if result:
            print("✅ Successfully scraped using GPT-provided URL")
            result['searched_company_name'] = company_name
            result['website_url'] = gpt_url
            return result
        else:
            print("❌ GPT-provided URL failed → falling back to scraped search-engine URL")

    # Now try the scraped_url (search-engine result)
    print(f"  Trying scraped/search-engine URL: {scraped_url}")
    result = attempt_url(scraped_url)
    if result:
        print("✅ Successfully scraped using scraped/search-engine URL")
        result['searched_company_name'] = company_name
        result['website_url'] = scraped_url
        return result

    # If we reach here both attempts failed
    print("🚨 All attempts failed. No data extracted.")
    print(f"  Tried URLs: {tried_urls}")
    return None





def scrape_company_by_domain(domain: str) -> Optional[Dict]:

    print(f"\n{'='*60}")
    print(f" COMPANY SCRAPER: {domain}")
    print(f"{'='*60}")

    # Normalize and decide which URL(s) to try
    def normalize(u: Optional[str]) -> Optional[str]:
        if not u:
            return None
        u = u.strip()
        if not u.startswith(('http://', 'https://')):
            u = 'https://' + u
        return u

    scraped_url = normalize(domain)
    gpt_url = normalize(domain)

    tried_urls = []

    def attempt_url(url_to_try: str) -> Optional[Dict]:
        print(f"\n🌐 Attempting to scrape candidate URL: {url_to_try}")
        tried_urls.append(url_to_try)

        html, method = get_html(url_to_try)
        if not html:
            print(f"    ❌ Both requests and Selenium failed for {url_to_try}")
            return None

        print(f"    ✅ Fetch succeeded via '{method}' for {url_to_try} (parsing...)")
        parsed_info = scrape_website(url_to_try, cached_html=html, cached_method=method)

        # If parse returns something but it's not meaningful, mark as failed
        if parsed_info and is_meaningful_scrape(parsed_info):
            print(f"    ✅ Parsed content looks meaningful for {url_to_try}")
            return parsed_info
        else:
            print(f"    ⚠️ Parsed content looks insufficient or suspicious for {url_to_try}")
            return None
        
    # Try the domain directly
    print(f"  Trying scraped/search-engine URL: {scraped_url}")
    result = attempt_url(scraped_url)
    if result:
        print("✅ Successfully scraped using scraped/search-engine URL")
        result['searched_company_name'] = domain
        result['website_url'] = scraped_url
        return result
    
    # if not Find the company website (search engine scraped URL)
    scraped_url = find_company_website(domain)
    if not scraped_url:
        print(f"❌ Could not find website for {domain}")
        return None
    print(f"  Scraped URL (from search engines): {scraped_url}")

    # Ask GPT to validate / correct the scraped URL
    try:
        suggest = get_correct_url(domain, scraped_url)
        gpt_url = (suggest.get("url") if isinstance(suggest, dict) else None)
    except Exception as e:
        print(f"⚠️ Error calling get_correct_url(): {e}")
        gpt_url = None

    # Try GPT URL first (if available and different); otherwise try scraped_url first
    if gpt_url and gpt_url != scraped_url:
        print(f"  GPT suggested URL: {gpt_url}")
        result = attempt_url(gpt_url)
        if result:
            print("✅ Successfully scraped using GPT-provided URL")
            result['searched_company_name'] = domain
            result['website_url'] = gpt_url
            return result
        else:
            print("❌ GPT-provided URL failed → falling back to scraped search-engine URL")

    # Now try the scraped_url (search-engine result)
    print(f"  Trying scraped/search-engine URL: {scraped_url}")
    result = attempt_url(scraped_url)
    if result:
        print("✅ Successfully scraped using scraped/search-engine URL")
        result['searched_company_name'] = domain
        result['website_url'] = scraped_url
        return result

    # If we reach here both attempts failed
    print("🚨 All attempts failed. No data extracted.")
    print(f"  Tried URLs: {tried_urls}")
    return None