# gpt_service.py (with robust field handling)
import json
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import hashlib
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator, ConfigDict
import backoff
from openai import OpenAI, AsyncOpenAI
import os
import logging
from dotenv import load_dotenv
from openai import APIError, RateLimitError, APITimeoutError
from datetime import datetime
import re

load_dotenv()

logger = logging.getLogger(__name__)

_openai_client = None
_async_openai_client = None

def get_openai_client():
    """Get singleton OpenAI client instance"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=3
        )
    return _openai_client

def get_async_openai_client():
    """Get singleton async OpenAI client instance"""
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=3
        )
    return _async_openai_client

# Pydantic models with robust validation
class CriteriaInfo(BaseModel):
    summary: str = Field(default="")
    required_fields: List[str] = Field(default_factory=list)
    model_config = ConfigDict(validate_assignment=True, extra='ignore')
    
    @field_validator('summary', mode='before')
    @classmethod
    def normalize_summary(cls, v):
        if v is None:
            return ""
        # If the LLM returns a list, join it into a string
        if isinstance(v, list):
            return " ".join(str(item) for item in v)
        # If it's already a string
        if isinstance(v, str):
            return v
        # Fallback
        return str(v)
    
    @field_validator('required_fields', mode='before')
    @classmethod
    def normalize_required_fields(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            # Try to parse JSON string
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if item]
            except:
                # fallback: comma-separated
                return [item.strip() for item in v.split(',') if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if item]
        return []

class MatchResult(BaseModel):
    match_score: int = Field(default=0, ge=0, le=100)
    reason: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_keywords: List[str] = Field(default_factory=list)
    unmatched_keywords: List[str] = Field(default_factory=list)
    processing_time: float = Field(default=0.0)
    model_config = ConfigDict(validate_assignment=True, extra='ignore')
    
    @field_validator('match_score', mode='before')
    @classmethod
    def normalize_match_score(cls, v):
        """Handle various match score formats"""
        if v is None:
            return 0
        if isinstance(v, str):
            try:
                # Try to extract number from string
                numbers = re.findall(r'\d+', v)
                if numbers:
                    return min(100, max(0, int(numbers[0])))
                # Try to parse directly
                return min(100, max(0, int(float(v))))
            except:
                return 0
        if isinstance(v, (int, float)):
            return min(100, max(0, int(v)))
        return 0
    
    @field_validator('confidence', mode='before')
    @classmethod
    def normalize_confidence(cls, v):
        """Handle various confidence formats including 'high', 'medium', 'low'"""
        if v is None:
            return 0.0
        
        # If it's already a number
        if isinstance(v, (int, float)):
            return min(1.0, max(0.0, float(v)))
        
        # If it's a string
        if isinstance(v, str):
            v_lower = v.lower().strip()
            
            # Handle common confidence words
            confidence_map = {
                'high': 0.9,
                'very high': 0.95,
                'medium': 0.7,
                'medium high': 0.75,
                'medium low': 0.4,
                'low': 0.3,
                'very low': 0.2,
                'certain': 1.0,
                'uncertain': 0.5,
                'doubtful': 0.3
            }
            
            if v_lower in confidence_map:
                return confidence_map[v_lower]
            
            # Try to extract percentage
            if '%' in v:
                try:
                    percentage = float(re.search(r'(\d+(\.\d+)?)%', v).group(1))
                    return percentage / 100.0
                except:
                    pass
            
            # Try to extract decimal number
            try:
                numbers = re.findall(r'\d+(\.\d+)?', v)
                if numbers:
                    num = float(numbers[0])
                    if num > 1.0:  # Might be percentage without % sign
                        return num / 100.0
                    return min(1.0, max(0.0, num))
            except:
                pass
            
            # Try direct conversion
            try:
                return min(1.0, max(0.0, float(v)))
            except:
                return 0.0
        
        # Default fallback
        return 0.0
    
    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, v):
        if v is None:
            return ""
        if isinstance(v, dict):
            try:
                return json.dumps(v)
            except:
                return str(v)
        if isinstance(v, list):
            return " ".join(str(item) for item in v)
        return str(v)
    
    @field_validator('matched_keywords', 'unmatched_keywords', mode='before')
    @classmethod
    def normalize_keyword_lists(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            # Try to parse as JSON array
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if item]
            except:
                # Try comma-separated
                return [item.strip() for item in v.split(',') if item.strip()]
        if isinstance(v, dict):
            return list(v.values())
        if isinstance(v, list):
            return [str(item).strip() for item in v if item is not None]
        return []

@dataclass
class MatchConfig:
    min_confidence: float = 0.7
    max_retries: int = 3
    timeout_seconds: int = 30
    cache_ttl: int = 3600
    batch_size: int = 5
    max_concurrent: int = 10

class CompanyMatcher:
    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()
        self.client = get_openai_client()
        self.async_client = get_async_openai_client()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
    @lru_cache(maxsize=1000)
    def _cached_criteria_extraction(self, criteria_hash: str, criteria: str) -> CriteriaInfo:
        """Cache criteria extraction results"""
        return self._extract_criteria_info(criteria)
    
    # def _extract_criteria_info(self, criteria: str) -> CriteriaInfo:
        """Sync method to extract criteria info"""
        system_prompt = """You are an expert at analyzing investment/business criteria.
        Extract keywords, themes, and a summary. Return valid JSON with these fields.
        
        IMPORTANT: Return ONLY JSON with this exact format:
        {
            "keywords": ["keyword1", "keyword2"],
            "summary": "brief summary text",
            "themes": ["theme1", "theme2"]
        }
        
        All values must be strings or arrays of strings. No nested objects."""
        
        prompt = f"""Analyze this criteria and return JSON:\n\n{criteria}"""
        
        return self._call_llm_with_retry(
            system_prompt=system_prompt,
            user_prompt=prompt,
            response_model=CriteriaInfo
        )
    
    def _extract_criteria_info(self, criteria: str) -> CriteriaInfo:
        """
        Extracts:
        - summary: short natural-language summary of the criteria
        - required_fields: list of top-level company fields needed to evaluate the criteria
        """

        system_prompt = """
        You are an expert in analyzing business/investment criteria and mapping them to a fixed schema of company data.

        ### Allowed Fields
        You may ONLY choose from these fields:
        - name
        - orgnr
        - purpose
        - companyType
        - contact
        - location
        - industry
        - registration
        - governance
        - financialSummary
        - accountingHistory
        - risks

        ### Task
        Read the criteria and list which of these fields are required to determine whether the company meets the criteria.

        ### Output Format (STRICT JSON ONLY)
        {
            "summary": "short summary text",
            "required_fields": ["field1", "field2"]
        }

        ### Rules
        - Only output fields directly required by the criteria.
        - DO NOT output fields not in the allowed list.
        - DO NOT infer beyond what the criteria explicitly needs.
        - Response must be valid JSON only.
        """

        user_prompt = f"""
        Analyze the following criteria and identify:
        1. A short summary
        2. Which of the allowed fields are required to evaluate the criteria

        Criteria:
        \"\"\"{criteria}\"\"\"
        """

        return self._call_llm_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=CriteriaInfo
        )



    @backoff.on_exception(
        backoff.expo,
        (APIError, RateLimitError, APITimeoutError),
        max_tries=3,
        max_time=30
    )
    def _call_llm_with_retry(self, system_prompt: str, user_prompt: str,
                             response_model: type[BaseModel]) -> BaseModel:
        """Sync LLM call with retry logic"""
        # Ensure "json" appears in messages
        if "json" not in user_prompt.lower():
            user_prompt += "\n\nReturn your answer as JSON."
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug(f"LLM raw response: {content[:200]}")
            
            # Parse JSON with fallback
            parsed = self._parse_llm_response(content, response_model)
            return parsed
            
        except Exception as e:
            logger.error(f"Sync LLM call failed: {str(e)}")
            raise
    
    def _parse_llm_response(self, content: str, response_model: type[BaseModel]) -> BaseModel:
        """Robust parsing of LLM response"""
        # Strategy 1: Direct JSON parse
        try:
            parsed = json.loads(content)
            return response_model(**parsed)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON with regex
        json_pattern = r'\{[^{}]*\{[^{}]*\}[^{}]*\}|\{[^{}]*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)
        
        for match in reversed(matches):  # Try from last to first
            try:
                # Clean up common issues
                cleaned = match.replace('\n', ' ').replace('\t', ' ')
                parsed = json.loads(cleaned)
                return response_model(**parsed)
            except:
                continue
        
        # Strategy 3: Try to clean markdown
        cleaned = re.sub(r'```json\s*|\s*```', '', content)
        cleaned = re.sub(r'```\s*|\s*```', '', cleaned)
        
        try:
            parsed = json.loads(cleaned)
            return response_model(**parsed)
        except json.JSONDecodeError:
            # Strategy 4: Manual extraction for MatchResult
            if response_model == MatchResult:
                return self._extract_match_result(content)
            elif response_model == CriteriaInfo:
                return CriteriaInfo(
                    keywords=[],
                    summary="Failed to parse response",
                    themes=[]
                )
            else:
                # Return default model
                return response_model()
    
    def _extract_match_result(self, content: str) -> MatchResult:
        """Extract MatchResult from text when JSON parsing fails"""
        result = {
            "match_score": 0,
            "reason": "",
            "confidence": 0.0,
            "matched_keywords": [],
            "unmatched_keywords": []
        }
        
        # Try to extract score
        score_match = re.search(r'match[_\s-]?score[\s:]*(\d+)', content, re.IGNORECASE)
        if score_match:
            result["match_score"] = min(100, int(score_match.group(1)))
        
        # Try to extract confidence
        confidence_patterns = [
            r'confidence[\s:]*(\d+(\.\d+)?)',
            r'confidence[\s:]*(\d+)%',
            r'confidence[\s:]*(\w+)'  # For "high", "medium", "low"
        ]
        
        for pattern in confidence_patterns:
            conf_match = re.search(pattern, content, re.IGNORECASE)
            if conf_match:
                try:
                    # Handle numeric confidence
                    result["confidence"] = float(conf_match.group(1)) / 100.0 if '%' in pattern else float(conf_match.group(1))
                except:
                    # Handle text confidence
                    conf_text = conf_match.group(1).lower()
                    if 'high' in conf_text:
                        result["confidence"] = 0.9
                    elif 'medium' in conf_text:
                        result["confidence"] = 0.7
                    elif 'low' in conf_text:
                        result["confidence"] = 0.3
                    else:
                        result["confidence"] = 0.5
                break
        
        # Extract reason (try to get text after "reason:")
        reason_match = re.search(r'reason[\s:]*([^.]+\.)', content, re.IGNORECASE)
        if reason_match:
            result["reason"] = reason_match.group(1).strip()
        else:
            # Use first sentence as reason
            sentences = re.split(r'[.!?]+', content)
            if sentences and sentences[0].strip():
                result["reason"] = sentences[0].strip()[:200]  # Limit length
        
        return MatchResult(**result)
    
    @backoff.on_exception(
        backoff.expo,
        (APIError, RateLimitError, APITimeoutError),
        max_tries=3,
        max_time=30
    )
    async def _async_call_llm_with_retry(self, system_prompt: str, user_prompt: str,
                                        response_model: type[BaseModel]) -> BaseModel:
        """Async LLM call with retry logic"""
        async with self._semaphore:
            # Ensure "json" appears in messages
            if "json" not in user_prompt.lower():
                user_prompt += "\n\nReturn your answer as JSON."
            
            try:
                response = await self.async_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=500
                )
                
                content = response.choices[0].message.content.strip()
                logger.debug(f"Async LLM raw response: {content[:200]}")
                
                # Parse JSON with fallback
                parsed = self._parse_llm_response(content, response_model)
                return parsed
                
            except Exception as e:
                logger.error(f"Async LLM call failed: {str(e)}")
                raise
    

    # def check_match(self, criteria: str, company_data: Dict) -> MatchResult:
    #     """Sync match check for single company"""
    #     start_time = datetime.now()
        
    #     try:
    #         # Extract criteria info (cached)
    #         cache_key = hashlib.md5(criteria.encode()).hexdigest()
    #         criteria_info = self._cached_criteria_extraction(cache_key, criteria)
    #         print(criteria_info)
            
    #         # Evaluate match
    #         relevant_fields = criteria_info.required_fields
    #         filtered_data = {
    #             field: company_data.get(field)
    #             for field in relevant_fields
    #             if field in company_data
    #         }

    #         print(filtered_data)

    #         result = self._evaluate_match(criteria_info, company_data)
            
    #         # Add processing time
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         result.processing_time = processing_time
            
    #         logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
    #         return result
            
    #     except Exception as e:
    #         logger.error(f"Match check failed: {e}")
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         return MatchResult(
    #             match_score=0,
    #             reason=f"Evaluation failed: {str(e)}",
    #             confidence=0.0,
    #             matched_keywords=[],
    #             unmatched_keywords=[],
    #             processing_time=processing_time
    #         )
    
    # async def async_check_match(self, criteria: str, company_data: Dict) -> MatchResult:
    #     """Async match check for single company"""
    #     start_time = datetime.now()
        
    #     try:
    #         # Extract criteria info (cached)
    #         cache_key = hashlib.md5(criteria.encode()).hexdigest()
    #         criteria_info = self._cached_criteria_extraction(cache_key, criteria)
    #         print(criteria_info)
            
    #         # Evaluate match
    #         relevant_fields = criteria_info.required_fields
    #         filtered_data = {
    #             field: company_data.get(field)
    #             for field in relevant_fields
    #             if field in company_data
    #         }

    #         print(filtered_data)

    #         result = await self._async_evaluate_match(criteria_info, filtered_data)
            
    #         # Add processing time
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         result.processing_time = processing_time
            
    #         logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
    #         return result
            
    #     except Exception as e:
    #         logger.error(f"Match check failed: {e}")
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         return MatchResult(
    #             match_score=0,
    #             reason=f"Evaluation failed: {str(e)}",
    #             confidence=0.0,
    #             matched_keywords=[],
    #             unmatched_keywords=[],
    #             processing_time=processing_time
    #         )
    
    # async def async_check_match(self, criteria: str, company_data: Dict) -> MatchResult:
    #     """Async match check for single company"""
    #     start_time = datetime.now()
        
    #     try:
    #         # First, validate that we have company data
    #         if not company_data or not isinstance(company_data, dict):
    #             logger.error(f"Invalid or empty company data received")
    #             return MatchResult(
    #                 match_score=0,
    #                 reason="No valid company data available for evaluation",
    #                 confidence=0.0,
    #                 matched_keywords=[],
    #                 unmatched_keywords=[],
    #                 processing_time=0.0
    #             )
            
    #         # Log what we received
    #         logger.info(f"Company data keys: {list(company_data.keys())}")
    #         logger.info(f"Company name: {company_data.get('name', 'Unknown')}")
            
    #         # Extract criteria info (cached)
    #         cache_key = hashlib.md5(criteria.encode()).hexdigest()
    #         criteria_info = self._cached_criteria_extraction(cache_key, criteria)
    #         logger.info(f"Required fields: {criteria_info.required_fields}")
            
    #         # Filter data to relevant fields
    #         relevant_fields = criteria_info.required_fields
            
    #         # Build filtered data, but keep all data if no specific fields identified
    #         if relevant_fields:
    #             filtered_data = {
    #                 field: company_data.get(field)
    #                 for field in relevant_fields
    #                 if field in company_data and company_data.get(field) is not None
    #             }
                
    #             # If filtering resulted in empty data, use full company data
    #             if not filtered_data:
    #                 logger.warning(f"Filtered data is empty. Required fields {relevant_fields} not found in company data. Using full data.")
    #                 filtered_data = company_data
    #         else:
    #             # No specific fields identified, use all data
    #             logger.info("No specific required fields identified, using full company data")
    #             filtered_data = company_data
            
    #         logger.info(f"Filtered data keys: {list(filtered_data.keys())}")
            
    #         # Validate filtered data is not empty
    #         if not filtered_data:
    #             logger.error("Filtered data is empty after processing")
    #             return MatchResult(
    #                 match_score=0,
    #                 reason="Required company data fields are missing or empty",
    #                 confidence=0.0,
    #                 matched_keywords=[],
    #                 unmatched_keywords=[],
    #                 processing_time=0.0
    #             )
            
    #         # Evaluate match
    #         result = await self._async_evaluate_match(criteria_info, filtered_data)
            
    #         # Add processing time
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         result.processing_time = processing_time
            
    #         logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
    #         return result
            
    #     except Exception as e:
    #         logger.error(f"Match check failed: {e}", exc_info=True)
    #         processing_time = (datetime.now() - start_time).total_seconds()
    #         return MatchResult(
    #             match_score=0,
    #             reason=f"Evaluation failed: {str(e)}",
    #             confidence=0.0,
    #             matched_keywords=[],
    #             unmatched_keywords=[],
    #             processing_time=processing_time
    #         )
    
    # def check_match(self, criteria: str, company_data: Dict) -> MatchResult:
        """Sync match check for single company"""
        start_time = datetime.now()
        
        try:
            # First, validate that we have company data
            if not company_data or not isinstance(company_data, dict):
                logger.error(f"Invalid or empty company data received")
                return MatchResult(
                    match_score=0,
                    reason="No valid company data available for evaluation",
                    confidence=0.0,
                    matched_keywords=[],
                    unmatched_keywords=[],
                    processing_time=0.0
                )
            
            # Log what we received
            logger.info(f"Company data keys: {list(company_data.keys())}")
            logger.info(f"Company name: {company_data.get('name', 'Unknown')}")
            
            # Extract criteria info (cached)
            cache_key = hashlib.md5(criteria.encode()).hexdigest()
            criteria_info = self._cached_criteria_extraction(cache_key, criteria)
            logger.info(f"Required fields: {criteria_info.required_fields}")
            
            # Filter data to relevant fields
            relevant_fields = criteria_info.required_fields
            
            # Build filtered data, but keep all data if no specific fields identified
            if relevant_fields:
                filtered_data = {
                    field: company_data.get(field)
                    for field in relevant_fields
                    if field in company_data and company_data.get(field) is not None
                }
                
                # If filtering resulted in empty data, use full company data
                if not filtered_data:
                    logger.warning(f"Filtered data is empty. Required fields {relevant_fields} not found in company data. Using full data.")
                    filtered_data = company_data
            else:
                # No specific fields identified, use all data
                logger.info("No specific required fields identified, using full company data")
                filtered_data = company_data
            
            logger.info(f"Filtered data keys: {list(filtered_data.keys())}")
            
            # Validate filtered data is not empty
            if not filtered_data:
                logger.error("Filtered data is empty after processing")
                return MatchResult(
                    match_score=0,
                    reason="Required company data fields are missing or empty",
                    confidence=0.0,
                    matched_keywords=[],
                    unmatched_keywords=[],
                    processing_time=0.0
                )
            
            # Evaluate match
            result = self._evaluate_match(criteria_info, filtered_data)
            
            # Add processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            result.processing_time = processing_time
            
            logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Match check failed: {e}", exc_info=True)
            processing_time = (datetime.now() - start_time).total_seconds()
            return MatchResult(
                match_score=0,
                reason=f"Evaluation failed: {str(e)}",
                confidence=0.0,
                matched_keywords=[],
                unmatched_keywords=[],
                processing_time=processing_time
            )

    async def async_check_match(self, criteria: str, company_data: Dict) -> MatchResult:
        """Async match check for single company"""
        start_time = datetime.now()
        
        try:
            # First, validate that we have company data
            if not company_data or not isinstance(company_data, dict):
                logger.error(f"Invalid or empty company data received")
                return MatchResult(
                    match_score=0,
                    reason="No valid company data available for evaluation",
                    confidence=0.0,
                    matched_keywords=[],
                    unmatched_keywords=[],
                    processing_time=0.0
                )
            
            # Log what we received
            logger.info(f"Company data keys: {list(company_data.keys())}")
            logger.info(f"Company name: {company_data.get('name', 'Unknown')}")
            
            # Extract criteria info (cached)
            cache_key = hashlib.md5(criteria.encode()).hexdigest()
            criteria_info = self._cached_criteria_extraction(cache_key, criteria)
            logger.info(f"Criteria summary: {criteria_info.summary}")
            
            # Always use full company data to avoid field mapping issues
            # The LLM will determine what's relevant from the complete dataset
            filtered_data = company_data
            
            logger.info(f"Using full company data with {len(filtered_data)} top-level fields")
            
            # Evaluate match
            result = await self._async_evaluate_match(criteria_info, filtered_data)
            
            # Add processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            result.processing_time = processing_time
            
            logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Match check failed: {e}", exc_info=True)
            processing_time = (datetime.now() - start_time).total_seconds()
            return MatchResult(
                match_score=0,
                reason=f"Evaluation failed: {str(e)}",
                confidence=0.0,
                matched_keywords=[],
                unmatched_keywords=[],
                processing_time=processing_time
            )
    
    def check_match(self, criteria: str, company_data: Dict) -> MatchResult:
        """Sync match check for single company"""
        start_time = datetime.now()
        
        try:
            # First, validate that we have company data
            if not company_data or not isinstance(company_data, dict):
                logger.error(f"Invalid or empty company data received")
                return MatchResult(
                    match_score=0,
                    reason="No valid company data available for evaluation",
                    confidence=0.0,
                    matched_keywords=[],
                    unmatched_keywords=[],
                    processing_time=0.0
                )
            
            # Log what we received
            logger.info(f"Company data keys: {list(company_data.keys())}")
            logger.info(f"Company name: {company_data.get('name', 'Unknown')}")
            
            # Extract criteria info (cached)
            cache_key = hashlib.md5(criteria.encode()).hexdigest()
            criteria_info = self._cached_criteria_extraction(cache_key, criteria)
            logger.info(f"Criteria summary: {criteria_info.summary}")
            
            # Always use full company data to avoid field mapping issues
            # The LLM will determine what's relevant from the complete dataset
            filtered_data = company_data
            
            logger.info(f"Using full company data with {len(filtered_data)} top-level fields")
            
            # Evaluate match
            result = self._evaluate_match(criteria_info, filtered_data)
            
            # Add processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            result.processing_time = processing_time
            
            logger.info(f"Match score: {result.match_score} in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Match check failed: {e}", exc_info=True)
            processing_time = (datetime.now() - start_time).total_seconds()
            return MatchResult(
                match_score=0,
                reason=f"Evaluation failed: {str(e)}",
                confidence=0.0,
                matched_keywords=[],
                unmatched_keywords=[],
                processing_time=processing_time
            )

    def _evaluate_match(self, criteria_info: CriteriaInfo, company_data: Dict) -> MatchResult:
        """Sync evaluation with explicit format instructions"""
        system_prompt = """You are an expert company evaluator. 
        
        Analyze the company against the criteria and return a JSON object with these EXACT fields:
        - match_score: integer from 0-100 (higher = better match)
        - reason: string explanation with specific evidence
        - confidence: decimal number from 0.0 to 1.0 (NOT text like 'high' or 'low')
        - matched_keywords: array of strings (which criteria keywords were found)
        - unmatched_keywords: array of strings (which criteria keywords were missing)
        
        IMPORTANT: 
        - confidence MUST be a number between 0.0 and 1.0, NOT text
        - All fields must be present
        - Return ONLY valid JSON"""
        
        criteria_json = criteria_info.model_dump_json(indent=2)
        prompt = f"""CRITERIA (JSON):
{criteria_json}

