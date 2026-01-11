import os
import json
from typing import TypedDict, List, Any, Literal
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from intent_detection import IntentClassifier
from rag_pipeline import KnowledgeBase
from tools import mock_lead_capture, validate_email

load_dotenv()


class AgentState(TypedDict):
    messages: List[Any]
    current_intent: str
    lead_data: dict
    is_collecting_lead: bool
    awaiting_field: str
    turn_count: int
    lead_captured: bool


class AutoStreamAgent:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Missing ANTHROPIC_API_KEY in .env")
        
        self.llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            anthropic_api_key=api_key,
            temperature=0.7,
            max_tokens=500
        )
        
        self.intent_classifier = IntentClassifier(api_key)
        self.knowledge_base = KnowledgeBase()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        workflow.add_node("classify_intent", self._classify_intent_node)
        workflow.add_node("handle_lead_collection", self._handle_lead_collection_node)
        workflow.add_node("generate_response", self._generate_response_node)
        
        workflow.add_edge(START, "classify_intent")
        workflow.add_conditional_edges(
            "classify_intent",
            self._should_collect_lead,
            {
                "collect_lead": "handle_lead_collection",
                "respond": "generate_response"
            }
        )
        workflow.add_edge("handle_lead_collection", "generate_response")
        workflow.add_edge("generate_response", END)
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    def _classify_intent_node(self, state: AgentState) -> dict:
        last_message = state["messages"][-1]
        user_text = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
        intent = self.intent_classifier.classify(user_text)
        
        new_state = {"current_intent": intent}
        
        # reset lead_captured flag so we don't keep showing the same message
        if state.get("lead_captured"):
            new_state["lead_captured"] = False
        
        if intent == "high_intent_lead" and not state.get("is_collecting_lead") and not state.get("lead_captured"):
            new_state["is_collecting_lead"] = True
            new_state["awaiting_field"] = "ask_name"
            if not state.get("lead_data"):
                new_state["lead_data"] = {"name": None, "email": None, "platform": None}
        
        return new_state
    
    def _should_collect_lead(self, state: AgentState) -> Literal["collect_lead", "respond"]:
        if state.get("is_collecting_lead"):
            return "collect_lead"
        return "respond"
    
    def _handle_lead_collection_node(self, state: AgentState) -> dict:
        last_message = state["messages"][-1]
        user_input = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
        awaiting = state.get("awaiting_field", "ask_name")
        lead_data = state.get("lead_data", {"name": None, "email": None, "platform": None}).copy()
        
        updates = {}
        
        if awaiting == "ask_name":
            # just started collection, don't capture this message as name
            updates["awaiting_field"] = "name"
        elif awaiting == "name":
            lead_data["name"] = user_input.strip()
            updates["awaiting_field"] = "email"
        elif awaiting == "email":
            email = user_input.strip()
            if validate_email(email):
                lead_data["email"] = email
                updates["awaiting_field"] = "platform"
        elif awaiting == "platform":
            lead_data["platform"] = user_input.strip()
            updates["awaiting_field"] = "complete"
        
        updates["lead_data"] = lead_data
        
        if all(lead_data.get(f) for f in ["name", "email", "platform"]):
            result = mock_lead_capture(lead_data["name"], lead_data["email"], lead_data["platform"])
            updates["is_collecting_lead"] = False
            updates["lead_captured"] = True
            updates["capture_result"] = result
        
        return updates
    
    def _generate_response_node(self, state: AgentState) -> dict:
        intent = state.get("current_intent", "other")
        is_collecting = state.get("is_collecting_lead", False)
        awaiting = state.get("awaiting_field", "")
        lead_data = state.get("lead_data", {})
        
        # check if lead was just captured
        if state.get("lead_captured"):
            name = lead_data.get("name", "")
            email = lead_data.get("email", "")
            response = f"You're all set, {name}! We'll send your welcome info to {email}. Our team will reach out within 24 hours to help you get started!"
            return {
                "messages": state["messages"] + [AIMessage(content=response)],
                "turn_count": state.get("turn_count", 0) + 1
            }
        
        if is_collecting:
            if awaiting == "name":
                response = "That's great! I'd love to help you get started. What's your name?"
            elif awaiting == "email":
                name = lead_data.get("name", "there")
                response = f"Nice to meet you, {name}! What's your email address?"
            elif awaiting == "platform":
                response = "Got it! Which platform do you create content for? (YouTube, Instagram, TikTok, etc.)"
            else:
                response = "Great! Let's get you started. What's your name?"
            
            return {
                "messages": state["messages"] + [AIMessage(content=response)],
                "turn_count": state.get("turn_count", 0) + 1
            }
        
        last_msg = state["messages"][-1]
        query = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        context = ""
        if intent in ["pricing_inquiry", "product_inquiry", "support_question"]:
            relevant = self.knowledge_base.search(query)
            if relevant:
                context = "\n\nProduct Information:\n" + "\n".join(relevant)
        
        system_prompt = f"""You are a friendly sales assistant for AutoStream, an automated video editing SaaS for content creators.

Help customers learn about our product and guide interested users toward signing up.

Keep responses conversational and concise (2-3 sentences).
{context}

Pricing:
- Basic Plan: $29/month - 10 videos/month, 720p resolution
- Pro Plan: $79/month - Unlimited videos, 4K resolution, AI captions

Policies:
- No refunds after 7 days
- 24/7 support available only on Pro plan

If someone wants to sign up or try the product, let them know you can help get them started."""

        messages = [SystemMessage(content=system_prompt)]
        
        for msg in state["messages"][-6:]:
            if isinstance(msg, HumanMessage):
                messages.append(msg)
            elif isinstance(msg, AIMessage):
                messages.append(msg)
            else:
                messages.append(HumanMessage(content=str(msg)))
        
        response = self.llm.invoke(messages)
        
        return {
            "messages": state["messages"] + [AIMessage(content=response.content)],
            "turn_count": state.get("turn_count", 0) + 1
        }
    
    def chat(self, user_message: str, thread_id: str = "default") -> str:
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            current_state = self.graph.get_state(config)
            if current_state.values:
                existing_messages = current_state.values.get("messages", [])
                lead_data = current_state.values.get("lead_data", {"name": None, "email": None, "platform": None})
                is_collecting = current_state.values.get("is_collecting_lead", False)
                awaiting = current_state.values.get("awaiting_field", "")
                turn_count = current_state.values.get("turn_count", 0)
            else:
                existing_messages = []
                lead_data = {"name": None, "email": None, "platform": None}
                is_collecting = False
                awaiting = ""
                turn_count = 0
        except Exception:
            existing_messages = []
            lead_data = {"name": None, "email": None, "platform": None}
            is_collecting = False
            awaiting = ""
            turn_count = 0
        
        input_state = {
            "messages": existing_messages + [HumanMessage(content=user_message)],
            "current_intent": "",
            "lead_data": lead_data,
            "is_collecting_lead": is_collecting,
            "awaiting_field": awaiting,
            "turn_count": turn_count
        }
        
        result = self.graph.invoke(input_state, config)
        
        if result["messages"]:
            last = result["messages"][-1]
            return last.content if hasattr(last, 'content') else str(last)
        
        return "I'm here to help! Ask me anything about AutoStream."
    
    def reset_conversation(self, thread_id: str = "default"):
        pass


def main():
    print("AutoStream AI Agent")
    print("=" * 40)
    print("Type 'quit' to exit, 'reset' for new conversation\n")
    
    agent = AutoStreamAgent()
    thread_id = "session_1"
    
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        if user_input.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break
        
        if user_input.lower() == "reset":
            thread_id = f"session_{hash(str(os.urandom(8)))}"
            print("Conversation reset.\n")
            continue
        
        response = agent.chat(user_input, thread_id)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
