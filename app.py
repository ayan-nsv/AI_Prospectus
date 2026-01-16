import time
import httpx
import logging
import asyncio
from typing import List, Dict, Optional

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends

from main import get_company_data
from models.request_model import RequestModel, BatchRequestModel
from services.gpt_service import CompanyMatcher, MatchConfig
from clean_allabolag import clean_company_info

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Company Data API",
    description="API for fetching company information from various sources",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency for matcher
def get_matcher():
    config = MatchConfig(
        min_confidence=0.75,
        max_retries=3,
        timeout_seconds=60,  # Increased timeout for slower operations
        batch_size=20,  # Increased from 10 for better parallelism (process more companies concurrently)
        max_concurrent=50  # Increased from 20 to allow more concurrent LLM calls and operations
    )
    return CompanyMatcher(config)

@app.get("/")
async def root():
    return {"message": "Company Data API", "status": "active"}

@app.post("/evaluate-company")
async def evaluate_single_company(
    request: RequestModel,
    matcher: CompanyMatcher = Depends(get_matcher)
):
    """Evaluate single company"""
    start_time = time.time()
    
    org_number = request.org_number
    criteria = request.criteria
    
    # Overall timeout for single company evaluation: 5 minutes
    single_company_timeout = 300.0
    
    try:
        # Get company data (with criteria for contact prioritization) with timeout
        try:
            company_data = await asyncio.wait_for(
                get_company_data(org_number, criteria),
                timeout=single_company_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting company data for {org_number} after {single_company_timeout}s")
            raise HTTPException(
                status_code=504,
                detail=f"Timeout retrieving company data after {single_company_timeout/60:.1f} minutes"
            )
        
        if not company_data:
            logger.error(f"Couldn't generate brand profile for {org_number}")
            raise HTTPException(status_code=404, detail="Company data not found")
        
        # Check match with timeout
        try:
            filtered_data = await asyncio.wait_for(
                clean_company_info(org_number),
                timeout=60.0  # 60 seconds for cleaning
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout cleaning company info for {org_number} after 60s")
            raise HTTPException(
                status_code=504,
                detail="Timeout cleaning company information"
            )
        
        print(filtered_data)
        
        # Evaluate match with timeout
        try:
            match_result = await asyncio.wait_for(
                matcher.async_check_match(criteria, filtered_data),
                timeout=60.0  # 60 seconds for LLM evaluation
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout evaluating match for {org_number} after 60s")
            raise HTTPException(
                status_code=504,
                detail="Timeout evaluating match criteria"
            )
        
        is_match = match_result.match_score >= 80
        
        processing_time = time.time() - start_time
        
        return {
            "org_number": org_number,
            "is_match": is_match,
            "match_score": match_result.match_score,
            "reason": match_result.reason,
            "confidence": match_result.confidence,
            "matched_keywords": match_result.matched_keywords,
            "unmatched_keywords": match_result.unmatched_keywords,
            "company_profile": company_data,
            "processing_time_seconds": processing_time
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error evaluating company {org_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


async def process_batch_without_criteria(
    org_numbers: List[str],
    get_company_data_func,
    batch_size: int = 5,
    criteria: Optional[str] = None,
    timeout_per_company: float = 120.0  # 2 minutes per company max
 ) -> List[Dict]:
    """
    Process a batch of companies without criteria evaluation - just fetch company data
    
    Args:
        org_numbers: List of organization numbers to process
        criteria: Not used in this function but kept for signature compatibility
        get_company_data_func: Function to get company data
        clean_company_info_func: Function to clean company info
        batch_size: Number of companies to process concurrently
        timeout_per_company: Maximum time to wait for each company (seconds)
        
    Returns:
        List of results with company data
    """
    all_results = []
    total_companies = len(org_numbers)
    
    logger.info(f"Starting batch data retrieval for {total_companies} companies (no criteria evaluation)")
    
    # Process in batches
    for i in range(0, total_companies, batch_size):
        batch_orgs = org_numbers[i:i + batch_size]
        batch_results = []
        
        logger.info(f"Processing batch {i//batch_size + 1}: companies {i+1}-{min(i+batch_size, total_companies)}")
        
        # Create tasks for this batch with timeout protection
        async def process_single_company(org_number: str) -> Dict:
            """Process a single company with timeout protection"""
            try:
                # Get company data with timeout
                company_data = await asyncio.wait_for(
                    get_company_data_func(org_number, criteria),
                    timeout=timeout_per_company
                )
                
                if company_data and company_data.get("CompanyName"):
                    return {
                        "org_number": org_number,
                        "is_match": True,  # No criteria evaluation
                        "match_score": None,
                        "reason": "Data retrieved successfully - no criteria evaluation",
                        "confidence": None,
                        "matched_keywords": [],
                        "unmatched_keywords": [],
                        "processing_time": 0.0,
                        "status": "success",
                        "company_profile": company_data
                    }
                else:
                    return {
                        "org_number": org_number,
                        "is_match": False,
                        "match_score": None,
                        "reason": "Failed to retrieve company data",
                        "confidence": None,
                        "matched_keywords": [],
                        "unmatched_keywords": [],
                        "processing_time": 0.0,
                        "status": "failed",
                        "error": "Company data not found or incomplete",
                        "company_profile": None
                    }
            except asyncio.TimeoutError:
                logger.error(f"Timeout processing {org_number} after {timeout_per_company}s")
                return {
                    "org_number": org_number,
                    "is_match": False,
                    "match_score": None,
                    "reason": f"Timeout after {timeout_per_company} seconds",
                    "confidence": None,
                    "matched_keywords": [],
                    "unmatched_keywords": [],
                    "processing_time": 0.0,
                    "status": "failed",
                    "error": f"Timeout after {timeout_per_company} seconds",
                    "company_profile": None
                }
            except Exception as e:
                logger.error(f"Error processing {org_number}: {e}", exc_info=True)
                return {
                    "org_number": org_number,
                    "is_match": False,
                    "match_score": None,
                    "reason": f"Error: {str(e)}",
                    "confidence": None,
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
                    "match_score": None,
                    "reason": f"Unexpected error: {str(result)}",
                    "confidence": None,
                    "matched_keywords": [],
                    "unmatched_keywords": [],
                    "processing_time": 0.0,
                    "status": "failed",
                    "error": str(result),
                    "company_profile": None
                }
            else:
                logger.info(f"Retrieved data for {result.get('org_number')}: {result.get('status')}")
        
        all_results.extend(batch_results)
        
        # Small delay between batches to avoid overwhelming the system
        if i + batch_size < total_companies:
            await asyncio.sleep(0.5)
    
    logger.info(f"Batch data retrieval completed: {len(all_results)} results")
    return all_results


# CALLBACK_URL = "https://test-prospecting.funnelbud-flow.com/ai/jobs/batch-callback"
CALLBACK_URL = "https://webhook.site/474ebc21-b55d-4a3d-8fc0-c10bd220e153"

@app.post("/evaluate-batch")
async def evaluate_batch_companies(
    request: BatchRequestModel,
    matcher: CompanyMatcher = Depends(get_matcher)
 ):
    """
    Evaluate a batch of companies against criteria or just retrieve company data
    
    If criteria is provided: Evaluates companies and returns match scores
    If criteria is NOT provided: Only retrieves company data without evaluation
    """
    start_time = time.time()

    logger.info(f"Batch {request.batch_id} started with {len(request.org_numbers)} companies")

    # Validate input
    if not request.org_numbers:
        raise HTTPException(status_code=400, detail="No organization numbers provided")

    if len(request.org_numbers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 companies per batch")
    
    # Calculate overall batch timeout: 5 minutes per company, minimum 10 minutes, maximum 2 hours
    num_companies = len(request.org_numbers)
    overall_timeout = min(max(num_companies * 5 * 60, 600), 7200)  # 5 min/company, min 10min, max 2hrs
    
    logger.info(f"Batch timeout set to {overall_timeout}s ({overall_timeout/60:.1f} minutes) for {num_companies} companies")
    
    try:
        # Process based on whether criteria is provided with overall timeout protection
        if not request.criteria:
            logger.info(f"No criteria provided - retrieving company data only")
            results = await asyncio.wait_for(
                process_batch_without_criteria(
                    org_numbers=request.org_numbers,
                    get_company_data_func=get_company_data,
                    batch_size=request.batch_size or 5,
                    criteria=None  # No criteria for filtering, but may have contact priority preferences
                ),
                timeout=overall_timeout
            )
        else:
            logger.info(f"Criteria provided - evaluating companies against criteria")
            # Process batch with criteria evaluation
            results = await asyncio.wait_for(
                matcher.process_batch_with_criteria(
                    org_numbers=request.org_numbers,
                    criteria=request.criteria,
                    get_company_data_func=get_company_data,
                    batch_size=request.batch_size or 5,
                    clean_company_info_func=clean_company_info
                ),
                timeout=overall_timeout
            )
    except asyncio.TimeoutError:
        logger.error(f"Batch {request.batch_id} timed out after {overall_timeout}s")
        # Return partial results if any were processed
        results = []  # Will be handled below
        raise HTTPException(
            status_code=504,
            detail=f"Batch processing timed out after {overall_timeout/60:.1f} minutes. The batch may be too large or operations are taking too long."
        )

    # Calculate metrics
    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    
    # Match count only relevant if criteria was provided
    match_count = None
    match_rate = None
    if request.criteria:
        match_count = sum(1 for r in results if r.get("is_match") is True)
        match_rate = f"{(match_count / len(results) * 100):.1f}%" if results else "0%"

    total_time = time.time() - start_time

    # Prepare callback payload
    payload = {
        "batch_id": request.batch_id,
        "status": "success" if successful > failed else "partial" if successful > 0 else "failed",
        "total_companies": len(request.org_numbers),
        "processed_companies": len(results),
        "successful_evaluations": successful,
        "failed_evaluations": failed,
        "matching_companies": match_count,
        "match_rate": match_rate,
        "criteria_provided": bool(request.criteria),
        "total_processing_time_seconds": round(total_time, 2),
        "average_time_per_company": round(total_time / len(results), 2) if results else 0,
        "results": results
    }

    # Send callback
    callback_status = "success"
    try:
        logger.info(f"Sending callback for batch {request.batch_id}")
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(CALLBACK_URL, json=payload)

        if res.status_code != 200:
            logger.error(f"Callback failed with status {res.status_code}: {res.text}")
            callback_status = "failed"
        else:
            logger.info(f"Callback sent successfully for batch {request.batch_id}")

    except httpx.TimeoutException:
        logger.error(f"Callback timeout for batch {request.batch_id}")
        callback_status = "timeout"
    except Exception as e:
        logger.error(f"Callback error for batch {request.batch_id}: {e}", exc_info=True)
        callback_status = "error"

    # Return response
    return {
        "status": callback_status,
        "batch_id": request.batch_id,
        "summary": {
            "total": len(request.org_numbers),
            "successful": successful,
            "failed": failed,
            "matches": match_count,
            "processing_time": round(total_time, 2)
        }
    }


@app.post("/test-evaluate-batch")
async def test_evaluate_batch_companies(
    request: BatchRequestModel,
    matcher: CompanyMatcher = Depends(get_matcher)
 ):
    """
    Test endpoint for batch evaluation - always returns results directly without callback
    
    If criteria is provided: Evaluates companies and returns match scores
    If criteria is NOT provided: Only retrieves company data without evaluation
    """
    start_time = time.time()

    logger.info(f"Test batch started with {len(request.org_numbers)} companies")

    # Validate input
    if not request.org_numbers:
        raise HTTPException(status_code=400, detail="No organization numbers provided")

    if len(request.org_numbers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 companies per batch")
    
    # Calculate overall batch timeout: 5 minutes per company, minimum 10 minutes, maximum 2 hours
    num_companies = len(request.org_numbers)
    overall_timeout = min(max(num_companies * 5 * 60, 600), 7200)  # 5 min/company, min 10min, max 2hrs
    
    logger.info(f"Test batch timeout set to {overall_timeout}s ({overall_timeout/60:.1f} minutes) for {num_companies} companies")
    
    try:
        # Process based on whether criteria is provided with overall timeout protection
        if not request.criteria:
            logger.info(f"No criteria provided - retrieving company data only")
            results = await asyncio.wait_for(
                process_batch_without_criteria(
                    org_numbers=request.org_numbers,
                    get_company_data_func=get_company_data,
                    batch_size=request.batch_size or 5,
                    criteria=None
                ),
                timeout=overall_timeout
            )
        else:
            logger.info(f"Criteria provided - evaluating companies against criteria")
            # Process batch with criteria evaluation
            results = await asyncio.wait_for(
                matcher.process_batch_with_criteria(
                    org_numbers=request.org_numbers,
                    criteria=request.criteria,
                    get_company_data_func=get_company_data,
                    batch_size=request.batch_size or 5,
                    clean_company_info_func=clean_company_info
                ),
                timeout=overall_timeout
            )
    except asyncio.TimeoutError:
        logger.error(f"Test batch timed out after {overall_timeout}s")
        raise HTTPException(
            status_code=504,
            detail=f"Batch processing timed out after {overall_timeout/60:.1f} minutes. The batch may be too large or operations are taking too long."
        )

    # Calculate metrics
    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    
    # Match count only relevant if criteria was provided
    match_count = None
    match_rate = None
    if request.criteria:
        match_count = sum(1 for r in results if r.get("is_match") is True)
        match_rate = f"{(match_count / len(results) * 100):.1f}%" if results else "0%"

    total_time = time.time() - start_time

    # Return response with full results (no callback)
    return {
        "summary": {
            "total": len(request.org_numbers),
            "successful": successful,
            "failed": failed,
            "matches": match_count,
            "match_rate": match_rate,
            "processing_time": round(total_time, 2),
            "average_time_per_company": round(total_time / len(results), 2) if results else 0
        },
        "results": results 
    }
