import asyncio
import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from src.script import ChineseNewsScraper, NEWS_SOURCES

app = FastAPI()

@app.get("/scrape-news")
async def scrape_news():
    try:
        # Initialize the scraper
        scraper = ChineseNewsScraper(max_retries=5, delay=2)
        
        # Run the scraper
        df = await scraper.scrape_all_sources()
        
        # Check if the output file was created
        output_dir = 'output'
        if not os.path.exists(output_dir):
            raise HTTPException(status_code=500, detail="Output directory not found")
        
        # Find the latest JSON file
        json_files = [f for f in os.listdir(output_dir) if f.endswith('.json')]
        if not json_files:
            raise HTTPException(status_code=500, detail="No JSON output file found")
        
        latest_file = max(json_files, key=lambda x: os.path.getctime(os.path.join(output_dir, x)))
        file_path = os.path.join(output_dir, latest_file)
        
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Return the JSON data as the response
        return JSONResponse(content=data)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)