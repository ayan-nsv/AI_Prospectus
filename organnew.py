import re
import time
import random
import requests

import urllib3
import urllib.parse

from bs4 import BeautifulSoup
from fake_useragent import UserAgent

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import logging
logger = logging.getLogger(__name__)


def get_org_number(company_name, max_attempts=2):
    """
    Get organization number for a company name with retries
    Args:
        company_name (str): The name of the company to search for
        max_attempts (int): How many retry rounds to do
    Returns:
        str: Organization number or "Not found" if not found
    """
    print(f"  🔢 Searching for org number: {company_name}")
    
    ua = UserAgent()
    
    # Strategy 1: Try direct Allabolag access first (most reliable)
    org_num = try_direct_allabolag(company_name, ua)
    if org_num != "Not found":
        return org_num
    
    # Strategy 2: Try Allabolag search page
    org_num = try_allabolag_search(company_name, ua, max_attempts)
    if org_num != "Not found":
        return org_num
    
    # Strategy 3: Try DuckDuckGo (less aggressive blocking)
    org_num = try_duckduckgo_search(company_name, ua, max_attempts)
    if org_num != "Not found":
        return org_num
    
    print(f"    ❌ No organization number found after all attempts")
    return "Not found"


def try_direct_allabolag(company_name, ua):
    """Try direct URL patterns on allabolag.se"""
    print(f"    🔍 Trying direct allabolag.se access...")
    
    # Try multiple URL patterns
    url_variations = [
        company_name.lower().replace(' ', '-'),
        company_name.lower().replace(' ', ''),
        company_name.lower()
    ]
    
    for url_suffix in url_variations:
        try:
            url = f"https://www.allabolag.se/{url_suffix}"
            
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Referer": "https://www.allabolag.se/"
            }
            
            time.sleep(random.uniform(1.5, 3))
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            
            if response.status_code == 200:
                org_num = extract_org_number(response.text)
                if org_num:
                    print(f"    ✅ Found org number directly: {org_num}")
                    return org_num
                    
        except Exception as e:
            print(f"    ⚠️  Error with URL {url_suffix}: {str(e)[:50]}")
            continue
    
    return "Not found"


def try_allabolag_search(company_name, ua, max_attempts):
    """Try Allabolag's search functionality"""
    print(f"    🔍 Trying allabolag.se search...")
    
    for attempt in range(max_attempts):
        try:
            search_url = f"https://www.allabolag.se/what/{urllib.parse.quote(company_name)}"
            
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://www.allabolag.se/"
            }
            
            time.sleep(random.uniform(2, 4))
            response = requests.get(search_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                org_num = extract_org_number(response.text)
                if org_num:
                    print(f"    ✅ Found org number via search: {org_num}")
                    return org_num
                    
        except Exception as e:
            print(f"    ⚠️  Search attempt {attempt + 1} error: {str(e)[:50]}")
            continue
    
    return "Not found"


def try_duckduckgo_search(company_name, ua, max_attempts):
    """Try DuckDuckGo search (less aggressive blocking than Google/Bing)"""
    print(f"    🔍 Trying DuckDuckGo search...")
    
    for attempt in range(max_attempts):
        try:
            query = f"{company_name} organisationsnummer site:allabolag.se"
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            
            headers = {
                "User-Agent": ua.random,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            time.sleep(random.uniform(3, 5))
            response = requests.get(search_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Look for allabolag.se links in results
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if 'allabolag.se' in href and not '/what/' in href:
                        # Found a company page, try to fetch it
                        try:
                            actual_url = extract_actual_url(href)
                            if actual_url:
                                time.sleep(random.uniform(2, 3))
                                page_response = requests.get(actual_url, headers=headers, timeout=15)
                                if page_response.status_code == 200:
                                    org_num = extract_org_number(page_response.text)
                                    if org_num:
                                        print(f"    ✅ Found org number via DuckDuckGo: {org_num}")
                                        return org_num
                        except:
                            continue
                            
        except Exception as e:
            print(f"    ⚠️  DuckDuckGo attempt {attempt + 1} error: {str(e)[:50]}")
            continue
    
    return "Not found"


def extract_org_number(html_text):
    """Extract organization number from HTML text using multiple patterns"""
    # Pattern 1: With label
    match = re.search(r"[Oo]rganisationsnummer[:\s]*([0-9]{6}[-\s]?[0-9]{4})", html_text)
    if match:
        return match.group(1).replace(' ', '-')
    
    # Pattern 2: Direct format XXXXXX-XXXX
    match = re.search(r"\b([0-9]{6}-[0-9]{4})\b", html_text)
    if match:
        return match.group(1)
    
    # Pattern 3: Format without dash
    match = re.search(r"\b([0-9]{10})\b", html_text)
    if match:
        num = match.group(1)
        return f"{num[:6]}-{num[6:]}"
    
    return None


def extract_actual_url(duckduckgo_url):
    """Extract actual URL from DuckDuckGo redirect URL"""
    try:
        if 'uddg=' in duckduckgo_url:
            return urllib.parse.unquote(duckduckgo_url.split('uddg=')[1].split('&')[0])
        return duckduckgo_url
    except:
        return None

##########################################################################################
def get_company_data(org_number):
    """Get company data using the organization number"""
    try:
        from allabolag import Company
        company = Company(org_number)
        return company.data
    except Exception as e:
        logger.error(f"Error getting company data: {str(e)}")
        return None





