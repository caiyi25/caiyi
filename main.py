import asyncio
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from src.script import ChineseNewsScraper

app = FastAPI()

# Dictionary to store job statuses and results
jobs = {}

def scrape_and_store(job_id: str):
    """
    This function runs the scraper in the background and stores the result.
    """
    try:
        scraper = ChineseNewsScraper(max_retries=5, delay=2)
        df = asyncio.run(scraper.scrape_all_sources())  # Run async function in sync mode
        jobs[job_id] = {"status": "completed", "data": df.to_dict(orient='records')}  # Store results
    except Exception as e:
        jobs[job_id] = {"status": "failed", "error": str(e)}

@app.get("/scrape-news")
async def scrape_news(background_tasks: BackgroundTasks):
    """
    Starts a background scraping task and returns a Job ID immediately.
    """
    job_id = str(len(jobs) + 1)  # Generate a simple Job ID
    jobs[job_id] = {"status": "processing"}  # Mark job as in progress
    background_tasks.add_task(scrape_and_store, job_id)  # Run scraper in background
    return {"message": "Scraping started", "job_id": job_id}

@app.get("/scrape-news/{job_id}")
async def get_status(job_id: str):
    """
    Retrieves the status or result of a scraping job using its Job ID.
    """
    result = jobs.get(job_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JSONResponse(content=result, media_type="application/json")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
