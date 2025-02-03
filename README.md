# CAIYI

This project provides a FastAPI-based web service for scraping Chinese news articles from various sources. The scraping logic is implemented in the `src/script.py` file, and the FastAPI application is defined in the `main.py` file.

## Getting Started

To get started, follow these steps:

1. Clone the repository:
```bash
git clone https://github.com/caiyi25/caiyi.git
cd caiyi
```

2. Create a virtual environment (optional but recommended):
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install the dependencies:
```bash
pip install -r requirements.txt
```

4. Run the FastAPI application:
```bash
uvicorn main:app --reload
```

Now, the FastAPI application should be running at http://127.0.0.1:8000.

## API Endpoints

The API provides a single endpoint for scraping news articles:

- `/scrape-news`: This endpoint scrapes news articles from various sources and returns them as a JSON response.

## Scraping Logic

The scraping logic is implemented in the `src/script.py` file. The `ChineseNewsScraper` class is responsible for scraping news articles from different sources.

The `NEWS_SOURCES` dictionary contains the URLs and parsing functions for each news source. You can add or modify the sources in this dictionary to scrape from additional websites.

The `scrape_all_sources` method of the `ChineseNewsScraper` class iterates through the `NEWS_SOURCES` dictionary, scrapes articles from each source, and combines them into a single DataFrame.

The DataFrame is then converted to a list of dictionaries using the `to_dict(orient='records')` method. This list is returned as the JSON response.

## Error Handling

The API includes basic error handling to catch and return HTTP 500 errors. If an exception occurs during the scraping process, the error message will be included in the JSON response.

## Deployment

To deploy the FastAPI application, you can use a containerization platform like Docker. A Dockerfile is provided in the root directory of the repository.

Build the Docker image:

```bash
docker build -t chinese-news-scraper-api .
```

Run the Docker container:

```bash
docker run -p 8000:8000 chinese-news-scraper-api
```

Now, the FastAPI application should be running in a Docker container at http://127.0.0.1:8000.

## Contributing

Contributions are welcome! If you find any bugs or have suggestions for improvements, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.
