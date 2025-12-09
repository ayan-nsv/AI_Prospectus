import re
from typing import Dict, Any

def validate_input(user_input: str) -> Dict[str, Any]:
    """
    Validate if input is an email or company name
    Returns dictionary with validation results
    """
    # Email validation pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    result = {
        'input': user_input,
        'is_valid': False,
        'type': 'unknown',
        'cleaned_input': user_input.strip()
    }
    
    if not user_input or not user_input.strip():
        return result
    
    # Check if it's an email
    if re.match(email_pattern, user_input.strip()):
        result['is_valid'] = True
        result['type'] = 'email'
        return result
    
    # Check if it's a company name (at least 2 characters, not just numbers)
    cleaned_name = user_input.strip()
    if len(cleaned_name) >= 2 and not cleaned_name.replace(' ', '').isdigit():
        result['is_valid'] = True
        result['type'] = 'company_name'
        return result
    
    return result


def check_email(user_input: str):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_pattern, user_input.strip()):
        return True
    return False
    

def extract_company_from_email(email: str) -> str:
    """Extract company name from email address"""
    if '@' in email:
        domain = email.split('@')[1]
        # Remove common domain parts and extract company name
        company = domain.split('.')[0]
        # Clean up common prefixes/suffixes
        company = re.sub(r'^(info|contact|support|hello)\.?', '', company)
        return company.title()
    return email