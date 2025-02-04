#!/usr/bin/env python3

import asyncio
import sys
import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import logging
from fake_useragent import UserAgent
import json
from urllib.parse import urljoin
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import aiohttp
import hashlib
import random
import tempfile
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ContentType(Enum):
    NEWS = "news"
    SOCIAL = "social"
    BLOG = "blog"

@dataclass
class NewsSource:
    name: str
    url: str
    content_type: ContentType
    article_selector: str
    title_selector: str
    body_selector: str
    date_selector: str
    link_selector: str
    image_selector: Optional[str] = None
    content_selector: Optional[str] = None
    category_selector: Optional[str] = None
    language: str = "en"
    requires_js: bool = False
    pagination_selector: Optional[str] = None
    max_pages: int = 1

class ContentProcessor:
    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\n\r\t]', ' ', text)
        return text.strip()

    @staticmethod
    def extract_date(date_str: str) -> Optional[str]:
        try:
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{2}/\d{2}/\d{4}',
                r'\w+ \d{1,2}, \d{4}',
                r'\d{2}-\d{2}-\d{4}',
                r'\d{1,2} \w+ \d{4}',
                r'\d{1,2} hours? ago',
                r'\d{1,2} minutes? ago',
                r'yesterday',
                r'today'
            ]

            for pattern in date_patterns:
                match = re.search(pattern, date_str.lower())
                if match:
                    date_str = match.group(0)

                    if 'ago' in date_str:
                        hours = int(re.search(r'\d+', date_str).group(0))
                        return (datetime.now() - pd.Timedelta(hours=hours)).isoformat()
                    elif 'yesterday' in date_str:
                        return (datetime.now() - pd.Timedelta(days=1)).isoformat()
                    elif 'today' in date_str:
                        return datetime.now().isoformat()

                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%B %d, %Y', '%d-%m-%Y', '%d %B %Y']:
                        try:
                            return datetime.strptime(date_str, fmt).isoformat()
                        except ValueError:
                            continue

            return datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Date parsing error: {str(e)}")
            return None

