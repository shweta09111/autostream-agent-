import json
import os
from typing import List


class KnowledgeBase:
    def __init__(self, kb_path: str = None):
        if kb_path is None:
            kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base", "product_info.json")
        
        self.documents = []
        self._load_knowledge_base(kb_path)
    
    def _load_knowledge_base(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # flatten the json into searchable text chunks
            if "pricing" in data:
                for plan in data["pricing"].get("plans", []):
                    text = f"Plan: {plan['name']} - ${plan['price']}/month. Features: {', '.join(plan.get('features', []))}"
                    self.documents.append(text)
                
                if "trial" in data["pricing"]:
                    self.documents.append(f"Free trial: {data['pricing']['trial']}")
            
            if "features" in data:
                for feature in data["features"]:
                    text = f"Feature: {feature['name']} - {feature['description']}"
                    self.documents.append(text)
            
            if "faqs" in data:
                for faq in data["faqs"]:
                    self.documents.append(f"FAQ: {faq['question']} Answer: {faq['answer']}")
            
            if "policies" in data:
                pol = data["policies"]
                if "refund" in pol:
                    self.documents.append(f"Refund policy: {pol['refund']}")
                if "support" in pol:
                    self.documents.append(f"Support: {pol['support']}")
        
        except FileNotFoundError:
            self.documents = [
                "Basic Plan: $29/month - 10 videos/month, 720p resolution",
                "Pro Plan: $79/month - Unlimited videos, 4K resolution, AI captions",
                "No refunds after 7 days",
                "24/7 support available only on Pro plan"
            ]
    
    def search(self, query: str, top_k: int = 3) -> List[str]:
        """simple keyword matching search"""
        query_lower = query.lower()
        keywords = query_lower.split()
        
        scored = []
        for doc in self.documents:
            doc_lower = doc.lower()
            score = sum(1 for kw in keywords if kw in doc_lower)
            if score > 0:
                scored.append((score, doc))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
