import requests, re, time, json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from io import BytesIO
from PIL import Image
from colorthief import ColorThief

USER_AGENT = "Mozilla/5.0"

def screenshot_colors(url, num_colors=5):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(3)
    png = driver.get_screenshot_as_png()
    driver.quit()
    with BytesIO(png) as f:
        ct = ColorThief(f)
        palette = ct.get_palette(color_count=num_colors)
    return ['#%02x%02x%02x' % c for c in palette]

def fetch_css_and_inline(soup, base_url):
    texts = []
    for tag in soup.find_all("style"):
        texts.append(tag.text or "")
    for tag in soup.find_all(style=True):
        texts.append(tag["style"])
    for link in soup.find_all("link", rel="stylesheet", href=True):
        href = urljoin(base_url, link["href"])
        try:
            r = requests.get(href, headers={"User-Agent":USER_AGENT}, timeout=5)
            if r.status_code == 200:
                texts.append(r.text)
        except:
            continue
    return texts

def extract_colors_from_css(texts):
    combined = "\n".join(texts)
    colors = re.findall(r'#[0-9a-fA-F]{3,6}', combined)
    colors += re.findall(r'rgba?\([^)]+\)', combined)
    colors += re.findall(r'--[\w-]+\s*:\s*(#[0-9a-fA-F]{3,6})', combined)
    return [c for c in colors]

def extract_fonts_from_css(texts):
    combined = "\n".join(texts)
    fonts = re.findall(r'font-family\s*:\s*([^;]+);', combined)
    gf = re.findall(r'https?://fonts\.googleapis\.com[^"\')]+', combined)
    fonts = [f.strip().strip('"\'') for f in fonts]
    for link in gf:
        fam = link.split("family=")[-1].split("&")[0].replace("+"," ")
        fonts.append("Google:"+fam)
    return fonts

def detect_logo(soup, base_url):
    icon = soup.find("link", rel=lambda x: x and "icon" in x.lower())
    if icon and icon.has_attr("href"):
        return urljoin(base_url, icon["href"])
    for img in soup.find_all("img", src=True):
        alt = img.get("alt","")
        src = img["src"]
        if "logo" in src.lower() or "logo" in alt.lower():
            return urljoin(base_url, src)
    return None

def rank_by_frequency(items):
    cnt = Counter(items)
    ranked = [c for c,_ in cnt.most_common(5)]
    return ranked

def scrape_theme(url):
    # fetch page
    r = requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    base = "{uri.scheme}://{uri.netloc}".format(uri=urlparse(url))
    # logo
    logo = detect_logo(soup, base)
    # css & inline
    css_texts = fetch_css_and_inline(soup, base)
    colors = extract_colors_from_css(css_texts)
    fonts = extract_fonts_from_css(css_texts)
    top_css_colors = rank_by_frequency([c.lower() for c in colors])
    top_fonts = rank_by_frequency(fonts)
    # screenshot
    vis_colors = screenshot_colors(url)
    merged = []
    for c in vis_colors + top_css_colors:
        lc = c.lower()
        if lc not in merged:
            merged.append(lc)
    theme_colors = merged[:5]
    return {
        "url": url,
        "logo_url": logo,
        "fonts": top_fonts[:5],
        "theme_colors": theme_colors
    }

