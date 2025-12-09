from allabolag import Company
import logging
from typing import Dict, Any


logger = logging.getLogger(__name__)


#get company data from allabolag
def get_company_data(org_number):
    """
    Get company data using the organization number from allabolag.se
    
    Args:
        org_number (str): The organization number to look up
        
    Returns:
        dict: Company data from allabolag or None if not found
    """
    if org_number != "Not found":
        try:
            print(f"         Fetching data from allabolag.se for org number: {org_number}")
            company = Company(org_number)
            data = company.data
            print(f"        ✅ Successfully retrieved data from allabolag.se")
            return data
        except Exception as e:
            print(f"        ❌ Error getting company data: {str(e)}")
            logger.error(f"Error getting company data for {org_number}: {str(e)}")
            
            # Check if it's a specific error type
            if "not found" in str(e).lower() or "404" in str(e):
                print(f"        ℹ️  Company {org_number} not found on allabolag.se")
            elif "connection" in str(e).lower() or "timeout" in str(e).lower():
                print(f"         Network error when accessing allabolag.se")
            else:
                print(f"        🔍 Unknown error accessing allabolag.se")
            
            return None
    return None


#### parse company data
def safe_get(obj, path, default=None):
    """Safely navigate nested dict using dot notation."""
    for p in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return default
    return obj if obj is not None else default


def normalize_roles(roles_block):
    """Flatten board/roles structure robustly."""
    members = []
    if not roles_block:
        return members

    for group in roles_block.get("roleGroups", []):
        for r in group.get("roles", []):
            members.append({
                "name": r.get("name"),
                "role": r.get("role"),
                "fromDate": r.get("fromDate"),
                "birthYear": r.get("birthYear"),
                "city": r.get("city"),
                "country": r.get("country")
            })
    return members


def normalize_accounts(company):
    """Extract full accounting history with every detail preserved."""
    history = []
    accounts = company.get("companyAccounts", [])
    for yr in accounts:
        history.append({
            "year": yr.get("year"),
            "period": yr.get("period"),
            "lengthMonths": yr.get("lengthMonths"),
            "currency": yr.get("currency"),
            "consolidated": yr.get("isConsolidated"),
            "submittedDate": yr.get("submittedDate"),
            "accounts": yr.get("accounts", [])  # KEEP ALL detailed rows
        })
    return history


def normalize_registration(company):
    """Extract all legal registrations, flags & authority registrations."""
    return {
        "legalForm": safe_get(company, "legalForm.name"),
        "companyTypeCode": safe_get(company, "legalForm.code"),

        "foundedDate": company.get("foundedDate"),
        "shareCapital_SEK": company.get("shareCapital"),
        "status": safe_get(company, "status.status"),
        "statusDate": safe_get(company, "status.statusDate"),

        "orgnr": company.get("orgnr"),
        "vatNumber": company.get("vatNumber"),

        "registeredForVAT": company.get("registeredForVat"),
        "registeredForPrepaymentTax": company.get("registeredForPrepayment"),
        "registeredForPayrollTax": company.get("registeredForPayrollTax"),
        "registeredForFskatt": company.get("fSkatt"),

        "registeredAuthorities": company.get("registeredAuthorities"),
    }


def normalize_location(company):
    return {
        "visitorAddress": company.get("visitorAddress"),
        "postalAddress": company.get("postalAddress"),
        "municipality": safe_get(company, "location.municipality"),
        "county": safe_get(company, "location.county"),
        "region": safe_get(company, "location.countryPart"),
        "coordinates": safe_get(company, "location.coordinates"),
    }


def normalize_industry(company):
    return {
        "mainSni": safe_get(company, "currentIndustry.code"),
        "mainSniName": safe_get(company, "currentIndustry.name"),
        "naceCodes": company.get("naceIndustries"),
        "industryHierarchy": company.get("industryHierarchy"),
    }


def normalize_contact(company):
    return {
        "phone": company.get("phone") or company.get("legalPhone"),
        "email": company.get("email"),
        "website": company.get("homePage"),
        "contactPersons": company.get("contactPersons"),
    }


def normalize_financial_summary(company):
    return {
        "turnoverRange_SEK": company.get("estimatedTurnover"),
        "employees": company.get("numberOfEmployees"),
        "revenue_SEK": company.get("revenue"),
        "profit_SEK": company.get("profit"),
        "equity_SEK": company.get("equity"),
        "assets_SEK": company.get("totalAssets"),
        "liabilities_SEK": company.get("totalLiabilities"),
        "profitMargin": company.get("profitMargin"),
        "liquidity": company.get("liquidity"),
        "solvency": company.get("solvency"),
        "cashFlow_SEK": company.get("cashFlow"),
        "taxDebt_SEK": company.get("taxDebt")
    }


def normalize_risks(company):
    return {
        "paymentRemarks": company.get("paymentRemarks"),
        "collectionCases": company.get("collectionCases"),
        "bankruptcies": company.get("bankruptcies"),
        "mortgages": company.get("mortgages"),
        "encumbrances": company.get("encumbrances"),
        "creditRating": company.get("creditRating"),
        "riskClass": company.get("riskClass"),
    }


