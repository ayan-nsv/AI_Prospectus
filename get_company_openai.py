import openai
import json
import logging
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def get_openai_client():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
    return openai.OpenAI(api_key=api_key)

def generate_company_summary(company_name, website_content="", company_info=None):
    print(f"         Generating company summary...")
    
    context_parts = []
    
    if company_info:
        context_parts.append(f"Company Registration Data:")
        if company_info.get('name'):
            context_parts.append(f"- Official name: {company_info['name']}")
        if company_info.get('industry'):
            context_parts.append(f"- Industry: {company_info['industry']}")
        if company_info.get('value_proposition'):
            context_parts.append(f"- Business purpose: {company_info['value_proposition']}")
        if company_info.get('location'):
            location = company_info['location']
            context_parts.append(f"- Location: {location.get('municipality', '')}, {location.get('county', '')}")
    
    if website_content:
        context_parts.append(f"\nWebsite Content:")
        context_parts.append(website_content[:1000])  # Limit to first 1000 characters
    
    context = "\n".join(context_parts)
    
    prompt = f"""
You are a business analyst. Create a concise, professional summary (4-5 sentences) about {company_name} based on the available information.

The summary should be:
- Professional and factual
- 4-5 sentences maximum
- Focus on what the company does and who they serve
- Avoid marketing language or superlatives
- Avoid including any information about employees, revenue, or financials
- Also avoid mentioning the price of products or services

Available Information:
{context}

Generate a brief company summary:
"""
    
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip()
        print(f"         Company summary generated successfully")
        logger.info(f"Company summary generated for: {company_name}")
        return result
        
    except Exception as e:
        error_msg = f"Error generating company summary: {e}"
        print(f"         {error_msg}")
        logger.error(f"Error generating company summary for {company_name}: {str(e)}")
        return f"Error: {error_msg}"

def determine_business_type(company_name, website_content="", company_info=None):
    """
    Determine if the company is B2B or B2C using AI analysis
    
    Args:
        company_name (str): The company name
        website_content (str): Content scraped from website paragraphs
        company_info (dict): Company information from allabolag
        
    Returns:
        str: "B2B" or "B2C"
    """
    print(f"         Analyzing business type...")
    
    # Build context for the AI
    context_parts = []
    
    if company_info:
        context_parts.append(f"Company Registration Data:")
        if company_info.get('industry'):
            context_parts.append(f"- Industry: {company_info['industry']}")
        if company_info.get('industries'):
            context_parts.append(f"- Industries: {', '.join(company_info['industries'])}")
        if company_info.get('value_proposition'):
            context_parts.append(f"- Business purpose: {company_info['value_proposition']}")
    
    if website_content:
        context_parts.append(f"\nWebsite Content:")
        context_parts.append(website_content[:800])  # Limit to first 800 characters
    
    context = "\n".join(context_parts)
    
    prompt = f"""
Analyze {company_name} and determine if it's primarily a B2B (business-to-business) or B2C (business-to-consumer) company.

B2B indicators:
- Sells to other businesses, organizations, or professionals
- Provides business services, consulting, or enterprise solutions
- Language focused on "clients", "partners", "enterprise"
- Services like consulting, software for businesses, B2B marketing, etc.

B2C indicators:
- Sells directly to individual consumers
- Provides consumer products or services
- Language focused on "customers", personal benefits
- Services like retail, consumer apps, personal services, etc.

Available Information:
{context}

Based on this information, respond with ONLY one word: "B2B" or "B2C"
"""
    
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip().upper()
        
        # Validate response
        if result in ["B2B", "B2C"]:
            print(f"         Business type determined: {result}")
            logger.info(f"Business type determined for {company_name}: {result}")
            return result
        else:
            # Fallback to B2B if unclear
            print(f"         Unclear response, defaulting to B2B")
            return "B2B"
        
    except Exception as e:
        error_msg = f"Error determining business type: {e}"
        print(f"         {error_msg}")
        logger.error(f"Error determining business type for {company_name}: {str(e)}")
        return "B2B"  # Default fallback

def build_prompt(company_name, extra_info=None):
    """
    Build prompt for OpenAI to generate company profile (legacy function - kept for compatibility)
    """
    base_intro = f"""
You are a professional business writer helping a marketing manager quickly understand companies.

Your task is to create a clear, engaging Company Profile Summary for "{company_name}".

Output Structure:
Company Overview:
Start with a concise paragraph summarizing what the company does, its target customers, and its value proposition. Make it informative but easy to skim for a busy executive.

Key Facts:
Present critical company details in a structured list:
- Headquarters location
- Main offices / regions of operation
- Founding year
- CEO / Leadership
- Number of employees
- Latest reported revenue / turnover
- Industry sector
- Main products & services
- Key customers or target audience
- Business industry

Recent Highlights & Updates:
Share any notable news, updates, or strategic moves (e.g., expansions, partnerships, innovations).

Answer These Specific Questions:
- Where is {company_name} headquartered?
- What are the main locations/offices of {company_name}?
- When was {company_name} founded?
- Who is the CEO of {company_name}?
- What is the latest reported turnover/revenue of {company_name}?
- What does {company_name} do?
- What products/services does {company_name} offer?
- Who are the main customers of {company_name}?
- What industry does {company_name} operate in?
- What are some recent news or updates about {company_name}?
- What is the revenue or turnover of {company_name}?
- What is the business industry of {company_name}?

Industry Analysis:
Provide a clear, specific industry name and location.
Format: "Industry: [specific industry name] in [location]"
Example: "Industry: Telecommunications equipment manufacturing in Stockholm, Sweden"
"""

    if extra_info:
        extra_info_block = f"\n---\nExtra Context (if available):\nUse the following additional raw data to enrich your summary if relevant:\n{extra_info.strip()}"
        prompt = base_intro + extra_info_block
    else:
        prompt = base_intro

    return prompt.strip()

