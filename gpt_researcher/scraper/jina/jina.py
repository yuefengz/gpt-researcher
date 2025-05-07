
import os
import logging
import requests

from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from urllib.parse import urljoin
from readability import Document
from readabilipy import simple_json_from_html_string
from markdownify import markdownify as md
from ..utils import get_relevant_images

logger = logging.getLogger(__name__)


def is_429_error(exc: Exception) -> bool:
    """True ⇢ retry only when the exception is an HTTP 429."""
    from requests.exceptions import HTTPError
    return (
        isinstance(exc, HTTPError) and
        exc.response is not None and
        exc.response.status_code == 429          # "Too many requests"
    )


class JinaScraper:

    def __init__(self, link, session=None):
        self.link = link
        self.session = session or requests.Session()
        self.api_key = self.get_api_key()
        self.api_url = self.get_server_url()

    def get_api_key(self) -> str:
        """
        Gets the Jina API key
        Returns:
        Api key (str)
        """
        try:
            api_key = os.environ["JINA_API_KEY"]
        except KeyError:
            logger.warning("Jina API key not set.")
        return api_key

    def get_server_url(self) -> str:
        """
        Gets the Jina server URL.
        Default to official Jina API endpoint.
        Returns:
        server url (str)
        """
        try:
            server_url = os.environ["JINA_SERVER_URL"]
        except KeyError:
            server_url = 'https://r.jina.ai/'
        return server_url

    @retry(
        retry=retry_if_exception(is_429_error),        
        wait=wait_exponential(multiplier=1,         
                              min=10, max=600),     
        stop=stop_after_attempt(5),             
        reraise=True                            
    )
    def scrape(self) -> tuple:
        """
        This function extracts content and title from a specified link using the Jina API,
        images from the link are extracted using the functions from `gpt_researcher/scraper/utils.py`.

        Returns:
          A tuple containing the extracted content, a list of image URLs, and
          the title of the webpage specified by the `self.link` attribute.
        """
        try:
            # Prepare the request to Jina API
            if self.api_key:
                headers_json = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Return-Format": "html",
                }
            else:
                headers_json = {
                    "Content-Type": "application/json",
                    "X-Return-Format": "html",
                }
            
            data = {"url": self.link}
            response = requests.post(self.api_url, headers=headers_json, json=data) 
            response.raise_for_status()
            raw_html = response.text

            article = simple_json_from_html_string(raw_html, use_readability=True)
            title = article["title"]

            # cleaned HTML
            soup = BeautifulSoup(article["content"], "html.parser")

            markdown = md(article["content"])
            
            # Get relevant images using the utility function
            image_urls = get_relevant_images(soup, self.link)
            
            return markdown, image_urls, title
            
        except Exception as e:
            if is_429_error(e):
                raise e
            logger.exception(e)
            return "", [], ""