def parse_company(raw: Dict[str, Any]) -> Dict[str, Any]:
    company = raw.get("company", {})

    return {
        "name": company.get("name"),
        "orgnr": company.get("orgnr"),

        "purpose": company.get("purpose"),
        "companyType": safe_get(company, "legalForm.name"),

        "contact": normalize_contact(company),
        "location": normalize_location(company),
        "industry": normalize_industry(company),
        "registration": normalize_registration(company),
        "governance": {
            "boardMembers": normalize_roles(company.get("roles")),
            "signatories": company.get("signatoryGroups"),
            "owners": company.get("owners")
        },

        "financialSummary": normalize_financial_summary(company),
        "accountingHistory": normalize_accounts(company),

        "risks": normalize_risks(company),

        # Metadata that may be useful
        "meta": {
            "lastUpdated": company.get("lastUpdated"),
            "sourceSystem": company.get("system"),
            "reportCount": company.get("numberOfAnnualReports"),
        }
    }


def analyze_company(company_data):
    """
    Clean and analyze company data from allabolag
    
    Args:
        company_data (dict): Raw company data from allabolag
        
    Returns:
        dict: Cleaned and analyzed company information
    """
    print(f"        🧹 Cleaning and analyzing company data...")
    
    # Check if company_data is None or empty
    if not company_data:
        print(f"        ❌ No company data provided for analysis")
        return None
    
    # The data is nested under 'company' key
    company = company_data.get('company', {})
    print("        🔍 Available keys in company data:")
    print("        ", list(company.keys()))
    print("        🌐 Website fields check:")
    print("          homePage:", company.get("homePage"))
    print("          webshopUrl:", company.get("webshopUrl"))
    print("          contactFormUrl:", company.get("contactFormUrl"))
    print("          externalLinks:", company.get("externalLinks"))
    print("          socialMediaLinks:", company.get("socialMediaLinks"))

    print(company)
    result = {
        "name": company.get("name"),
        "org_number": company.get("orgnr"),
        "website": company.get("homePage"),
        "turnover": company.get("revenue"),
        "turnover_range": company.get("estimatedTurnover"),
        "turnoverYear": company.get("turnoverYear"),
        "registration_date": company.get("registrationDate"),
        "foundation_year": company.get("foundationYear"),
        "employees": company.get("numberOfEmployees"),
        "industry": company.get("currentIndustry", {}).get("name") if company.get("currentIndustry") else None,
        "industries": [i["name"] for i in company.get("industries", []) if isinstance(i, dict) and "name" in i],
        "nace_industries": company.get("naceIndustries", []),
        "location": {
            "region": company.get("location", {}).get("countryPart") if company.get("location") else None,
            "county": company.get("location", {}).get("county") if company.get("location") else None,
            "municipality": company.get("location", {}).get("municipality") if company.get("location") else None,
        },
        "value_proposition": company.get("purpose"),
    }

    # Heuristic: guess B2B or B2C from industries
    b2b_keywords = ["företag", "business", "konsult", "utveckling", "organisation"]
    nace_industries = result.get("nace_industries", []) or []
    all_industries_text = " ".join(result.get("industries", []) + nace_industries)
    result["business_type_guess"] = "B2B" if any(k.lower() in all_industries_text.lower() for k in b2b_keywords) else "B2C"
    print(result)
    print(f"        ✅ Company data cleaned successfully")
    print(f"          - Name: {result.get('name', 'Unknown')}")
    print(f"          - Employees: {result.get('employees', 'Unknown')}")
    print(f"          - Industry: {result.get('industry', 'Unknown')}")
    print(f"          - Business Type: {result.get('business_type_guess', 'Unknown')}")

    return result


def get_clean_company_info(org_number):
    """
    Main function to get and clean company information from organization number
    
    Args:
        org_number (str): The organization number to look up
        
    Returns:
        dict: Cleaned company information or None if not found
    """
    print(f"      📊 Getting company data for org number: {org_number}")
    logger.info(f"Getting company data for org number: {org_number}")
    
    # Get raw company data
    company_data = get_company_data(org_number)
    
    if company_data:
        # Clean and analyze the data
        cleaned_data = analyze_company(company_data)
        if cleaned_data:
            print(f"      ✅ Successfully retrieved and cleaned company data")
            logger.info(f"Successfully retrieved and cleaned company data for: {cleaned_data.get('name', 'Unknown')}")
            return cleaned_data
        else:
            print(f"      ❌ Failed to clean company data")
            logger.warning(f"Failed to clean company data for org number: {org_number}")
            return None
    else:
        print(f"      ❌ No company data found for org number: {org_number}")
        logger.warning(f"No company data found for org number: {org_number}")
        return None

async def clean_company_info(org_number):
    """
    Main function to get and clean company information from organization number
    
    Args:
        org_number (str): The organization number to look up
        
    Returns:
        dict: Cleaned company information or None if not found
    """
    print(f"      📊 Getting company data for org number: {org_number}")
    logger.info(f"Getting company data for org number: {org_number}")
    
    # Get raw company data
    company_data = get_company_data(org_number)
    
    if company_data:
        # Clean and analyze the data
        cleaned_data = parse_company(company_data)
        if cleaned_data:
            print(f"      ✅ Successfully retrieved and cleaned company data")
            logger.info(f"Successfully retrieved and cleaned company data for: {cleaned_data.get('name', 'Unknown')}")
            return cleaned_data
        else:
            print(f"      ❌ Failed to clean company data")
            logger.warning(f"Failed to clean company data for org number: {org_number}")
            return None
    else:
        print(f"      ❌ No company data found for org number: {org_number}")
        logger.warning(f"No company data found for org number: {org_number}")
        return None
