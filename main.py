from organnew import get_org_number

from clean_allabolag import get_clean_company_info
from final6thscrpe import scrape_company_by_name, scrape_company_by_domain
from get_company_openai import generate_company_summary, determine_business_type
from findcompy import search_company_google, search_company_with_fallbacks, search_company_duckduckgo
import re
import json
import time
import logging
from datetime import datetime
from difflib import SequenceMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def format_date(date_str):
    """Convert YYYY-MM-DD to DD.MM.YYYY format"""
    if not date_str:
        return None
    try:
        if isinstance(date_str, str) and '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except:
        pass
    return date_str

def get_empty_response():
    
    return {
        "about": "",
        "scraped_data": {
            "Emails": [],
            "Phones": [],
            "SocialMedia": {}
        },
        "Websites": [],
        "CompanyName": "",
        "OrgNumber": "",
        "currentIndustry": "",
        "industries": [],
        "naceIndustries": [],
        "Location": {
            "countryPart": "",
            "county": "",
            "municipality": ""
        },
        "Revenue": "",
        "estimatedTurnover": "",
        "foundationyear": "",
        "registrationDate": "",
        "foundationDate": "",
        "turnoverYear": "",
        "Employees": "",
        "valueProposition": "",
        "business_type_guess": ""
    }

def structure_response_data( allabolag_data, website_data):
    """
    Structure the response data with enhanced contact info including exact source URLs
    """
    # Initialize response structure
    response = {
        "about": "",
        "scraped_data": {
            "Emails": [],
            "Phones": [],
            "SocialMedia": {}
        },
        "Websites": [],
        "CompanyName": "",
        "OrgNumber": "",
        "currentIndustry": "",
        "industries": [],
        "naceIndustries": [],
        "Location": {
            "countryPart": "",
            "county": "",
            "municipality": ""
        },
        "Revenue": "",
        "estimatedTurnover": "",
        "foundationyear": "",
        "registrationDate": "",
        "foundationDate": "",
        "turnoverYear": "",
        "Employees": "",
        "valueProposition": "",
        "business_type_guess": ""
    }
    
    # Fill allabolag data
    if allabolag_data:
        response["CompanyName"] = allabolag_data.get("name", "")
        response["OrgNumber"] = allabolag_data.get("org_number", "")
        response["currentIndustry"] = allabolag_data.get("industry", "")
        response["industries"] = allabolag_data.get("industries", [])
        response["naceIndustries"] = allabolag_data.get("nace_industries", [])
        response["Revenue"] = str(allabolag_data.get("turnover", "")) if allabolag_data.get("turnover") else ""
        response["estimatedTurnover"] = allabolag_data.get("turnover_range", "")
        response["foundationyear"] = str(allabolag_data.get("foundation_year", "")) if allabolag_data.get("foundation_year") else ""
        response["registrationDate"] = allabolag_data.get("registration_date", "")
        response["turnoverYear"] = allabolag_data.get("turnoverYear", "")
        response["foundationDate"] = format_date(allabolag_data.get("registration_date", ""))
        response["Employees"] = str(allabolag_data.get("employees", "")) if allabolag_data.get("employees") else ""
        response["valueProposition"] = allabolag_data.get("value_proposition", "")
        
        # Location data
        location = allabolag_data.get("location", {})
        if location:
            response["Location"]["countryPart"] = location.get("region", "")
            response["Location"]["county"] = location.get("county", "")
            response["Location"]["municipality"] = location.get("municipality", "")
        
        # Website from allabolag
        if allabolag_data.get("website"):
            response["Websites"].append(allabolag_data["website"])
    
    # Fill website scraping data with enhanced contact information (no addresses)
    if website_data:
        # Add website URL
        if website_data.get("website_url") and website_data["website_url"] not in response["Websites"]:
            response["Websites"].append(website_data["website_url"])
        
        # Enhanced contact information handling with exact source URLs
        if website_data.get("detailed_contact_info"):
            detailed_contact = website_data["detailed_contact_info"]
            
           # Add emails with exact source URLs and name fields
            for email_item in detailed_contact.get("emails", []):
                response["scraped_data"]["Emails"].append({
                    "email": email_item["email"],
                    "source": email_item["source"],  # Exact page URL where email was found
                    "firstname": email_item.get("firstname"),
                    "lastname": email_item.get("lastname")
                })
            
            # Add phones with exact source URLs
            for phone_item in detailed_contact.get("phones", []):
                response["scraped_data"]["Phones"].append({
                    "phone": phone_item["phone"],
                    "source": phone_item["source"]  # Exact page URL where phone was found
                })
        
        else:
            # Fallback to simple format if detailed contact info is not available
            emails = website_data.get("emails", [])
            for email in emails:
                response["scraped_data"]["Emails"].append({
                    "email": email,
                    "source": website_data.get("website_url", "")
                })
            
            phones = website_data.get("phones", [])
            for phone in phones:
                response["scraped_data"]["Phones"].append({
                    "phone": phone,
                    "source": website_data.get("website_url", "")
                })
        
        # Add social media data
        if website_data.get("social_media"):
            response["scraped_data"]["SocialMedia"] = website_data["social_media"]
        
    return response

