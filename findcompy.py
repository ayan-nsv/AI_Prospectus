from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import re
from urllib.parse import urlparse

def search_company_google(email: str) -> str:
    domain = email.split('@')[-1].strip()  # FIXED: removed [0]
    query = f"{domain} company"

    print(f"🔍 Searching Google for: {query}")

    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/google-chrome-stable" 
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_page_load_timeout(30)
        
        print(f"🌐 Loading Google search...")
        driver.get(f"https://www.google.com/search?q={query}")
        
        # Wait for results to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.g, div.tF2Cxc, h3"))
            )
        except TimeoutException:
            print("⏱️ Timeout waiting for Google results")
            return None
        
        time.sleep(2)  # Additional settling time

        # Try multiple selectors for Google search results
        selectors_to_try = [
            "div.tF2Cxc",  # Most reliable modern selector
            "div.g",  # Standard Google result container
            "div[data-sokoban-container]",  # Alternative container
            "div.yuRUbf",  # Another common selector
        ]
        
        results_found = []
        for selector in selectors_to_try:
            try:
                print(f"🔍 Trying selector: {selector}")
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"   Found {len(elements)} elements with {selector}")
                
                if elements:
                    for i, element in enumerate(elements[:10]):  # Check more results
                        try:
                            # Get title from h3
                            title_elem = element.find_element(By.CSS_SELECTOR, "h3")
                            title = title_elem.text.strip()
                            
                            # Get link
                            link = ""
                            try:
                                link_elem = element.find_element(By.CSS_SELECTOR, "a")
                                link = link_elem.get_attribute("href")
                            except:
                                pass
                            
                            if title and len(title) > 2:
                                results_found.append({
                                    'title': title,
                                    'link': link,
                                    'selector': selector,
                                    'index': i
                                })
                                print(f"   📄 Result {i+1}: {title[:60]}...")
                                
                        except Exception as e:
                            continue
                    
                    if results_found:
                        break  # Found results with this selector
                        
            except Exception as e:
                print(f"   ❌ Selector {selector} failed: {e}")
                continue

        print(f"📊 Total results found: {len(results_found)}")
        
        # Extract domain parts for matching
        domain_base = extract_domain_base(domain)
        
        # Score and rank results
        scored_results = []
        for result in results_found:
            score = score_result(result['title'], result['link'], domain, domain_base)
            scored_results.append({**result, 'score': score})
        
        # Sort by score (highest first)
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Return the best match if it meets threshold
        if scored_results and scored_results[0]['score'] > 0:
            best = scored_results[0]
            print(f"✅ Best match (score: {best['score']}): {best['title']}")
            return clean_company_name(best['title'])

        print("❌ Google search failed to find valid company name")
        return None

    except Exception as e:
        print(f"❌ Google search error: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def search_company_bing(email: str) -> str:
    domain = email.split('@')[-1].strip()
    query = f"{domain} company"

    print(f"🔍 Searching Bing for: {query}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_page_load_timeout(30)
        
        print(f"🌐 Loading Bing search...")
        driver.get(f"https://www.bing.com/search?q={query}")
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.b_algo, h2 a"))
            )
        except TimeoutException:
            print("⏱️ Timeout waiting for Bing results")
            return None
            
        time.sleep(2)

        # Bing selectors
        selectors_to_try = [
            "li.b_algo",  # Standard Bing result container
            "div.b_title",  # Title container
        ]
        
        results_found = []
        for selector in selectors_to_try:
            try:
                print(f"🔍 Trying Bing selector: {selector}")
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"   Found {len(elements)} elements with {selector}")
                
                if elements:
                    for i, element in enumerate(elements[:10]):
                        try:
                            title_elem = element.find_element(By.CSS_SELECTOR, "h2 a, a")
                            title = title_elem.text.strip()
                            link = title_elem.get_attribute("href")
                            
                            if title and len(title) > 2:
                                results_found.append({
                                    'title': title,
                                    'link': link,
                                    'index': i
                                })
                                print(f"   📄 Bing Result {i+1}: {title[:60]}...")
                                
                        except Exception as e:
                            continue
                    
                    if results_found:
                        break
                        
            except Exception as e:
                print(f"   ❌ Bing selector {selector} failed: {e}")
                continue

        print(f"📊 Total Bing results found: {len(results_found)}")
        
        domain_base = extract_domain_base(domain)
        
        # Score results
        scored_results = []
        for result in results_found:
            score = score_result(result['title'], result['link'], domain, domain_base)
            scored_results.append({**result, 'score': score})
        
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        if scored_results and scored_results[0]['score'] > 0:
            best = scored_results[0]
            print(f"✅ Best Bing match (score: {best['score']}): {best['title']}")
            return clean_company_name(best['title'])

        print("❌ Bing search failed to find valid company name")
        return None

    except Exception as e:
        print(f"❌ Bing search error: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def search_company_duckduckgo(email: str) -> str:
    domain = email.split('@')[-1].strip()
    query = f"{domain} company"

    print(f"🔍 Searching DuckDuckGo for: {query}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_page_load_timeout(30)
        
        print(f"🌐 Loading DuckDuckGo search...")
        driver.get(f"https://duckduckgo.com/?q={query}")
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article, h2"))
            )
        except TimeoutException:
            print("⏱️ Timeout waiting for DuckDuckGo results")
            return None
            
        time.sleep(2)

        # DuckDuckGo selectors
        selectors_to_try = [
            "article[data-testid='result']",  # Modern DDG
            "article",  # Standard DuckDuckGo result container
            "div.result",  # Older selector
        ]
        
        results_found = []
        for selector in selectors_to_try:
            try:
                print(f"🔍 Trying DuckDuckGo selector: {selector}")
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"   Found {len(elements)} elements with {selector}")
                
                if elements:
                    for i, element in enumerate(elements[:10]):
                        try:
                            # Try multiple ways to find title link
                            title_elem = None
                            try:
                                title_elem = element.find_element(By.CSS_SELECTOR, "h2 a")
                            except:
                                try:
                                    title_elem = element.find_element(By.CSS_SELECTOR, "a[data-testid='result-title-a']")
                                except:
                                    title_elem = element.find_element(By.CSS_SELECTOR, "a")
                            
                            title = title_elem.text.strip()
                            link = title_elem.get_attribute("href")
                            
                            if title and len(title) > 2:
                                results_found.append({
                                    'title': title,
                                    'link': link,
                                    'index': i
                                })
                                print(f"   📄 DuckDuckGo Result {i+1}: {title[:60]}")
                                
                        except Exception as e:
                            continue
                    
                    if results_found:
                        break
                        
            except Exception as e:
                print(f"   ❌ DuckDuckGo selector {selector} failed: {e}")
                continue

        print(f"📊 Total DuckDuckGo results found: {len(results_found)}")
        
        domain_base = extract_domain_base(domain)
        
        # Score results
        scored_results = []
        for result in results_found:
            score = score_result(result['title'], result['link'], domain, domain_base)
            scored_results.append({**result, 'score': score})
        
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        if scored_results and scored_results[0]['score'] > 0:
            best = scored_results[0]
            print(f"✅ Best DDG match (score: {best['score']}): {best['title']}")
            return clean_company_name(best['title'])

        print("❌ DuckDuckGo search failed to find valid company name")
        return None

    except Exception as e:
        print(f"❌ DuckDuckGo search error: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def extract_domain_base(domain: str) -> str:
    """Extract the main part of domain (e.g., 'google' from 'google.com')"""
    parts = domain.split('.')
    # Handle cases like co.uk, com.au
    if len(parts) >= 2:
        return parts[-2].lower()
    return domain.lower()


def score_result(title: str, link: str, full_domain: str, domain_base: str) -> int:
    """
    Score a search result based on relevance to the domain.
    Higher score = better match
    """
    score = 0
    title_lower = title.lower()
    link_lower = link.lower() if link else ""
    
    # Parse URL domain
    url_domain = ""
    if link:
        try:
            parsed = urlparse(link)
            url_domain = parsed.netloc.lower()
        except:
            pass
    
    # Strong positive signals
    if domain_base in url_domain:
        score += 100  # Link contains the domain
    
    if full_domain in url_domain:
        score += 50  # Exact domain match
    
    # Company name in title (without common suffixes)
    clean_title = clean_company_name(title).lower()
    if domain_base in clean_title:
        score += 30
    
    # Check for official site indicators
    official_indicators = ['official site', 'official website', 'homepage', 'home page']
    if any(indicator in title_lower for indicator in official_indicators):
        score += 20
    
    # Negative signals - these are NOT what we want
    bad_patterns = [
        'wikipedia', 'wiki', 'linkedin', 'facebook', 'twitter', 'instagram',
        'crunchbase', 'bloomberg', 'yahoo finance', 'google maps',
        'yelp', 'tripadvisor', 'directory', 'yellow pages',
        'search', 'find', 'locate', 'list of', 'companies like',
        'careers at', 'jobs at', 'reviews of', 'complaints about',
        'news about', 'articles about', 'information about'
    ]
    
    for pattern in bad_patterns:
        if pattern in title_lower:
            score -= 50
            break
    
    # Check for overly generic titles
    if len(clean_title) < 3 or len(title.split()) > 15:
        score -= 20
    
    return score


def clean_company_name(title: str) -> str:
    """
    Clean up company name from search result title.
    Remove common suffixes, separators, and noise.
    """
    # Split on common separators and take first part
    for sep in [' - ', ' – ', ' — ', ' | ', ' : ', ' :: ']:
        if sep in title:
            parts = title.split(sep)
            # Take the first non-empty part
            for part in parts:
                part = part.strip()
                if len(part) > 2 and not is_generic_suffix(part):
                    title = part
                    break
            break
    
    # Remove common trailing patterns
    patterns_to_remove = [
        r'\s*-\s*Official Site.*$',
        r'\s*\|\s*Official.*$',
        r'\s*-\s*Wikipedia.*$',
        r'\s*-\s*LinkedIn.*$',
        r'\s*-\s*Crunchbase.*$',
        r'\s*-\s*Home.*$',
        r'\s*-\s*About.*$',
        r'\s*\(.*?\)\s*$',  # Remove trailing parentheses
        r'\s*\.{2,}$',  # Remove trailing ellipsis
        r'\s*-\s*GOV\.UK$',
        r'\s*-\s*Find and update company information$',
        r'\s*-\s*Company Profile$',
    ]
    
    for pattern in patterns_to_remove:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    title = ' '.join(title.split())
    
    return title.strip()


def is_generic_suffix(text: str) -> bool:
    """Check if text is a generic suffix we should ignore"""
    generic = [
        'official site', 'official website', 'home', 'homepage',
        'about us', 'about', 'wikipedia', 'linkedin', 'facebook',
        'overview', 'profile', 'crunchbase', 'company profile'
    ]
    return text.lower().strip() in generic


def format_domain_name(domain: str) -> str:
    """Format domain name as a fallback company name"""
    # Remove common TLD
    domain = re.sub(r'\.(com|org|net|io|co|uk|us|in)$', '', domain, flags=re.IGNORECASE)
    
    # Handle mixed names like 87sixty -> "87sixty" (keep original casing)
    if any(c.isdigit() for c in domain):
        # Split on digit boundaries
        parts = re.split(r'(\d+)', domain)
        return ''.join([p.title() if p and not p.isdigit() else p for p in parts if p])
    
    return domain.title()


def search_company_with_fallbacks(email: str) -> str:
    """
    Main function that tries multiple search engines with fallbacks
    """
    domain = email.split('@')[-1].strip()
    
    print(f"🚀 Starting company search for: {email}")
    print(f"📧 Domain: {domain}")
    
    # Try Google first
    print("\n" + "="*50)
    print("🔍 ATTEMPT 1: Google Search")
    print("="*50)
    result = search_company_google(email)
    if result:
        return result
    
    # Try Bing if Google fails
    print("\n" + "="*50)
    print("🔍 ATTEMPT 2: Bing Search")
    print("="*50)
    result = search_company_bing(email)
    if result:
        return result
    
    # Try DuckDuckGo if Bing fails
    print("\n" + "="*50)
    print("🔍 ATTEMPT 3: DuckDuckGo Search")
    print("="*50)
    result = search_company_duckduckgo(email)
    if result:
        return result
    
    # Final fallback to formatted domain
    print("\n" + "="*50)
    print("⚠️ ALL SEARCH ENGINES FAILED - USING DOMAIN FALLBACK")
    print("="*50)
    fallback = format_domain_name(domain.split('.')[0])
    print(f"⚠️ Using fallback: {fallback}")
    return fallback


# Example usage
# if __name__ == "__main__":
#     test_emails = [
#         "user@funnelbud.com",
#         "danny@arjtransport.com"
#     ]
    
#     for email in test_emails:
#         print("\n" + "="*70)
#         result = search_company_with_fallbacks(email)
#         print(f"\n🎯 FINAL RESULT for {email}: {result}")
#         print("="*70 + "\n")