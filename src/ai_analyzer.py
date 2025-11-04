"""
AI-powered news analysis engine using OpenAI
"""
import openai
import asyncio
import json
import re
import hashlib
from typing import Dict, List, Optional, Any, Tuple
import logging
from datetime import datetime
import tiktoken

logger = logging.getLogger(__name__)

class AINewsAnalyzer:
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", max_tokens: int = 1000):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.encoding = tiktoken.encoding_for_model(model)
        
        # Pricing per 1K tokens (as of 2025)
        self.pricing = {
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            "gpt-4": {"input": 0.01, "output": 0.03},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03}
        }
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for API usage"""
        if self.model not in self.pricing:
            return 0.0
        
        price_config = self.pricing[self.model]
        input_cost = (input_tokens / 1000) * price_config["input"]
        output_cost = (output_tokens / 1000) * price_config["output"]
        return input_cost + output_cost
    
    def truncate_text(self, text: str, max_tokens: int = 3000) -> str:
        """Truncate text to fit within token limits"""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        
        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)
    
    async def moderate_content(self, text: str) -> Dict[str, Any]:
        """Check content using OpenAI's moderation API"""
        try:
            response = await self.client.moderations.create(input=text)
            result = response.results[0]
            
            return {
                "flagged": result.flagged,
                "categories": dict(result.categories) if hasattr(result, 'categories') else {},
                "category_scores": dict(result.category_scores) if hasattr(result, 'category_scores') else {}
            }
        except Exception as e:
            logger.error(f"Content moderation failed: {e}")
            return {"flagged": False, "categories": {}, "category_scores": {}}
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of the text"""
        
        # Moderate content first
        moderation = await self.moderate_content(text)
        if moderation["flagged"]:
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "reasoning": "Content flagged by moderation",
                "moderation_flagged": True
            }
        
        prompt = f"""Analyze the sentiment of this news article text. Provide your analysis in JSON format:

Text: "{self.truncate_text(text, 2000)}"

Return JSON with:
- score: float between -1.0 (very negative) and 1.0 (very positive)
- label: "positive", "negative", or "neutral"
- confidence: float between 0.0 and 1.0
- reasoning: brief explanation of the sentiment

JSON:"""

        try:
            input_tokens = self.count_tokens(prompt)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1
            )
            
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = self.calculate_cost(input_tokens, output_tokens)
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                sentiment_data = json.loads(json_match.group())
                sentiment_data["cost"] = cost
                sentiment_data["moderation_flagged"] = False
                return sentiment_data
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {
                "score": 0.0,
                "label": "neutral", 
                "confidence": 0.0,
                "reasoning": f"Analysis failed: {str(e)}",
                "cost": 0.0,
                "moderation_flagged": False
            }
    
    async def summarize_article(self, title: str, content: str) -> Dict[str, Any]:
        """Generate a concise summary of the article"""
        
        full_text = f"{title}\n\n{content}"
        
        # Moderate content first
        moderation = await self.moderate_content(full_text[:1000])  # Check first 1000 chars
        if moderation["flagged"]:
            return {
                "summary": "Content unavailable due to moderation policies",
                "key_points": [],
                "cost": 0.0,
                "moderation_flagged": True
            }
        
        prompt = f"""Summarize this news article in 2-3 sentences and extract 3-5 key points. Return JSON format:

Title: {title}

Content: {self.truncate_text(content, 2500)}

Return JSON with:
- summary: 2-3 sentence summary
- key_points: array of 3-5 key points (each 1 sentence)

JSON:"""

        try:
            input_tokens = self.count_tokens(prompt)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2
            )
            
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = self.calculate_cost(input_tokens, output_tokens)
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                summary_data = json.loads(json_match.group())
                summary_data["cost"] = cost
                summary_data["moderation_flagged"] = False
                return summary_data
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return {
                "summary": "Summary unavailable",
                "key_points": [],
                "cost": 0.0,
                "moderation_flagged": False
            }
    
    async def classify_topics(self, title: str, content: str) -> Dict[str, Any]:
        """Classify article into topics and categories"""
        
        full_text = f"{title}\n\n{content}"
        
        categories = [
            "Politics", "Business", "Technology", "Healthcare", "Sports", 
            "Entertainment", "Science", "Environment", "Education", "Crime",
            "International", "Economy", "Finance", "Startup", "AI/ML",
            "Cybersecurity", "Energy", "Transportation", "Real Estate"
        ]
        
        prompt = f"""Classify this news article into relevant categories and extract entities. Return JSON format:

Title: {title}

Content: {self.truncate_text(content, 2000)}

Available categories: {', '.join(categories)}

Return JSON with:
- categories: array of 1-3 most relevant categories from the list above
- entities: object with arrays for "people", "companies", "locations", "events"
- keywords: array of 5-10 most important keywords/phrases

JSON:"""

        try:
            input_tokens = self.count_tokens(prompt)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1
            )
            
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = self.calculate_cost(input_tokens, output_tokens)
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                classification_data = json.loads(json_match.group())
                classification_data["cost"] = cost
                return classification_data
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            logger.error(f"Topic classification failed: {e}")
            return {
                "categories": ["General"],
                "entities": {"people": [], "companies": [], "locations": [], "events": []},
                "keywords": [],
                "cost": 0.0
            }
    
    async def analyze_article(self, article: Dict[str, Any], include_content: bool = True) -> Dict[str, Any]:
        """Complete AI analysis of a single article"""
        
        title = article.get("title", "")
        content = article.get("content", "") if include_content else article.get("summary", "")
        
        if not content:
            content = title  # Fallback to title if no content
        
        # Generate unique article ID
        article_text = f"{title}{content}"
        article_id = hashlib.sha256(article_text.encode()).hexdigest()[:16]
        
        # Run all analyses concurrently
        tasks = [
            self.analyze_sentiment(f"{title}\n{content}"),
            self.classify_topics(title, content)
        ]
        
        # Add summarization if we have substantial content
        if len(content) > 200:
            tasks.append(self.summarize_article(title, content))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0, result={
                "summary": article.get("summary", title),
                "key_points": [],
                "cost": 0.0,
                "moderation_flagged": False
            })))
        
        sentiment, classification, summarization = await asyncio.gather(*tasks)
        
        # Calculate total cost
        total_cost = (
            sentiment.get("cost", 0) + 
            classification.get("cost", 0) + 
            summarization.get("cost", 0)
        )
        
        # Calculate trending score (simple heuristic)
        trending_score = 0.5  # Base score
        if "breaking" in title.lower() or "urgent" in title.lower():
            trending_score += 0.3
        if abs(sentiment.get("score", 0)) > 0.7:  # Strong sentiment
            trending_score += 0.2
        
        analysis_result = {
            "article_id": article_id,
            "analyzed_at": datetime.now().isoformat(),
            "sentiment": sentiment,
            "classification": classification,
            "summarization": summarization,
            "trending_score": min(trending_score, 1.0),
            "total_cost": total_cost,
            "word_count": len(content.split()) if content else 0,
            "reading_time": f"{max(1, len(content.split()) // 200)} minutes" if content else "< 1 minute"
        }
        
        return analysis_result
    
    async def batch_analyze(
        self, 
        articles: List[Dict[str, Any]], 
        max_concurrent: int = 5,
        include_content: bool = True
    ) -> List[Dict[str, Any]]:
        """Analyze multiple articles with rate limiting"""
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_limit(article):
            async with semaphore:
                try:
                    analysis = await self.analyze_article(article, include_content)
                    article["analysis"] = analysis
                    return article
                except Exception as e:
                    logger.error(f"Analysis failed for article {article.get('title', 'Unknown')}: {e}")
                    article["analysis"] = {
                        "error": str(e),
                        "total_cost": 0.0,
                        "analyzed_at": datetime.now().isoformat()
                    }
                    return article
        
        # Process articles concurrently with rate limiting
        tasks = [analyze_with_limit(article) for article in articles]
        analyzed_articles = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        successful_analyses = [
            article for article in analyzed_articles 
            if not isinstance(article, Exception)
        ]
        
        return successful_analyses