async def get_company_data(org_number: str):
   
    start_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"Processing: {org_number}")
    print(f"{'='*60}")
    
    logger.info(f"Starting company data retrieval for: {org_number}")
    
    # Track completed steps
    steps_completed = []
    
    # Step 1: Get and clean company data using clean_allabolag module
    company_info = None
    if org_number != "Not found":
        print(f"Getting company data from allabolag...")
        company_info = get_clean_company_info(org_number)
        
        if company_info:
            print(f"Retrieved company data successfully")
        else:
            print(f"Failed to get company data")
            # If failed to get company data, return empty response
            return get_empty_response()
        logger.info(f"Retrieved company data: {'Success' if company_info else 'Failed'}")
    if company_info:
        steps_completed.append("allabolag_data")
    
    
    # Step 2: Scrape website data using final6thscrpe module
    scraped_data = None
    if company_info and company_info.get('name'):
        try:
            print(f"Scraping website data...")
            scraped_data = scrape_company_by_name(company_info['name'])
            
            #fix
            if not scraped_data:
                print(f"❌ TERMINATING: Website scraping returned empty data for {company_info['name']}")
                return get_empty_response()
            
            
            if scraped_data:
                print(f"Website scraping completed successfully")
            else:
                print(f"Website scraping failed")
            logger.info("Website scraping completed successfully")
        except Exception as e:
            print(f"Error scraping website: {str(e)}")
            logger.error(f"Error scraping website: {str(e)}")
    if scraped_data:
        steps_completed.append("website_scraping")

    # Step 3:  
    
    # Calculate processing time
    end_time = datetime.now()
    processing_time = str(end_time - start_time)
    
    processing_status = {
        "overall": "success" if len(steps_completed) > 2 else "partial",
        "steps_completed": steps_completed,
        "processing_time": processing_time
    }
    
    # Step 5: Structure the response data
    print(f"Structuring response data...")
    structured_data = structure_response_data(
       company_info, scraped_data
    )
    
    # Step 6: Generate AI-powered "about" summary and business type
    website_content = ""
    if scraped_data and scraped_data.get('content', {}).get('paragraphs'):
        website_content = " ".join(scraped_data['content']['paragraphs'][:10])  # Use first 10 paragraphs
    
    # Generate company summary for "about" field
    if website_content or company_info:
        print(f"Generating AI summary...")
        try:
            company_name_for_ai = structured_data["CompanyName"] 
            about_summary = generate_company_summary(company_name_for_ai, website_content, company_info)
            if about_summary and not about_summary.startswith("Error"):
                structured_data["about"] = about_summary
                print(f"AI summary generated successfully")
        except Exception as e:
            print(f"Error generating AI summary: {str(e)}")
            logger.error(f"Error generating AI summary: {str(e)}")
    
    # Determine business type using AI
    if website_content or company_info:
        print(f"Determining business type...")
        try:
            company_name_for_ai = structured_data["CompanyName"]
            business_type = determine_business_type(company_name_for_ai, website_content, company_info)
            if business_type and not business_type.startswith("Error"):
                structured_data["business_type_guess"] = business_type
                print(f"Business type determined: {business_type}")
        except Exception as e:
            print(f"Error determining business type: {str(e)}")
            logger.error(f"Error determining business type: {str(e)}")
            # Fallback to existing logic if available
            if company_info and company_info.get("business_type_guess"):
                structured_data["business_type_guess"] = company_info["business_type_guess"]
                
            
        except Exception as e:
            print(f"Error determining SEO tags: {str(e)}")
            logger.error(f"Error determining SEO tags: {str(e)}")


    
    print(f"Processing completed for: structured_data['CompanyName']")
    print(f"{'='*60}\n")
    
    return structured_data




def valid_domain(domain: str):
    rejected_domains = [
        # Email providers
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", 
        "icloud.com", "protonmail.com", "zoho.com", "yandex.com", "mail.com",
        "gmx.com", "hubspot.com",
        
        # Swedish personal/identity services
        "allabolag.se", "hitta.se", "eniro.se", "merinfo.se", "ratsit.se",
        "birthday.se", "solidtango.com",
        
        # Search engines & tech giants
        "google.com", "bing.com", "duckduckgo.com", "facebook.com", "linkedin.com",
        "twitter.com", "instagram.com", "microsoft.com", "apple.com",
        
        # Generic/TLD domains
        "example.com", "test.com", "domain.com", "localhost", 
        
        # Swedish university/education
        "student.lnu.se", "edu.se", "skola.se",
        
        # Government/public services
        "gov.se", "kommun.se", "region.se",
        
        # Temporary/throwaway email services
        "tempmail.com", "10minutemail.com", "guerrillamail.com", "mailinator.com",
        "throwawaymail.com", "fakeinbox.com", "temp-mail.org",
        
        # Common free hosting
        "wordpress.com", "blogspot.com", "weebly.com", "wixsite.com"
    ]
    
    for rejected in rejected_domains:
        if rejected in domain:
            return False
    return True

