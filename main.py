from clean_allabolag import get_clean_company_info
from final6thscrpe import scrape_company_by_name
from get_company_openai import generate_company_summary, determine_business_type, check_if_category_contains_contact_details
import asyncio
import logging
from datetime import datetime
from typing import Optional

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

def structure_response_data( allabolag_data, website_data, criteria: Optional[str] = None):
    """
    Structure the response data with enhanced contact info including exact source URLs
    
    Args:
        allabolag_data: Company data from allabolag
        website_data: Scraped website data
        criteria: Optional criteria string for contact prioritization
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
                    "lastname": email_item.get("lastname"),
                    "role": email_item.get("role")  # Job title/role (CEO, CTO, etc.)
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
    
    # Apply contact prioritization if criteria is provided
    if criteria:
        print(f"Applying contact prioritization with criteria: {criteria}")
        print(f"  Emails before prioritization: {len(response.get('scraped_data', {}).get('Emails', []))}")
        from contact_prioritizer import prioritize_contacts_in_response
        response = prioritize_contacts_in_response(response, criteria)
        print(f"  Emails after prioritization: {len(response.get('scraped_data', {}).get('Emails', []))}")
    else:
        print(f"No criteria provided - skipping contact prioritization")
        
    return response

async def get_company_data(org_number: str, criteria: Optional[str] = None):
   
    start_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"Processing: {org_number}")
    print(f"{'='*60}")
    
    logger.info(f"Starting company data retrieval for: {org_number}")
    
    # Track completed steps
    steps_completed = []
    
    # Step 1: Get and clean company data using clean_allabolag module
    # Run blocking call in thread pool to avoid blocking event loop
    company_info = None
    if org_number != "Not found":
        print(f"Getting company data from allabolag...")
        try:
            # Run blocking call in thread pool to allow other tasks to run concurrently
            company_info = await asyncio.to_thread(get_clean_company_info, org_number)
        except Exception as e:
            logger.error(f"Error getting company data: {str(e)}")
            company_info = None
        
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
    # Run blocking call in thread pool with timeout to prevent long blocking
    scraped_data = None
    if company_info and company_info.get('name'):
   
        address = company_info.get('location')
        country = address.get('county')
        region = address.get('region')
  

        try:
            print(f"Scraping website data...")
            # Run blocking scraping in thread pool with timeout
            # This allows other companies to process while this one scrapes
            try:
                scraped_data = await asyncio.wait_for(
                    asyncio.to_thread(scrape_company_by_name, company_info['name'], region, country),
                    timeout=85.0  # 85 second timeout for scraping
                )
            except asyncio.TimeoutError:
                logger.warning(f"Website scraping timeout for {company_info['name']}")
                scraped_data = None
            
            # Don't terminate if scraping fails - continue with available data
            if not scraped_data:
                print(f"⚠️ Website scraping failed or timed out for {company_info['name']}, continuing without scraped data")
                logger.warning(f"Website scraping failed for {company_info['name']}, continuing without scraped data")
            else:
                print(f"Website scraping completed successfully")
                logger.info("Website scraping completed successfully")
        except Exception as e:
            print(f"Error scraping website: {str(e)}")
            logger.error(f"Error scraping website: {str(e)}")
            # Continue processing even if scraping fails
            scraped_data = None
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
       company_info, scraped_data, criteria
    )
    # step 6: check if category contains any details about the conatacts
    new_emails = check_if_category_contains_contact_details(criteria, structured_data["scraped_data"]["Emails"])
    if new_emails:
        structured_data["scraped_data"]["Emails"] = new_emails
        print(f"emails updated: {new_emails}")
    
    # Step 6: Generate AI-powered "about" summary and business type
    website_content = ""
    if scraped_data and scraped_data.get('content', {}).get('paragraphs'):
        website_content = " ".join(scraped_data['content']['paragraphs'][:10])  # Use first 10 paragraphs
    
    # Generate company summary for "about" field
    # Run AI calls in parallel if both are needed, and in thread pool to avoid blocking
    if website_content or company_info:
        print(f"Generating AI summary...")
        try:
            company_name_for_ai = structured_data["CompanyName"] 
            # Run blocking AI call in thread pool
            about_summary = await asyncio.to_thread(
                generate_company_summary, 
                company_name_for_ai, 
                website_content, 
                company_info
            )
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
            # Run blocking AI call in thread pool
            business_type = await asyncio.to_thread(
                determine_business_type,
                company_name_for_ai,
                website_content,
                company_info
            )
            if business_type and not business_type.startswith("Error"):
                structured_data["business_type_guess"] = business_type
                print(f"Business type determined: {business_type}")
        except Exception as e:
            print(f"Error determining business type: {str(e)}")
            logger.error(f"Error determining business type: {str(e)}")
            # Fallback to existing logic if available
            if company_info and company_info.get("business_type_guess"):
                structured_data["business_type_guess"] = company_info["business_type_guess"]


    
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