def get_company_info(company_name, extra_info=None):
   
    print(f"       Generating company profile for: {company_name}")
    
    prompt = build_prompt(company_name, extra_info)

    try:
        print(f"         Calling OpenAI API...")
        
        client = get_openai_client()
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        
        result = response.choices[0].message.content
        print(f"        Company profile generated successfully")
        logger.info(f"Company profile generated successfully for: {company_name}")
        return result
        
    except Exception as e:
        error_msg = f"Error while generating company info: {e}"
        print(f"        {error_msg}")
        logger.error(f"Error generating company profile for {company_name}: {str(e)}")
        return f"Error: {error_msg}"
     


def clean_phone_numbers(numbers: List[Dict[str, str]]) -> Dict:
    """
    Clean and validate a list of phone numbers with their source URLs.

    Args:
        numbers (List[Dict[str, str]]): List of dicts with 'phone' and 'source'.

    Returns:
        Dict: {"cleaned_phones": [{"phone": ..., "source": ...}, ...]}
    """
    system_message = """
    You are an expert in validating phone numbers.

    Task:
    - Take a list of dictionaries of phone numbers along with their source URLs. 
      Example input:
      [
        {"phone": "phone1", "source": "source url1"},
        {"phone": "phone2", "source": "source url2"}
      ]

    - Keep all numbers that look like real phone numbers (digits with optional spaces, dashes, brackets, or leading zeros).
    - Do NOT reformat, normalize, or change them in any way.
    - Only discard if the number is clearly invalid (e.g., letters, symbols, or unrealistically short).

    Priority: 
    - Include numbers from US, Europe, India, and Sweden.
    - If uncertain, keep the number instead of discarding.

    Output:
    - Return JSON strictly in this format:
      {"cleaned_phones": [
        {"phone": "original_number1", "source": "source url1"},
        {"phone": "original_number2", "source": "source url2"}
      ]}
    - Do not include explanations or extra text.
    """

    prompt = f"Clean these phone numbers: {numbers}"

    try:
        print(f"  Calling OpenAI for cleaning phone numbers: {numbers}")
        client = get_openai_client()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
            response_format={"type": "json_object"}  
        )

        # The response content is a JSON string
        result_str = response.choices[0].message.content

        # Convert it to a Python dict
        try:
            result = json.loads(result_str)
        except json.JSONDecodeError:
            print(f"  Warning: failed to parse JSON, returning empty list")
            result = {"cleaned_phones": []}

        print("        Phone numbers cleaned successfully")
        logger.info(f"Phone numbers cleaned successfully: {numbers}")
        print(result)  # Prints the cleaned JSON dict
        return result

    except Exception as e:
        error_msg = f"Error while cleaning phone numbers: {e}"
        print(f"  {error_msg}")
        logger.error(error_msg)
        return {"cleaned_phones": []}


import re
def get_correct_url(allabolag_name: str, scraped_url):
    logger.info(f"Using OpenAI to validate company website for '{allabolag_name}' with scraped URL: {scraped_url}")
    print(f"Using OpenAI to validate company website for '{allabolag_name}' with scraped URL: {scraped_url}")

    system_message = f"""
    You are a web analyst. Your task is to verify if the following URL is the official website for the company {allabolag_name}: {scraped_url}.
    If it is correct, confirm it. 
    If it is not correct, find the official website URL. 
    Use the following criteria to validate:
    1. Look at the domain registration (WHOIS) if available.
    2. Prefer the domain that matches the official company name or common patterns (.com, .se, etc.).
    3. Return only the final confirmed official URL strictly in JSON format like this: {{ "url": "web_url" }}.
    4. The official URL strictly should be of the format : " https://www.example(.com, .se, etc.)"
    """

    prompt = f"Analyze the URL and confirm if it is official. If not, provide the correct official website URL for {allabolag_name}."

    client = get_openai_client()  # assumes this function is defined elsewhere

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        logger.info(f"OpenAI response: {content}")

        try:
            result = json.loads(content)
            logger.info(f"Validated URL: {result.get('url')}")
            return result
        except json.JSONDecodeError:
            # fallback: try extracting JSON from text
            match = re.search(r"\{.*\}", content)
            if match:
                try:
                    result = json.loads(match.group())
                    logger.info(f"Fallback parsed URL: {result.get('url')}")
                    return result
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON in fallback for {allabolag_name}")
            # final fallback: return raw content
            logger.warning(f"Returning raw content as URL for {allabolag_name}")
            return {"url": content}

    except Exception as e:
        logger.error(f"Error validating URL for {allabolag_name}: {e}")
        return {"url": scraped_url}

