# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import asyncio

from main import get_company_data
from models.request_model import RequestModel, BatchRequestModel
from services.gpt_service import CompanyMatcher, MatchConfig
from fastapi import Depends


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
        timeout_seconds=45,
        batch_size=5,
        max_concurrent=10
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
    
    # Get company data
    company_data = await get_company_data(org_number)
    
    if not company_data:
        logger.error(f"Couldn't generate brand profile for {org_number}")
        raise HTTPException(status_code=404, detail="Company data not found")
    
    # Check match

  
    filtered_data = await clean_company_info(org_number)
    print(filtered_data)
    
    match_result = await matcher.async_check_match(criteria, filtered_data)
    
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

@app.post("/evaluate-batch")
async def evaluate_batch_companies(
    request: BatchRequestModel,
    matcher: CompanyMatcher = Depends(get_matcher)
):
    """
    Evaluate multiple companies in batch
    
    """
    start_time = time.time()
    
    if not request.org_numbers:
        raise HTTPException(status_code=400, detail="No organization numbers provided")
    
    if len(request.org_numbers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 companies per batch")
    
    logger.info(f"Starting batch evaluation of {len(request.org_numbers)} companies")
    
    try:
        # Process batch
        results = await matcher.process_batch(
            org_numbers=request.org_numbers,
            criteria=request.criteria,
            get_company_data_func=get_company_data,
            batch_size=request.batch_size,
            clean_company_info_func=clean_company_info
        )
        
        # Calculate statistics
        successful = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - successful
        match_count = sum(1 for r in results if r.get("is_match") == True)
        
        processing_time = time.time() - start_time
        
        response = {
            "total_companies": len(request.org_numbers),
            "processed_companies": len(results),
            "successful_evaluations": successful,
            "failed_evaluations": failed,
            "matching_companies": match_count,
            "match_rate": f"{(match_count/len(results)*100):.1f}%" if results else "0%",
            "total_processing_time_seconds": round(processing_time, 2),
            "average_time_per_company": round(processing_time/len(results), 2) if results else 0,
            "results": results
        }
        
        logger.info(f"Batch completed in {processing_time:.2f}s: {successful} success, {failed} failed, {match_count} matches")
        
        return response
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "company-evaluator",
        "timestamp": time.time()
    }