"""
News sources configuration and RSS feed management
"""
import feedparser
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Major news sources with their RSS feeds
NEWS_SOURCES = {
    "cnn": {
        "name": "CNN",
        "rss_feeds": [
            "http://rss.cnn.com/rss/edition.rss",
            "http://rss.cnn.com/rss/edition_world.rss",
            "http://rss.cnn.com/rss/edition_us.rss",
            "http://rss.cnn.com/rss/money_latest.rss"
        ],
        "domain": "cnn.com",
        "credibility_score": 0.85
    },
    "bbc": {
        "name": "BBC News",
        "rss_feeds": [
            "http://feeds.bbci.co.uk/news/rss.xml",
            "http://feeds.bbci.co.uk/news/world/rss.xml",
            "http://feeds.bbci.co.uk/news/business/rss.xml",
            "http://feeds.bbci.co.uk/news/technology/rss.xml"
        ],
        "domain": "bbc.com",
        "credibility_score": 0.92
    },
    "reuters": {
        "name": "Reuters",
        "rss_feeds": [
            "https://feeds.reuters.com/reuters/topNews",
            "https://feeds.reuters.com/reuters/worldNews", 
            "https://feeds.reuters.com/reuters/businessNews",
            "https://feeds.reuters.com/reuters/technologyNews"
        ],
        "domain": "reuters.com",
        "credibility_score": 0.95
    },
    "ap_news": {
        "name": "Associated Press",
        "rss_feeds": [
            "https://feeds.apnews.com/rss/apf-topnews",
            "https://feeds.apnews.com/rss/apf-usnews",
            "https://feeds.apnews.com/rss/apf-worldnews",
            "https://feeds.apnews.com/rss/apf-business"
        ],
        "domain": "apnews.com",
        "credibility_score": 0.93
    },
    "tech_crunch": {
        "name": "TechCrunch",
        "rss_feeds": [
            "https://feeds.feedburner.com/TechCrunch",
            "https://feeds.feedburner.com/techcrunch/startups",
            "https://feeds.feedburner.com/techcrunch/fundings-exits"
        ],
        "domain": "techcrunch.com",
        "credibility_score": 0.82
    },
    "bloomberg": {
        "name": "Bloomberg",
        "rss_feeds": [
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.bloomberg.com/technology/news.rss",
            "https://feeds.bloomberg.com/politics/news.rss"
        ],
        "domain": "bloomberg.com",
        "credibility_score": 0.88
    },
    "financial_times": {
        "name": "Financial Times",
        "rss_feeds": [
            "https://www.ft.com/rss/home",
            "https://www.ft.com/rss/companies",
            "https://www.ft.com/rss/markets"
        ],
        "domain": "ft.com",
        "credibility_score": 0.90
    }
}

class NewsAggregator:
    def __init__(self, user_agent: str = "News Intelligence Pro/1.0"):
        self.user_agent = user_agent
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": self.user_agent},
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_feed(self, feed_url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse a single RSS feed"""
        try:
            async with self.session.get(feed_url) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = feedparser.parse(content)
                    return {
                        "feed_url": feed_url,
                        "title": getattr(feed.feed, 'title', 'Unknown'),
                        "entries": feed.entries,
                        "updated": getattr(feed.feed, 'updated', None)
                    }
                else:
                    logger.warning(f"Failed to fetch {feed_url}: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {feed_url}: {e}")
            return None

    async def fetch_article_content(self, article_url: str) -> Optional[str]:
        """Fetch full article content from URL"""
        try:
            async with self.session.get(article_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Try to find main content areas
                    content_selectors = [
                        'article', '.article-content', '.story-content', 
                        '.post-content', '.entry-content', '[data-component="ArticleBody"]',
                        '.article-body', '.story-body'
                    ]
                    
                    for selector in content_selectors:
                        content_div = soup.select_one(selector)
                        if content_div:
                            return content_div.get_text(strip=True)
                    
                    # Fallback: get all paragraph text
                    paragraphs = soup.find_all('p')
                    if paragraphs:
                        return ' '.join([p.get_text(strip=True) for p in paragraphs])
                        
                    return soup.get_text(strip=True)[:5000]  # Limit content length
                else:
                    logger.warning(f"Failed to fetch article {article_url}: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching article content {article_url}: {e}")
            return None

    async def aggregate_news(
        self, 
        sources: List[str], 
        custom_feeds: List[str] = None,
        max_articles: int = 1000,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Aggregate news from multiple sources"""
        
        all_feeds = []
        
        # Add configured news sources
        for source in sources:
            if source in NEWS_SOURCES:
                source_config = NEWS_SOURCES[source]
                for feed_url in source_config["rss_feeds"]:
                    all_feeds.append({
                        "url": feed_url,
                        "source_name": source_config["name"],
                        "source_domain": source_config["domain"],
                        "credibility_score": source_config["credibility_score"]
                    })
        
        # Add custom RSS feeds
        if custom_feeds:
            for feed_url in custom_feeds:
                all_feeds.append({
                    "url": feed_url,
                    "source_name": "Custom",
                    "source_domain": "custom",
                    "credibility_score": 0.5  # Default for custom feeds
                })
        
        # Fetch all feeds concurrently
        tasks = [self.fetch_feed(feed["url"]) for feed in all_feeds]
        feed_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        articles = []
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        for i, result in enumerate(feed_results):
            if isinstance(result, Exception) or result is None:
                continue
                
            feed_info = all_feeds[i]
            
            for entry in result["entries"]:
                try:
                    # Parse publication date
                    pub_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        pub_date = datetime(*entry.updated_parsed[:6])
                    
                    # Skip old articles
                    if pub_date and pub_date < cutoff_time:
                        continue
                    
                    # Extract article data
                    article = {
                        "title": getattr(entry, 'title', 'No title'),
                        "url": getattr(entry, 'link', ''),
                        "summary": getattr(entry, 'summary', ''),
                        "published_at": pub_date.isoformat() if pub_date else None,
                        "author": getattr(entry, 'author', 'Unknown'),
                        "source": {
                            "name": feed_info["source_name"],
                            "domain": feed_info["source_domain"],
                            "credibility_score": feed_info["credibility_score"]
                        },
                        "content": None,  # Will be fetched if needed
                        "raw_entry": entry
                    }
                    
                    articles.append(article)
                    
                    if len(articles) >= max_articles:
                        break
                        
                except Exception as e:
                    logger.error(f"Error processing article entry: {e}")
                    continue
            
            if len(articles) >= max_articles:
                break
        
        # Sort by publication date (newest first), handle None values
        articles.sort(key=lambda x: x.get('published_at') or '1970-01-01T00:00:00Z', reverse=True)
        
        return articles[:max_articles]

    async def enrich_with_content(self, articles: List[Dict[str, Any]], max_concurrent: int = 5) -> List[Dict[str, Any]]:
        """Fetch full content for articles that need it"""
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_content_with_limit(article):
            async with semaphore:
                if article.get('url') and not article.get('content'):
                    content = await self.fetch_article_content(article['url'])
                    if content:
                        article['content'] = content
                return article
        
        # Fetch content concurrently with rate limiting
        tasks = [fetch_content_with_limit(article) for article in articles]
        enriched_articles = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        return [article for article in enriched_articles if not isinstance(article, Exception)]