COMPANY DATA (JSON):
{json.dumps(company_data, indent=2)}

Evaluate and return JSON with the required fields."""
        
        return self._call_llm_with_retry(
            system_prompt=system_prompt,
            user_prompt=prompt,
            response_model=MatchResult
        )
    
    async def _async_evaluate_match(self, criteria_info: CriteriaInfo, 
                                   company_data: Dict) -> MatchResult:
        """Async evaluation with explicit format instructions"""
        system_prompt = """You are an expert company evaluator. 
        
        Analyze the company against the criteria and return a JSON object with these EXACT fields:
        - match_score: integer from 0-100 (higher = better match)
        - reason: string explanation with specific evidence
        - confidence: decimal number from 0.0 to 1.0 (NOT text like 'high' or 'low')
        - matched_keywords: array of strings (which criteria keywords were found)
        - unmatched_keywords: array of strings (which criteria keywords were missing)
        
        IMPORTANT: confidence MUST be a number, NOT text."""
        
        criteria_json = criteria_info.model_dump_json(indent=2)
        prompt = f"""CRITERIA (JSON):
{criteria_json}

COMPANY DATA (JSON):
{json.dumps(company_data, indent=2)}

Evaluate and return JSON with the required fields."""
        
        return await self._async_call_llm_with_retry(
            system_prompt=system_prompt,
            user_prompt=prompt,
            response_model=MatchResult
        )
    


    
    async def process_batch_with_criteria(self, org_numbers: List[str], criteria: str, 
                           get_company_data_func, clean_company_info_func, batch_size: int = 5,
                           timeout_per_company: float = 120.0) -> List[Dict]:
        """
        Process a batch of companies efficiently with parallel processing
        
        Args:
            org_numbers: List of organization numbers to process
            criteria: Criteria string for evaluation
            get_company_data_func: Function to get company data
            clean_company_info_func: Function to clean company info
            batch_size: Number of companies to process concurrently
            timeout_per_company: Maximum time to wait for each company (seconds)
        """
        all_results = []
        total_companies = len(org_numbers)
        
        logger.info(f"Starting batch processing of {total_companies} companies")
        
        # Extract criteria info once per batch (cached, but still more efficient)
        cache_key = hashlib.md5(criteria.encode()).hexdigest()
        criteria_info = self._cached_criteria_extraction(cache_key, criteria)
        logger.info(f"Extracted criteria info once for batch: {criteria_info.summary}")
        
        # Process in batches
        for i in range(0, total_companies, batch_size):
            batch_orgs = org_numbers[i:i + batch_size]
            
            logger.info(f"Processing batch {i//batch_size + 1}: companies {i+1}-{min(i+batch_size, total_companies)}")
            
            # Process all companies in batch concurrently
            async def process_single_company(org_number: str) -> Dict:
                """Process a single company with error handling and timeout protection"""
                try:
                    # Get company data with timeout protection
                    # Pass criteria for contact prioritization
                    try:
                        company_data = await asyncio.wait_for(
                            get_company_data_func(org_number, criteria),
                            timeout=timeout_per_company
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout getting company data for {org_number} after {timeout_per_company}s")
                        return {
                            "org_number": org_number,
                            "is_match": False,
                            "match_score": 0,
                            "reason": f"Timeout retrieving company data after {timeout_per_company}s",
                            "confidence": 0.0,
                            "matched_keywords": [],
                            "unmatched_keywords": [],
                            "processing_time": 0.0,
                            "status": "failed",
                            "error": f"Timeout after {timeout_per_company} seconds",
                            "company_profile": None
                        }
                    
                    if not company_data:
                        return {
                            "org_number": org_number,
                            "is_match": False,
                            "match_score": 0,
                            "reason": "Failed to retrieve company data",
                            "confidence": 0.0,
                            "matched_keywords": [],
                            "unmatched_keywords": [],
                            "processing_time": 0.0,
                            "status": "failed",
                            "error": "Company data not found",
                            "company_profile": None
                        }
                    
                    # Get cleaned company info for matching with timeout protection
                    try:
                        filtered_data = await asyncio.wait_for(
                            clean_company_info_func(org_number),
                            timeout=timeout_per_company
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout getting cleaned company info for {org_number} after {timeout_per_company}s")
                        return {
                            "org_number": org_number,
                            "is_match": False,
                            "match_score": 0,
                            "reason": f"Timeout retrieving cleaned company data after {timeout_per_company}s",
                            "confidence": 0.0,
                            "matched_keywords": [],
                            "unmatched_keywords": [],
                            "processing_time": 0.0,
                            "status": "failed",
                            "error": f"Timeout after {timeout_per_company} seconds",
                            "company_profile": company_data
                        }
                    
                    if not filtered_data:
                        return {
                            "org_number": org_number,
                            "is_match": False,
                            "match_score": 0,
                            "reason": "Failed to retrieve cleaned company data",
                            "confidence": 0.0,
                            "matched_keywords": [],
                            "unmatched_keywords": [],
                            "processing_time": 0.0,
                            "status": "failed",
                            "error": "Cleaned company data not found",
                            "company_profile": company_data
                        }
                    
                    # Evaluate match using pre-extracted criteria info with timeout
                    # This avoids re-extracting criteria for each company
                    try:
                        match_result = await asyncio.wait_for(
                            self._async_evaluate_match_with_criteria_info(criteria_info, filtered_data),
                            timeout=60.0  # 60 seconds max for LLM evaluation
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout evaluating match for {org_number} after 60s")
                        return {
                            "org_number": org_number,
                            "is_match": False,
                            "match_score": 0,
                            "reason": "Timeout evaluating match criteria",
                            "confidence": 0.0,
                            "matched_keywords": [],
                            "unmatched_keywords": [],
                            "processing_time": 0.0,
                            "status": "failed",
                            "error": "Match evaluation timeout",
                            "company_profile": company_data
                        }
                    
                    return {
                        "org_number": org_number,
                        "is_match": match_result.match_score >= 80,
                        "match_score": match_result.match_score,
                        "reason": match_result.reason,
                        "confidence": match_result.confidence,
                        "matched_keywords": match_result.matched_keywords,
                        "unmatched_keywords": match_result.unmatched_keywords,
                        "processing_time": match_result.processing_time,
                        "status": "success",
                        "company_profile": company_data
                    }
                    
                except Exception as e:
                    logger.error(f"Error processing {org_number}: {e}", exc_info=True)
                    return {
                        "org_number": org_number,
                        "is_match": False,
                        "match_score": 0,
                        "reason": f"Error: {str(e)}",
                        "confidence": 0.0,
                        "matched_keywords": [],
                        "unmatched_keywords": [],
                        "processing_time": 0.0,
                        "status": "failed",
                        "error": str(e),
                        "company_profile": None
                    }
            
            # Process all companies in batch concurrently with error handling
            batch_tasks = [process_single_company(org_number) for org_number in batch_orgs]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Handle any exceptions that weren't caught
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    org_number = batch_orgs[idx]
                    logger.error(f"Unexpected exception processing {org_number}: {result}", exc_info=True)
                    batch_results[idx] = {
                        "org_number": org_number,
                        "is_match": False,
                        "match_score": 0,
                        "reason": f"Unexpected error: {str(result)}",
                        "confidence": 0.0,
                        "matched_keywords": [],
                        "unmatched_keywords": [],
                        "processing_time": 0.0,
                        "status": "failed",
                        "error": str(result),
                        "company_profile": None
                    }
            
            all_results.extend(batch_results)
            
            # Small delay between batches to avoid rate limits
            if i + batch_size < total_companies:
                await asyncio.sleep(0.5)
        
        logger.info(f"Batch processing completed: {len(all_results)} results")
        return all_results
    
    async def _async_evaluate_match_with_criteria_info(self, criteria_info: CriteriaInfo, 
                                                      company_data: Dict) -> MatchResult:
        """Async evaluation using pre-extracted criteria info (avoids redundant LLM call)"""
        start_time = datetime.now()
        
        try:
            result = await self._async_evaluate_match(criteria_info, company_data)
            processing_time = (datetime.now() - start_time).total_seconds()
            result.processing_time = processing_time
            return result
        except Exception as e:
            logger.error(f"Match evaluation failed: {e}", exc_info=True)
            processing_time = (datetime.now() - start_time).total_seconds()
            return MatchResult(
                match_score=0,
                reason=f"Evaluation failed: {str(e)}",
                confidence=0.0,
                matched_keywords=[],
                unmatched_keywords=[],
                processing_time=processing_time
            )
    
    