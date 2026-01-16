"""
Contact Prioritization Module

This module filters and prioritizes contacts based on criteria such as:
- Location preferences (e.g., Stockholm)
- Role preferences (e.g., CEO, CTO)
"""

import re
from typing import List, Dict, Optional, Set


class ContactPrioritizer:
    """Prioritizes contacts based on location and role criteria"""
    
    def __init__(self, criteria: Optional[str] = None):
        """
        Initialize with optional criteria string
        
        Args:
            criteria: Criteria string that may contain location and role preferences
                     Example: "companies based in stockholm along with contacts of CEO/CTO"
        """
        self.criteria = criteria or ""
        self.preferred_locations = self._extract_locations(criteria)
        self.preferred_roles = self._extract_roles(criteria)
    
    def _extract_locations(self, criteria: str) -> Set[str]:
        """Extract location preferences from criteria"""
        if not criteria:
            return set()
        
        criteria_lower = criteria.lower()
        locations = set()
        
        # Check for country-level locations first (they match all cities)
        country_keywords = {
            'sweden': ['sweden', 'sverige', 'swedish'],
            'norway': ['norway', 'norge', 'norwegian'],
            'denmark': ['denmark', 'danmark', 'danish'],
            'finland': ['finland', 'suomi', 'finnish']
        }
        
        is_country_match = False
        for country, keywords in country_keywords.items():
            if any(keyword in criteria_lower for keyword in keywords):
                locations.add(country)
                is_country_match = True
                break
        
        # If no country match, extract city-level locations
        if not is_country_match:
            # Common Swedish locations
            swedish_locations = [
                'stockholm', 'göteborg', 'gothenburg', 'malmö', 'malmo',
                'uppsala', 'västerås', 'vasteras', 'örebro', 'orebro',
                'linköping', 'linkoping', 'helsingborg', 'jönköping', 'jonkoping',
                'norrköping', 'norrkoping', 'lund', 'umeå', 'umea'
            ]
            
            for location in swedish_locations:
                if location in criteria_lower:
                    locations.add(location)
            
            # Also check for patterns like "based in X", "located in X", "from X"
            patterns = [
                r'\bbased\s+in\s+([a-zäöå\s]+)',
                r'\blocated\s+in\s+([a-zäöå\s]+)',
                r'\bfrom\s+([a-zäöå\s]+)',
                r'\bin\s+([a-zäöå\s]+)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, criteria_lower)
                for match in matches:
                    # Clean up the match (remove extra whitespace)
                    match_clean = match.strip()
                    if match_clean:
                        locations.add(match_clean)
        
        return locations
    
    def _extract_roles(self, criteria: str) -> Set[str]:
        """Extract role preferences from criteria"""
        if not criteria:
            return set()
        
        criteria_lower = criteria.lower()
        roles = set()
        
        # Map of role keywords to normalized role names
        role_keywords = {
            'ceo': ['ceo', 'chief executive officer', 'vd', 'verkställande direktör'],
            'cto': ['cto', 'chief technology officer', 'tekniskt ansvarig', 'teknisk chef'],
            'cfo': ['cfo', 'chief financial officer', 'ekonomidirektör', 'finansiell chef'],
            'coo': ['coo', 'chief operating officer', 'operativ chef'],
            'cmo': ['cmo', 'chief marketing officer', 'marknadschef'],
            'founder': ['founder', 'grundare', 'co-founder', 'medgrundare'],
            'director': ['director', 'direktör', 'managing director'],
            'manager': ['manager', 'chef', 'ledare'],
            'head': ['head of', 'chef för', 'ansvarig för'],
        }
        
        # Check for role mentions in criteria
        for normalized_role, keywords in role_keywords.items():
            for keyword in keywords:
                if keyword in criteria_lower:
                    roles.add(normalized_role.upper())
                    break
        
        return roles
    
    def prioritize_contacts(
        self, 
        company_data: Dict,
        contacts: List[Dict]
    ) -> List[Dict]:
        """
        Prioritize contacts based on role criteria (does NOT filter by location)
        
        Note: Location filtering should be done at the company level, not contact level.
        This function only prioritizes contacts by role.
        
        Args:
            company_data: Company data including location information (not used for filtering here)
            contacts: List of contact dictionaries with email, role, etc.
        
        Returns:
            Prioritized list of contacts (all contacts returned, just reordered)
        """
        if not contacts:
            return []
        
        # Prioritize contacts by role (do NOT filter by location here)
        prioritized = []
        other_contacts = []
        
        for contact in contacts:
            contact_role = contact.get('role')
            if contact_role:
                # Normalize role to uppercase
                contact_role = contact_role.upper()
            
            # Check if contact matches preferred roles
            if self.preferred_roles:
                if contact_role and any(pref_role in contact_role for pref_role in self.preferred_roles):
                    prioritized.append(contact)
                else:
                    other_contacts.append(contact)
            else:
                # No role preference, prioritize contacts with roles over generic ones
                if contact_role:
                    prioritized.append(contact)
                else:
                    other_contacts.append(contact)
        
        # Return prioritized contacts first, then others (all contacts are returned)
        return prioritized + other_contacts
    
    def _matches_location(self, company_data: Dict) -> bool:
        """Check if company matches location criteria"""
        if not self.preferred_locations:
            return True  # No location preference means match
        
        # Check various location fields
        location_fields = [
            company_data.get('Location', {}).get('municipality', '').lower(),
            company_data.get('Location', {}).get('county', '').lower(),
            company_data.get('Location', {}).get('countryPart', '').lower(),
        ]
        
        # Also check address fields in scraped data
        location_text = ' '.join(location_fields)
        
        # Normalize location names (handle Swedish characters)
        location_normalizations = {
            'gothenburg': 'göteborg',
            'malmo': 'malmö',
            'vasteras': 'västerås',
            'orebro': 'örebro',
            'linkoping': 'linköping',
            'jonkoping': 'jönköping',
            'norrkoping': 'norrköping',
            'umea': 'umeå'
        }
        
        # Country-level matching
        country_matches = {
            'sweden': ['sweden', 'sverige', 'swedish', 'göteborg', 'stockholm', 'malmö', 'uppsala', 
                      'västra götaland', 'västerås', 'örebro', 'linköping', 'helsingborg', 
                      'jönköping', 'norrköping', 'lund', 'umeå', 'hela sverige'],
            'norway': ['norway', 'norge', 'norwegian', 'oslo', 'bergen'],
            'denmark': ['denmark', 'danmark', 'danish', 'copenhagen', 'köpenhamn'],
            'finland': ['finland', 'suomi', 'finnish', 'helsinki', 'helsingfors']
        }
        
        # Check if any preferred location matches
        for preferred in self.preferred_locations:
            preferred_lower = preferred.lower()
            
            # Check for country-level match
            if preferred_lower in country_matches:
                # If looking for a country, check if company is in that country
                country_indicators = country_matches[preferred_lower]
                if any(indicator in location_text for indicator in country_indicators):
                    return True
            
            # City-level matching
            preferred_normalized = location_normalizations.get(preferred_lower, preferred_lower)
            
            # Direct match
            if preferred_normalized in location_text:
                return True
            
            # Check if preferred location is in any location field
            for field in location_fields:
                if preferred_normalized in field:
                    return True
        
        return False
    
    def filter_company_by_location(self, company_data: Dict) -> bool:
        """Check if company should be included based on location criteria"""
        if not self.preferred_locations:
            return True  # No location filter means include all
        
        return self._matches_location(company_data)


def prioritize_contacts_in_response(
    response_data: Dict,
    criteria: Optional[str] = None
) -> Dict:
    """
    Prioritize contacts in a company response based on criteria
    
    IMPORTANT: This function ONLY prioritizes contacts, it does NOT filter them out.
    If you want to filter companies by location, do that at a higher level.
    
    Args:
        response_data: Company data response dictionary
        criteria: Criteria string with location and role preferences
    
    Returns:
        Modified response_data with prioritized contacts
    """
    if not criteria:
        return response_data
    
    try:
        prioritizer = ContactPrioritizer(criteria)
        
        # NOTE: We do NOT filter out contacts based on location here
        # Location filtering should be done at the company evaluation level, not contact level
        # This function only prioritizes the contacts that were already found
        
        # Prioritize emails by role (but don't filter them out)
        emails = response_data.get('scraped_data', {}).get('Emails', [])
        if emails:
            # Prioritize contacts: matching roles first, then others
            prioritized_emails = prioritizer.prioritize_contacts(response_data, emails)
            response_data['scraped_data']['Emails'] = prioritized_emails
            print(f"      Prioritized {len(prioritized_emails)} emails (original: {len(emails)})")
        else:
            print(f"      No emails to prioritize in response_data")
        
        # For phones, we can prioritize if they're associated with roles
        # (currently phones don't have role info, but we can add it later)
        
    except Exception as e:
        print(f"      Error in contact prioritization: {e}")
        import traceback
        traceback.print_exc()
        # Don't fail - just return original data
    
    return response_data

