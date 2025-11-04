"""
Cost management and billing system for News Intelligence Pro
"""
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from apify import Actor

logger = logging.getLogger(__name__)

class CostManager:
    def __init__(self):
        self.pricing = {
            "built_in_ai": 6.0,  # $6 per 1000 articles with built-in AI
            "byok": 2.0,         # $2 per 1000 articles with user's API key
            "free_tier_limit": 50,  # 50 free articles per month
        }
        self.current_session_cost = 0.0
        self.articles_processed = 0
        
    def calculate_pricing_tier(self, 
                             enable_ai: bool, 
                             user_api_key: Optional[str], 
                             articles_count: int) -> Dict[str, Any]:
        """Calculate pricing based on configuration"""
        
        if not enable_ai:
            # No AI analysis, very low cost
            cost_per_article = 0.001  # Just infrastructure costs
            total_cost = articles_count * cost_per_article
            tier = "basic"
            description = "Basic news aggregation (no AI analysis)"
            
        elif user_api_key:
            # BYOK tier - user provides API key
            cost_per_article = self.pricing["byok"] / 1000
            total_cost = articles_count * cost_per_article
            tier = "byok"
            description = "Enterprise BYOK tier (user's OpenAI API key)"
            
        else:
            # Built-in AI tier
            if articles_count <= self.pricing["free_tier_limit"]:
                # Free tier
                total_cost = 0.0
                tier = "free"
                description = f"Free tier ({articles_count}/{self.pricing['free_tier_limit']} articles)"
            else:
                # Paid tier
                free_articles = self.pricing["free_tier_limit"]
                paid_articles = articles_count - free_articles
                cost_per_article = self.pricing["built_in_ai"] / 1000
                total_cost = paid_articles * cost_per_article
                tier = "built_in_ai"
                description = f"Built-in AI tier ({free_articles} free + {paid_articles} paid articles)"
        
        return {
            "tier": tier,
            "description": description,
            "cost_per_article": cost_per_article if 'cost_per_article' in locals() else 0,
            "cost_per_1000": self.pricing.get(tier, 0) if tier in self.pricing else cost_per_article * 1000,
            "total_cost": total_cost,
            "articles_count": articles_count,
            "currency": "USD"
        }
    
    def check_daily_limits(self, user_id: str = "default") -> Dict[str, Any]:
        """Check if user has exceeded daily spending limits"""
        
        # In a real implementation, this would check a database
        # For now, we'll use conservative defaults
        daily_limit = float(os.environ.get("DAILY_SPEND_LIMIT", "50.0"))
        current_daily_spend = self.current_session_cost  # Simplified
        
        remaining_budget = max(0, daily_limit - current_daily_spend)
        articles_remaining = int(remaining_budget / (self.pricing["built_in_ai"] / 1000))
        
        return {
            "daily_limit": daily_limit,
            "current_spend": current_daily_spend,
            "remaining_budget": remaining_budget,
            "articles_remaining": articles_remaining,
            "limit_exceeded": current_daily_spend >= daily_limit
        }
    
    def validate_request(self, 
                        enable_ai: bool,
                        user_api_key: Optional[str],
                        max_articles: int) -> Dict[str, Any]:
        """Validate if the request is within limits and calculate costs"""
        
        # Calculate pricing
        pricing_info = self.calculate_pricing_tier(enable_ai, user_api_key, max_articles)
        
        # Check daily limits (only for built-in AI)
        if pricing_info["tier"] == "built_in_ai":
            limits = self.check_daily_limits()
            if limits["limit_exceeded"]:
                return {
                    "valid": False,
                    "error": f"Daily spending limit of ${limits['daily_limit']:.2f} exceeded. Current spend: ${limits['current_spend']:.2f}",
                    "pricing": pricing_info,
                    "limits": limits
                }
            
            if max_articles > limits["articles_remaining"]:
                suggested_articles = limits["articles_remaining"]
                return {
                    "valid": False,
                    "error": f"Request for {max_articles} articles exceeds remaining daily budget. Maximum allowed: {suggested_articles}",
                    "pricing": pricing_info,
                    "limits": limits,
                    "suggested_max_articles": suggested_articles
                }
        
        # Request is valid
        return {
            "valid": True,
            "pricing": pricing_info,
            "estimated_cost": pricing_info["total_cost"]
        }
    
    def track_usage(self, articles_processed: int, actual_cost: float = 0.0):
        """Track actual usage and costs"""
        self.articles_processed += articles_processed
        self.current_session_cost += actual_cost
        
        Actor.log.info(f"Processed {articles_processed} articles. Session cost: ${self.current_session_cost:.4f}")
    
    def generate_cost_report(self, analysis_results: list) -> Dict[str, Any]:
        """Generate detailed cost breakdown from analysis results"""
        
        total_ai_cost = 0.0
        total_articles = len(analysis_results)
        successful_analyses = 0
        failed_analyses = 0
        
        cost_breakdown = {
            "sentiment_analysis": 0.0,
            "summarization": 0.0,
            "classification": 0.0,
            "content_moderation": 0.0
        }
        
        for article in analysis_results:
            analysis = article.get("analysis", {})
            
            if "error" in analysis:
                failed_analyses += 1
                continue
                
            successful_analyses += 1
            article_cost = analysis.get("total_cost", 0.0)
            total_ai_cost += article_cost
            
            # Break down costs by component (if available)
            sentiment = analysis.get("sentiment", {})
            cost_breakdown["sentiment_analysis"] += sentiment.get("cost", 0.0)
            
            summarization = analysis.get("summarization", {})
            cost_breakdown["summarization"] += summarization.get("cost", 0.0)
            
            classification = analysis.get("classification", {})
            cost_breakdown["classification"] += classification.get("cost", 0.0)
        
        # Calculate platform costs
        platform_cost = self.current_session_cost - total_ai_cost
        
        # Generate report
        report = {
            "summary": {
                "total_articles_requested": total_articles,
                "successful_analyses": successful_analyses,
                "failed_analyses": failed_analyses,
                "success_rate": f"{(successful_analyses/total_articles*100):.1f}%" if total_articles > 0 else "0%"
            },
            "costs": {
                "ai_processing": {
                    "total": total_ai_cost,
                    "per_article": total_ai_cost / successful_analyses if successful_analyses > 0 else 0,
                    "breakdown": cost_breakdown
                },
                "platform_usage": platform_cost,
                "total_session_cost": self.current_session_cost,
                "currency": "USD"
            },
            "usage_stats": {
                "articles_processed": self.articles_processed,
                "average_cost_per_article": self.current_session_cost / self.articles_processed if self.articles_processed > 0 else 0
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return report
    
    def get_billing_summary(self, pricing_tier: str, articles_count: int) -> str:
        """Generate human-readable billing summary"""
        
        pricing_info = self.calculate_pricing_tier(
            enable_ai=pricing_tier != "basic",
            user_api_key=pricing_tier == "byok",
            articles_count=articles_count
        )
        
        if pricing_info["total_cost"] == 0:
            return f"✅ Free tier: {articles_count} articles analyzed at no cost"
        
        cost_per_1k = pricing_info["cost_per_1000"]
        total_cost = pricing_info["total_cost"]
        
        summary = f"""💰 Billing Summary:
• Tier: {pricing_info['description']}
• Articles processed: {articles_count:,}
• Rate: ${cost_per_1k:.2f} per 1,000 articles
• Total cost: ${total_cost:.4f} USD"""

        if pricing_tier == "built_in_ai":
            summary += f"\n• Includes: AI sentiment analysis, summarization, categorization, and content moderation"
        elif pricing_tier == "byok":
            summary += f"\n• Your OpenAI API usage will be billed separately"
            
        return summary