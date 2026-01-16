import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging

logger = logging.getLogger(__name__)

class ContactInfoScraper:
    """Enhanced scraper that targets specific pages likely to contain contact information"""
    
    def __init__(self):
        self.contact_keywords = {
            'english': [
                'contact', 'contact-us', 'contact_us', 'contactus',
                'about', 'about-us', 'about_us', 'aboutus',
                'reach-us', 'get-in-touch'
            ],
            'swedish': [
                'kontakt', 'kontakta-oss', 'kontakta_oss',
                'om-oss', 'om_oss', 'omoss', 'om',
                'hitta-oss', 'kontaktaoss'
            ]
        }
        
    def find_contact_pages(self, base_url, soup):
        """Find URLs of pages likely to contain contact information with strict keyword matching"""
        contact_urls = set()
        
        # Get all links from the homepage
        all_links = soup.find_all('a', href=True)
        
        print(f"      Scanning {len(all_links)} links for contact pages...")
        
        for link in all_links:
            href = link.get('href', '').strip()
            if not href:
                continue
                
            # Convert relative URLs to absolute
            if href.startswith('/'):
                full_url = urljoin(base_url, href)
            elif href.startswith(('http://', 'https://')):
                full_url = href
            else:
                full_url = urljoin(base_url, href)
            
            # Parse URL to get clean path segments
            url_path = urlparse(full_url).path.lower().strip('/')
            link_text = link.get_text(strip=True).lower()
            
            # Get all keywords
            all_keywords = self.contact_keywords['english'] + self.contact_keywords['swedish']
            
            # Check for EXACT keyword matches with word boundaries
            found_match = False
            matched_keyword = None
            
            for keyword in all_keywords:
                # Check if keyword appears as a complete word or path segment
                # This prevents partial matches like "about" matching "aboutus" incorrectly
                
                # Check in URL path segments (split by / and -)
                path_segments = url_path.replace('-', '/').replace('_', '/').split('/')
                if keyword in path_segments:
                    found_match = True
                    matched_keyword = keyword
                    break
                
                # Check in link text as whole word
                import re
                if re.search(rf'\b{re.escape(keyword)}\b', link_text):
                    found_match = True
                    matched_keyword = keyword
                    break
                
                # Check in href as whole word/segment
                if re.search(rf'\b{re.escape(keyword)}\b', href.lower()):
                    found_match = True
                    matched_keyword = keyword
                    break
            
            if found_match:

                # Skip URLs with certain patterns that are unlikely to be contact pages
                skip_patterns = [
                    'client', 'customer', 'case', 'story', 'news', 'blog', 'article',
                    'product', 'service', 'solution', 'partner', 'career', 'job',
                    'login', 'register', 'signup', 'download', 'resource'
                ]
                
                should_skip = False
                for skip_pattern in skip_patterns:
                    if skip_pattern in url_path and matched_keyword != skip_pattern:
                        should_skip = True
                        print(f"        Skipping {full_url} (contains '{skip_pattern}', not a contact page)")
                        break
                
                if not should_skip:
                    contact_urls.add(full_url)
                    print(f"        Found contact page: {full_url} (keyword: {matched_keyword})")
        
        return list(contact_urls)
    
    
    def scrape_contact_info_from_page(self, url):
        print(f"        Scraping contact info from: {url}")
        
        try:
            # Try requests first
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                print("parsing url", url)
                # Pass the specific page URL (url) - this is the key fix
                return self.extract_contact_info(soup, url)
            else:
                print(f"          HTTP {response.status_code}, trying Selenium...")
                return self.scrape_with_selenium(url)
                
        except Exception as e:
            print(f"          Requests failed: {e}, trying Selenium...")
            return self.scrape_with_selenium(url)

    def scrape_with_selenium(self, url):
        """Fallback scraping using Selenium"""
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = None
        try:
            # Get ChromeDriver path with better error handling
            try:
                driver_path = ChromeDriverManager().install()
            except Exception as e:
                logger.error(f"Failed to install/get ChromeDriver: {e}")
                print(f"          ChromeDriver installation failed: {str(e)}")
                return {'emails': [], 'phones': [], 'addresses': []}
            
            # Create service with explicit path
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(20)
            driver.get(url)
            time.sleep(3)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # Pass the specific page URL (url) - this is the key fix
            return self.extract_contact_info(soup, url)
            
        except Exception as e:
            print(f"          Selenium failed: {e}")
            return {'emails': [], 'phones': [], 'addresses': []}
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        
    def extract_contact_info(self, soup, source_url):
        """Extract emails, phones, and addresses from soup with exact source URL"""
        # Remove script and style elements
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        
        # Get all text content
        all_text = soup.get_text(separator=' ')
        
        # Also check href attributes for mailto and tel links on specific pages (not homepage)
        parsed_url = urlparse(source_url)
        homepage_indicators = ['/', '/home', '/index', '/index.html', '/index.php']
        is_homepage = parsed_url.path.lower() in homepage_indicators or parsed_url.path == ''
        
        if not is_homepage: 
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if href.startswith('mailto:'):
                    all_text += ' ' + href
                elif href.startswith('tel:'):
                    all_text += ' ' + href

        return {
            'emails': self.extract_emails(all_text, source_url, soup),  # Pass soup for role detection
            'phones': self.extract_phones(all_text, source_url),
            'addresses': self.extract_addresses(soup, source_url)
        }
        
    def extract_emails(self, text, source_url, soup=None):
        """Enhanced email extraction with exact source URL and role detection"""
        # Multiple email patterns
        patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',
        ]
        
        emails = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            emails.extend(matches)
        
        # Filter out common false positives
        valid_emails = []
        invalid_patterns = [
            'example.com', 'domain.com', 'email@', 'test@',
            'noreply@', 'no-reply@', 'donotreply@'
        ]
        
        for email in set(emails):
            email = email.strip().lower()
            if (len(email) > 5 and 
                '.' in email and 
                not any(invalid in email for invalid in invalid_patterns)):
                print(f"          Found email: {email} from {source_url}")

               ## now look for firstname and lastname
                email_parts = email.split('@')[0].split('.')
                firstname = None
                lastname = None
                role = None
                
                # List of generic email prefixes that are not personal names
                generic_prefixes = [
                    'info', 'hello', 'contact', 'support', 'sales', 'admin', 
                    'help', 'mail', 'office', 'team', 'general', 'service',
                    'inquiries', 'inquiry', 'welcome', 'feedback', 'careers',
                    'jobs', 'hr', 'press', 'media', 'marketing', 'webmaster',
                    'postmaster', 'hostmaster', 'abuse', 'security', 'privacy'
                ]
                
                # Only extract names if the email doesn't start with a generic prefix
                first_part = email_parts[0].lower()
                if first_part not in generic_prefixes:
                    if len(email_parts) >= 2:
                        # If we have at least 2 parts, take first as firstname, last as lastname
                        firstname = email_parts[0].capitalize()
                        lastname = email_parts[-1].capitalize()
                    elif len(email_parts) == 1:
                        # If only one part, use it as firstname
                        firstname = email_parts[0].capitalize()
                
                # Try to detect role/title if soup is provided
                if soup:
                    role = self.detect_role_near_email(soup, email)
                
                valid_emails.append({
                    'email': email,
                    'source': source_url,
                    'firstname': firstname,
                    'lastname': lastname,
                    'role': role  # Added role field
                })
        
        return valid_emails
    
    def detect_role_near_email(self, soup, email):
        """Detect job title/role near an email address in the HTML"""
        # Common executive and leadership roles
        role_keywords = {
            'ceo': ['ceo', 'chief executive officer', 'vd', 'verkställande direktör'],
            'cto': ['cto', 'chief technology officer', 'tekniskt ansvarig', 'teknisk chef'],
            'cfo': ['cfo', 'chief financial officer', 'ekonomidirektör', 'finansiell chef'],
            'coo': ['coo', 'chief operating officer', 'operativ chef'],
            'cmo': ['cmo', 'chief marketing officer', 'marknadschef'],
            'founder': ['founder', 'grundare', 'co-founder', 'medgrundare'],
            'director': ['director', 'direktör', 'managing director', 'verkställande direktör'],
            'manager': ['manager', 'chef', 'vd', 'ledare'],
            'head': ['head of', 'chef för', 'ansvarig för'],
            'lead': ['lead', 'ledare', 'senior lead']
        }
        
        # Find elements containing the email
        email_lower = email.lower()
        elements_with_email = []
        
        # Search in various HTML elements
        for element in soup.find_all(['p', 'div', 'li', 'td', 'span', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = element.get_text(separator=' ', strip=True).lower()
            if email_lower in text:
                elements_with_email.append(element)
        
        # Search for role keywords near the email
        for element in elements_with_email[:5]:  # Limit search to avoid false positives
            text = element.get_text(separator=' ', strip=True).lower()
            
            # Check each role category
            for role_name, keywords in role_keywords.items():
                for keyword in keywords:
                    # Check if keyword appears near the email (within 50 characters)
                    email_pos = text.find(email_lower)
                    if email_pos != -1:
                        # Search in a window around the email
                        start = max(0, email_pos - 100)
                        end = min(len(text), email_pos + 100)
                        context = text[start:end]
                        
                        if keyword.lower() in context:
                            return role_name.upper()
            
            # Also check parent and sibling elements for role information
            parent = element.find_parent()
            if parent:
                parent_text = parent.get_text(separator=' ', strip=True).lower()
                for role_name, keywords in role_keywords.items():
                    for keyword in keywords:
                        if keyword.lower() in parent_text:
                            return role_name.upper()
        
        return None
    
    def extract_phones(self, text, source_url):
        patterns = [
            # International formats
            r'\+\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}',
            r'\+\d{1,4}(?:\s?\(0\))?(?:[\s\-]?\d{1,4}){2,5}',
            # Swedish formats
            r'0(?:[\s\-]?\d){8,16}',
        ]
        
        phones = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)

        valid_phones = []
        for phone in set(phones):
            digits_only = re.sub(r'[^\d]', '', phone)
            if len(digits_only) >= 7: 
                print(f"          Found phone: {phone.strip()} from {source_url}")
                valid_phones.append({
                    'phone': phone.strip(),
                    'source': source_url 
                })
        
        return valid_phones
    
    def extract_addresses(self, soup, source_url):
        addresses = []
        
        address_selectors = [
            'address',
            '[class*="address"]',
            '[class*="location"]',
            '[class*="contact"]',
            '[id*="address"]',
            '[id*="location"]'
        ]
        
        for selector in address_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(separator=' ', strip=True)
                if self.is_likely_address(text):
                    print(f"          Found address: {text[:50]}... from {source_url}")
                    addresses.append({
                        'address': text,
                        'source': source_url 
                    })
        
        all_paragraphs = soup.find_all(['p', 'div'])
        for p in all_paragraphs:
            text = p.get_text(separator=' ', strip=True)
            if self.is_likely_address(text) and len(text) < 200:
                print(f"          Found address: {text[:50]}... from {source_url}")
                addresses.append({
                    'address': text,
                    'source': source_url 
                })
        
        return addresses[:5] 
    
    def is_likely_address(self, text):
        """Heuristic to determine if text looks like an address"""
        if len(text) < 20 or len(text) > 200:
            return False
        
       
        swedish_indicators = [
            'sverige', 'sweden', 'stockholm', 'göteborg', 'malmö',
            'gatan', 'vägen', 'torget', 'storgatan', 'box', 'postbox'
        ]
        
        address_indicators = [
            'street', 'avenue', 'road', 'boulevard', 'lane', 'drive',
            'zip', 'postal', 'code', 'suite', 'floor', 'building'
        ]
        
        text_lower = text.lower()
        
      
        if not re.search(r'\d', text):
            return False
        
    
        indicators_found = (
            any(ind in text_lower for ind in swedish_indicators) or
            any(ind in text_lower for ind in address_indicators)
        )
        
        return indicators_found
    
    def scrape_all_contact_info(self, base_url, homepage_soup):
        """Main method to scrape contact info from multiple pages with exact source URLs"""
        print(f"    Starting comprehensive contact info extraction...")

        all_contact_info = {
            'emails': [],
            'phones': [],
            'addresses': []
        }

        parsed = urlparse(base_url)
        homepage_url = f"{parsed.scheme}://{parsed.netloc}/"

      
        print(f"      Extracting from homepage: {homepage_url}")
        homepage_info = self.extract_contact_info(homepage_soup, homepage_url)

        for key in all_contact_info:
            all_contact_info[key].extend(homepage_info[key])

       
        contact_pages = self.find_contact_pages(base_url, homepage_soup)

        print(f"      Found {len(contact_pages)} potential contact pages")

        for page_url in contact_pages[:5]:  # Limit to 5 pages to avoid being blocked
            try:
                print(f"      Processing contact page: {page_url}")
                page_info = self.scrape_contact_info_from_page(page_url)

                for key in all_contact_info:
                    if key in page_info:
                        all_contact_info[key].extend(page_info[key])

                time.sleep(2) 

            except Exception as e:
                print(f"        Failed to scrape {page_url}: {e}")
                continue

        # Remove duplicates while preserving source information
        for key in all_contact_info:
            seen = set()
            unique_items = []
            for item in all_contact_info[key]:
                
                identifier = item.get('email') or item.get('phone') or item.get('address')
                if identifier and identifier not in seen:
                    seen.add(identifier)
                    unique_items.append(item)
            all_contact_info[key] = unique_items

        print(f"      Total extracted:")
        print(f"        - Emails: {len(all_contact_info['emails'])}")
        print(f"        - Phones: {len(all_contact_info['phones'])}")
        print(f"        - Addresses: {len(all_contact_info['addresses'])}")

        # Print some sample results for debugging
        if all_contact_info['emails']:
            print(f"      Sample emails found:")
            for i, email_item in enumerate(all_contact_info['emails'][:3]):
                print(f"        {i+1}. {email_item.get('email', 'N/A')} from {email_item.get('source', 'N/A')}")
        
        if all_contact_info['phones']:
            print(f"      Sample phones found:")
            for i, phone_item in enumerate(all_contact_info['phones'][:3]):
                print(f"        {i+1}. {phone_item.get('phone', 'N/A')} from {phone_item.get('source', 'N/A')}")

        return all_contact_info


def enhance_contact_extraction(base_url, soup):
    """
    Drop-in replacement for your existing email/phone extraction
    """
    scraper = ContactInfoScraper()
    return scraper.scrape_all_contact_info(base_url, soup)









    