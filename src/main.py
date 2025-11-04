"""
News Intelligence Pro - AI-powered news aggregation and analysis
Developed for the Apify $1M Challenge by Serup.ai
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from apify import Actor

from .news_sources import NewsAggregator
from .ai_analyzer import AINewsAnalyzer 
from .cost_manager import CostManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Main News Intelligence Pro actor logic"""
    async with Actor:
        # Initialize components
        cost_manager = CostManager()
        
        # Get actor input
        actor_input = await Actor.get_input() or {}
        Actor.log.info("News Intelligence Pro starting...")
        Actor.log.info(f"Input configuration: {actor_input}")
        
        # Parse input parameters
        news_sources = actor_input.get('news_sources', ['cnn', 'bbc', 'reuters'])
        custom_rss_feeds = []  # Removed from schema due to Apify constraints
        keywords_str = actor_input.get('keywords', '')
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()] if keywords_str else []
        enable_ai_analysis = actor_input.get('enable_ai_analysis', True)
        user_openai_key = actor_input.get('openai_api_key')
        max_articles = actor_input.get('max_articles', 1000)
        date_range = actor_input.get('date_range', '1d')
        languages = actor_input.get('languages', ['en'])
        
        # AI analysis options
        sentiment_analysis = actor_input.get('sentiment_analysis', True)
        summarization = actor_input.get('summarization', True)
        topic_classification = actor_input.get('topic_classification', True)
        entity_extraction = actor_input.get('entity_extraction', True)
        
        # Convert date range to hours
        date_range_hours = {
            '1h': 1, '6h': 6, '1d': 24, '3d': 72, '7d': 168, '30d': 720
        }.get(date_range, 24)
        
        # Validate request and calculate costs
        validation = cost_manager.validate_request(
            enable_ai=enable_ai_analysis,
            user_api_key=user_openai_key,
            max_articles=max_articles
        )
        
        if not validation["valid"]:
            Actor.log.error(f"Request validation failed: {validation['error']}")
            await Actor.exit(exit_code=1)
            return
        
        Actor.log.info("💰 Cost Estimate:")
        pricing_info = validation["pricing"]
        Actor.log.info(f"• Pricing tier: {pricing_info['description']}")
        Actor.log.info(f"• Articles to process: {max_articles}")
        Actor.log.info(f"• Estimated cost: ${pricing_info['total_cost']:.4f} USD")
        
        if pricing_info["total_cost"] > 0:
            Actor.log.info(f"• Rate: ${pricing_info['cost_per_1000']:.2f} per 1,000 articles")
        
        # Step 1: Aggregate news from sources
        Actor.log.info(f"📰 Aggregating news from {len(news_sources)} sources...")
        
        try:
            async with NewsAggregator() as aggregator:
                articles = await aggregator.aggregate_news(
                    sources=news_sources,
                    custom_feeds=custom_rss_feeds,
                    max_articles=max_articles,
                    hours_back=date_range_hours
                )
                
                Actor.log.info(f"Found {len(articles)} articles")
                
                if not articles:
                    Actor.log.warning("No articles found matching criteria")
                    await Actor.push_data({
                        "summary": "No articles found",
                        "timestamp": datetime.now().isoformat(),
                        "criteria": {
                            "sources": news_sources,
                            "date_range": date_range,
                            "max_articles": max_articles
                        }
                    })
                    return
                
                # Filter by keywords if specified
                if keywords:
                    Actor.log.info(f"🔍 Filtering articles by keywords: {keywords}")
                    keyword_lower = [k.lower() for k in keywords]
                    filtered_articles = []
                    
                    for article in articles:
                        title = article.get('title', '').lower()
                        summary = article.get('summary', '').lower()
                        
                        if any(keyword in title or keyword in summary for keyword in keyword_lower):
                            filtered_articles.append(article)
                    
                    articles = filtered_articles
                    Actor.log.info(f"After keyword filtering: {len(articles)} articles")
                
                # Step 2: Fetch full content for articles (if AI analysis is enabled)
                if enable_ai_analysis and (summarization or sentiment_analysis):
                    Actor.log.info("📄 Fetching full article content...")
                    articles = await aggregator.enrich_with_content(articles, max_concurrent=3)
        
        except Exception as e:
            Actor.log.error(f"Failed to aggregate news: {e}")
            Actor.log.error(f"News aggregation failed: {str(e)}")
            await Actor.exit(exit_code=1)
            return
        
        # Step 3: AI Analysis (if enabled)
        if enable_ai_analysis and articles:
            Actor.log.info("🧠 Starting AI analysis...")
            
            # Determine which API key to use
            if user_openai_key:
                api_key = user_openai_key
                Actor.log.info("Using user-provided OpenAI API key")
            else:
                api_key = os.environ.get('OPENAI_API_KEY')
                if not api_key:
                    Actor.log.error("No OpenAI API key available. Please provide your API key or use the free tier without AI analysis.")
                    Actor.log.error("OpenAI API key required for AI analysis")
                    await Actor.exit(exit_code=1)
                    return
                Actor.log.info("Using built-in OpenAI API key")
            
            try:
                analyzer = AINewsAnalyzer(api_key=api_key)
                
                # Configure analysis based on user preferences
                include_content = summarization or sentiment_analysis
                
                Actor.log.info(f"Analyzing {len(articles)} articles with AI...")
                Actor.log.info(f"• Sentiment analysis: {sentiment_analysis}")
                Actor.log.info(f"• Summarization: {summarization}")
                Actor.log.info(f"• Topic classification: {topic_classification}")
                Actor.log.info(f"• Entity extraction: {entity_extraction}")
                
                # Process articles in batches to manage costs and rate limits
                analyzed_articles = await analyzer.batch_analyze(
                    articles=articles,
                    max_concurrent=3,  # Conservative rate limiting
                    include_content=include_content
                )
                
                # Track usage and costs
                total_ai_cost = sum(
                    article.get("analysis", {}).get("total_cost", 0) 
                    for article in analyzed_articles
                )
                cost_manager.track_usage(len(analyzed_articles), total_ai_cost)
                
                Actor.log.info(f"✅ AI analysis completed. Cost: ${total_ai_cost:.4f}")
                
            except Exception as e:
                Actor.log.error(f"AI analysis failed: {e}")
                # Continue without AI analysis rather than failing completely
                Actor.log.info("Continuing without AI analysis...")
                analyzed_articles = articles
                
        else:
            analyzed_articles = articles
            Actor.log.info("Skipping AI analysis (disabled or no articles)")
        
        # Step 4: Generate output data
        Actor.log.info("📊 Generating output data...")
        
        # Add metadata to each article
        for article in analyzed_articles:
            article["processed_at"] = datetime.now().isoformat()
            article["processing_session"] = {
                "sources": news_sources,
                "keywords": keywords,
                "ai_enabled": enable_ai_analysis,
                "date_range": date_range
            }
        
        # Step 5: Save results to dataset
        Actor.log.info(f"💾 Saving {len(analyzed_articles)} articles to dataset...")
        
        # Save individual articles
        for article in analyzed_articles:
            await Actor.push_data(article)
        
        # Generate and save summary report
        cost_report = cost_manager.generate_cost_report(analyzed_articles)
        
        summary_report = {
            "type": "SUMMARY_REPORT",
            "session_info": {
                "processed_at": datetime.now().isoformat(),
                "sources_used": news_sources,
                "custom_feeds": len(custom_rss_feeds),
                "keywords_filter": keywords,
                "date_range": date_range,
                "languages": languages
            },
            "results": {
                "total_articles_found": len(analyzed_articles),
                "ai_analysis_enabled": enable_ai_analysis,
                "successful_analyses": cost_report["summary"]["successful_analyses"],
                "failed_analyses": cost_report["summary"]["failed_analyses"]
            },
            "cost_analysis": cost_report,
            "billing_summary": cost_manager.get_billing_summary(
                pricing_tier=validation["pricing"]["tier"],
                articles_count=len(analyzed_articles)
            )
        }
        
        await Actor.push_data(summary_report)
        
        # Step 6: Final logging and metrics
        Actor.log.info("🎉 News Intelligence Pro completed successfully!")
        Actor.log.info(f"📈 Session Statistics:")
        Actor.log.info(f"• Articles processed: {len(analyzed_articles)}")
        Actor.log.info(f"• AI analyses: {cost_report['summary']['successful_analyses']}")
        Actor.log.info(f"• Total session cost: ${cost_manager.current_session_cost:.4f}")
        Actor.log.info(f"• Average cost per article: ${cost_manager.current_session_cost/len(analyzed_articles):.4f}" if analyzed_articles else "N/A")
        
        if enable_ai_analysis:
            Actor.log.info(cost_manager.get_billing_summary(
                pricing_tier=validation["pricing"]["tier"],
                articles_count=len(analyzed_articles)
            ))


if __name__ == '__main__':
    asyncio.run(main())