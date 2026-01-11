from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage


class IntentClassifier:
    def __init__(self, api_key: str):
        self.llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            anthropic_api_key=api_key,
            temperature=0,
            max_tokens=50
        )
        
        self.intents = [
            "greeting",
            "pricing_inquiry",
            "product_inquiry", 
            "high_intent_lead",
            "support_question",
            "farewell",
            "other"
        ]
    
    def classify(self, message: str) -> str:
        prompt = f"""Classify the user message into exactly one intent category.

Categories:
- greeting: Hello, hi, hey, good morning, etc.
- pricing_inquiry: Questions about cost, plans, pricing
- product_inquiry: Questions about features, how it works
- high_intent_lead: User wants to sign up, try, start, buy, get started
- support_question: Questions about refunds, cancellation, policies
- farewell: Goodbye, thanks, bye, etc.
- other: Anything else

User message: "{message}"

Reply with ONLY the intent name, nothing else."""

        response = self.llm.invoke([
            SystemMessage(content="You are a simple intent classifier. Output only the intent category."),
            HumanMessage(content=prompt)
        ])
        
        intent = response.content.strip().lower()
        
        for valid in self.intents:
            if valid in intent:
                return valid
        
        return "other"