class ChineseNewsScraper:
    def __init__(self, max_retries: int = 3, delay: int = 2):
        self.max_retries = max_retries
        self.delay = delay
        self.user_agent = UserAgent()
        self.content_processor = ContentProcessor()
        self.article_cache = set()
    
        self.chrome_options = webdriver.ChromeOptions()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--remote-debugging-port=9222")
        self.chrome_options.add_argument("--disable-software-rasterizer")
        self.chrome_options.add_argument("--disable-extensions")
        self.chrome_options.add_argument("--disable-features=NetworkService,VizDisplayCompositor")
        self.chrome_options.add_argument("--disable-web-security")
        self.chrome_options.add_argument("--disable-site-isolation-trials")
        self.chrome_options.add_argument("--ignore-certificate-errors")
        self.chrome_options.add_argument(f"user-agent={self.user_agent.random}")
    
        self.temp_dir = tempfile.mkdtemp()
        self.chrome_options.add_argument(f'--user-data-dir={self.temp_dir}')
    
        try:
            self.service = ChromeService(
                ChromeDriverManager().install(),
                log_path="logs/chromedriver.log"
            )
            self.driver = webdriver.Chrome(
                service=self.service,
                options=self.chrome_options
            )
            self.driver.set_page_load_timeout(100)
            self.driver.set_script_timeout(100)
            self.driver.implicitly_wait(40)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': self.user_agent.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'DNT': '1',
            'Referer': 'https://www.google.com/',
            'Cache-Control': 'max-age=0'
        }

    async def _process_globaltimes_article(self, title_elem, source, current_url):
        """Helper method to process Global Times articles with error handling"""
        try:
            title = self.content_processor.clean_text(title_elem.text)
            article_url = title_elem.get_attribute('href')
            
            if not title or not article_url:
                logger.warning("Missing title or URL for Global Times article")
                return None
            
            article_hash = hashlib.md5(
                f"{title}{article_url}{source.name}".encode('utf-8')
            ).hexdigest()
            
            if article_hash in self.article_cache:
                logger.debug(f"Article already processed: {title}")
                return None
                
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.driver.get(article_url)
            
            try:
                # Wait for the article container to load
                article_container = WebDriverWait(self.driver, 100).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        source.body_selector
                    ))
                )
                
                # Extract the article title
                article_title = self.content_processor.clean_text(title)
                
                # Extract the body content
                body_text = article_container.text.strip()
                body_text = self.content_processor.clean_text(body_text)
                
                # Extract the image URL
                image_url = None
                if source.image_selector:
                    try:
                        image_element = self.driver.find_element(By.XPATH, source.image_selector)
                        image_url = image_element.get_attribute('src')
                    except Exception as e:
                        logger.warning(f"Could not extract image URL: {str(e)}")
                
                if len(body_text) > 50:
                    self.article_cache.add(article_hash)
                    return {
                        'source': source.name,
                        'title': article_title,
                        'date': datetime.now().isoformat(),
                        'link': article_url,
                        'body': body_text,
                        'content_type': source.content_type.value,
                        'language': source.language,
                        'hash': article_hash,
                        'timestamp': datetime.now().isoformat(),
                        'image_url': image_url
                    }
                else:
                    logger.warning(f"Article content too short: {article_url}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error extracting Global Times article content: {str(e)}")
                return None
                
            finally:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error processing Global Times article: {str(e)}")
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
            return None

    async def scrape_source(self, source: NewsSource) -> List[Dict]:
        articles = []
        retry_count = 0
        max_source_retries = 3

        while retry_count < max_source_retries:
            try:
                logger.info(f"Attempting to scrape {source.name} (attempt {retry_count + 1}/{max_source_retries})")
                
                self.driver.delete_all_cookies()
                await asyncio.sleep(random.uniform(2, 5))
                
                logger.info(f"Loading URL: {source.url}")
                self.driver.get(source.url)
                
                if source.name == "Global Times":
                    try:
                        header = WebDriverWait(self.driver, 100).until(
                            EC.presence_of_element_located((
                                By.XPATH,
                                '//*[@id="header"]/div/div[2]'
                            ))
                        )
                        logger.info("Global Times header element found")

                        latest_article = WebDriverWait(self.driver, 100).until(
                            EC.presence_of_element_located((
                                By.XPATH,
                                '//*[@id="main_section01"]/div/div[2]/div[1]/a'
                            ))
                        )
                        
                        article_data = await self._process_globaltimes_article(
                            latest_article, source, self.driver.current_url
                        )
                        
                        if article_data:
                            articles.append(article_data)
                            logger.info(f"Successfully processed Global Times article: {article_data['title']}")
                        
                    except Exception as e:
                        logger.error(f"Global Times elements not found: {str(e)}")
                        retry_count += 1
                        continue
                        
                elif source.name == "CGTN":
                    try:
                        WebDriverWait(self.driver, 100).until(
                            EC.presence_of_element_located((By.XPATH, "/html/body/div[1]/div[4]/h2/a"))
                        )
                        
                        article_titles = WebDriverWait(self.driver, 100).until(
                            EC.presence_of_all_elements_located(
                                (By.XPATH, source.article_selector)
                            )
                        )
                        
                        debug_file = f"logs/debug_{source.name.lower().replace(' ', '_')}_{retry_count}.html"
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        logger.info(f"Saved debug HTML to {debug_file}")
                        
                        for title_elem in article_titles:
                            try:
                                title = self.content_processor.clean_text(title_elem.text)
                                article_url = title_elem.get_attribute('href')
                                
                                if not title or not article_url:
                                    logger.warning("Missing title or URL, skipping article")
                                    continue
                                
                                logger.info(f"Processing article: {title}")
                                
                                article_hash = hashlib.md5(
                                    f"{title}{article_url}{source.name}".encode('utf-8')
                                ).hexdigest()
                                
                                if article_hash in self.article_cache:
                                    logger.debug(f"Article already processed: {title}")
                                    continue
                                
                                current_url = self.driver.current_url
                                
                                title_elem.click()
                                
                                content_div = WebDriverWait(self.driver, 100).until(
                                    EC.presence_of_element_located((By.XPATH, source.body_selector))
                                )
                                
                                paragraphs = content_div.find_elements(By.TAG_NAME, "p")
                                body_text = []
                                
                                for para in paragraphs:
                                    para_text = para.text.strip()
                                    if para_text:
                                        body_text.append(para_text)
                                
                                body_text = "\n".join(body_text)
                                body_text = self.content_processor.clean_text(body_text)
                                
                                # Extract image URL
                                image_url = None
                                if source.image_selector:
                                    try:
                                        image_element = self.driver.find_element(By.XPATH, source.image_selector)
                                        image_url = image_element.get_attribute('src')
                                    except Exception as e:
                                        logger.warning(f"Could not extract image URL: {str(e)}")
                                
                                if len(body_text) < 50:
                                    logger.warning(f"Article content too short: {article_url}")
                                    self.driver.get(current_url)
                                    continue
                                
                                self.article_cache.add(article_hash)
                                articles.append({
                                    'source': source.name,
                                    'title': title,
                                    'date': datetime.now().isoformat(),
                                    'link': article_url,
                                    'body': body_text,
                                    'content_type': source.content_type.value,
                                    'language': source.language,
                                    'hash': article_hash,
                                    'timestamp': datetime.now().isoformat(),
                                    'image_url': image_url
                                })
                                
                                logger.info(f"Successfully processed CGTN article: {title}")
                                
                                self.driver.get(current_url)
                                await asyncio.sleep(2)
                                
                            except Exception as e:
                                logger.error(f"Error processing CGTN article: {str(e)}")
                                self.driver.get(current_url)
                                continue
                                
                    except Exception as e:
                        logger.error(f"CGTN elements not found: {str(e)}")
                        retry_count += 1
                        continue

                elif source.name == "CGTN China":
                    try:
                        # Wait for the article container to load
                        WebDriverWait(self.driver, 100).until(
                            EC.presence_of_element_located((By.XPATH, source.article_selector))
                        )
                        
                        # Find all article elements
                        article_titles = WebDriverWait(self.driver, 100).until(
                            EC.presence_of_all_elements_located((By.XPATH, source.article_selector))
                        )
                        
                        debug_file = f"logs/debug_{source.name.lower().replace(' ', '_')}_{retry_count}.html"
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        logger.info(f"Saved debug HTML to {debug_file}")
                        
                        for title_elem in article_titles:
                            try:
                                # Extract the article title from the main page
                                title = self.content_processor.clean_text(title_elem.text)
                                
                                if not title:
                                    logger.warning("Missing title, skipping article")
                                    continue
                                
                                logger.info(f"Processing article: {title}")
                                
                                # Click on the article to navigate to the content page
                                title_elem.click()
                                
                                # Wait for the title on the content page to load
                                article_title = WebDriverWait(self.driver, 100).until(
                                    EC.presence_of_element_located((By.XPATH, source.title_selector))
                                ).text
                                
                                # Extract the body content
                                body_div = WebDriverWait(self.driver, 100).until(
                                    EC.presence_of_element_located((By.XPATH, source.body_selector))
                                )
                                paragraphs = body_div.find_elements(By.TAG_NAME, "p")
                                body_text = "\n".join([para.text.strip() for para in paragraphs if para.text.strip()])
                                body_text = self.content_processor.clean_text(body_text)
                                
                                # Extract the image URL
                                image_url = None
                                if source.image_selector:
                                    try:
                                        image_element = self.driver.find_element(By.XPATH, source.image_selector)
                                        image_url = image_element.get_attribute('src')
                                    except Exception as e:
                                        logger.warning(f"Could not extract image URL: {str(e)}")
                                
                                # Generate a unique hash for the article
                                article_hash = hashlib.md5(
                                    f"{title}{self.driver.current_url}{source.name}".encode('utf-8')
                                ).hexdigest()
                                
                                if article_hash in self.article_cache:
                                    logger.debug(f"Article already processed: {title}")
                                    self.driver.back()
                                    await asyncio.sleep(2)
                                    continue
                                
                                # Add the article to the list if the body content is sufficient
                                if len(body_text) >= 50:
                                    self.article_cache.add(article_hash)
                                    articles.append({
                                        'source': source.name,
                                        'title': article_title,
                                        'date': datetime.now().isoformat(),
                                        'link': self.driver.current_url,
                                        'body': body_text,
                                        'content_type': source.content_type.value,
                                        'language': source.language,
                                        'hash': article_hash,
                                        'timestamp': datetime.now().isoformat(),
                                        'image_url': image_url
                                    })
                                    logger.info(f"Successfully processed CGTN China article: {article_title}")
                                else:
                                    logger.warning(f"Article content too short: {self.driver.current_url}")
                                
                                # Navigate back to the main page
                                self.driver.back()
                                await asyncio.sleep(2)
                                
                            except Exception as e:
                                logger.error(f"Error processing CGTN China article: {str(e)}")
                                self.driver.back()
                                await asyncio.sleep(2)
                                continue
                                
                    except Exception as e:
                        logger.error(f"CGTN China elements not found: {str(e)}")
                        retry_count += 1
                        continue

                if articles:
                    logger.info(f"Successfully scraped {len(articles)} articles from {source.name}")
                    break
                    
                retry_count += 1
                await asyncio.sleep(self.delay * (retry_count + 1))
                
            except Exception as e:
                logger.error(f"Error scraping source {source.name} (attempt {retry_count + 1}): {str(e)}")
                retry_count += 1
                await asyncio.sleep(self.delay * (retry_count + 1))
                continue

        return articles

    async def scrape_all_sources(self) -> pd.DataFrame:
        all_articles = []
        tasks = [self.scrape_source(source) for source in NEWS_SOURCES]

        results = await asyncio.gather(*tasks)
        for articles in results:
            all_articles.extend(articles)

        df = pd.DataFrame(all_articles)
        if not df.empty:
            self._save_results(df)
        return df

    def _save_results(self, df: pd.DataFrame):
        os.makedirs('output', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        json_filename = f"output/chinese_news_{timestamp}.json"
        
        # Convert DataFrame to a list of dictionaries
        articles_list = df.to_dict(orient='records')
        
        # Save the JSON with proper indentation
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(articles_list, f, ensure_ascii=False, indent=4)

        logger.info(f"Saved results to {json_filename}")

# Updated sources list with Global Times and CGTN only
NEWS_SOURCES = [
    NewsSource(
        name="Global Times",
        url="https://www.globaltimes.cn/",
        content_type=ContentType.NEWS,
        article_selector='//*[@id="main_section01"]/div/div[2]/div[1]/a',
        title_selector='/html/body/div[4]/div/div/div[2]/div[1]/div[2]',
        body_selector='//div[@class="article_content"]',
        date_selector='',
        link_selector='//*[@id="main_section01"]/div/div[2]/div[1]/a',
        image_selector='//div[@class="article_content"]//img',
        language="en",
        requires_js=True
    ),
    NewsSource(
        name="CGTN",
        url="https://www.cgtn.com/sci-tech",
        content_type=ContentType.NEWS,
        article_selector='/html/body/div[1]/div[5]/div[1]/div/div[1]/div[2]/h3/a',
        title_selector='/html/body/div[1]/div[5]/div[1]/div/div[1]/div[2]/h3/a',
        body_selector='//*[@id="cmsMainContent"]',
        date_selector='',
        link_selector='/html/body/div[1]/div[5]/div[1]/div/div[1]/div[2]/h3/a',
        image_selector='//div[@class="cmsImage"]/img',
        language="en",
        requires_js=True
    ),
    NewsSource(
        name="CGTN China",
        url="https://www.cgtn.com/china",
        content_type=ContentType.NEWS,
        article_selector='/html/body/div[1]/div[5]/div[1]/div/div[1]/div[2]/h3',
        title_selector='/html/body/div[1]/div[4]/div/div/div[2]/div[1]/div[1]/div/h1',
        body_selector='//*[@id="cmsMainContent"]/div[2]',
        date_selector='',
        link_selector='//div[@class="news-item-intro"]//a[@class="news-headline"]',
        image_selector='//div[@class="cmsImage"]/img',
        language="en",
        requires_js=True
    )
]

async def main():
    print("Starting Chinese News Scraper...")
    print("This may take a few minutes. Check logs/scraper.log for detailed progress.")

    scraper = ChineseNewsScraper(max_retries=5, delay=2)
    df = await scraper.scrape_all_sources()

    print("\nScraping Complete!")
    print("=" * 50)
    print("\nScraped Articles Summary:")
    print(f"Total articles: {len(df)}")

    if not df.empty:
        print("\nSources distribution:")
        print(df['source'].value_counts())
        print("\nContent types distribution:")
        print(df['content_type'].value_counts())
        print("\nSample of articles:")
        print(df[['source', 'title', 'date']].head())
        print("\nResults have been saved to the 'output' directory.")
    else:
        print("No articles were scraped. Please check the logs for errors.")
        print("Debug HTML files have been saved in the logs directory.")

if __name__ == "__main__":
    try:
        asyncio.run(main(), debug=True)
    except KeyboardInterrupt:
        print("\nScraping cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)
