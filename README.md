# AutoStream AI Agent

Conversational AI agent for AutoStream - an automated video editing SaaS for content creators. Uses LangGraph for state management and RAG for product knowledge.

## How to Run

```bash
# create virtual environment
python -m venv venv

# activate (windows)
venv\Scripts\activate

# activate (mac/linux)
source venv/bin/activate

# install deps
pip install -r requirements.txt

# set up env
cp .env.example .env
# add your Anthropic API key

# run the agent
python agent.py
```

Type messages to chat, `reset` to start over, `quit` to exit.

## Architecture (~200 words)

### Why LangGraph over AutoGen?

I went with LangGraph because it gives more control over conversation flow through its graph-based approach. The main reasons:

1. **Typed State** - LangGraph uses TypedDict for state, so I can define exactly what data persists across turns (messages, lead_data, current_intent, etc). This made tracking the lead collection flow much cleaner than trying to manage it with AutoGen's message-passing.

2. **Conditional Routing** - The graph lets me branch based on state. When intent detection flags a high-intent user, the flow automatically routes to lead collection nodes. With AutoGen I'd need more complex agent coordination.

3. **Built-in Checkpointing** - MemorySaver handles persistence automatically. State carries across conversation turns without me manually serializing anything.

### State Management

State flows through three nodes: `classify_intent` → `handle_lead_collection` (conditional) → `generate_response`

The AgentState tracks:
- `messages`: conversation history
- `current_intent`: classified intent (greeting, pricing_inquiry, high_intent_lead, etc)
- `lead_data`: dict with name/email/platform being collected
- `is_collecting_lead`: flag for collection mode
- `awaiting_field`: which field to ask for next
- `turn_count`: tracks conversation length

MemorySaver checkpointer stores state keyed by thread_id, so each conversation maintains its own context across 5-6+ turns.

## WhatsApp Integration

To deploy this on WhatsApp using webhooks:

**Architecture:**
```
User → WhatsApp → Meta Cloud API → Your Webhook → Agent → Response → WhatsApp API → User
```

**Steps:**

1. Set up WhatsApp Business API through Meta Cloud API or a provider like Twilio

2. Create a webhook endpoint (Flask example):
```python
from flask import Flask, request
from agent import AutoStreamAgent

app = Flask(__name__)
sessions = {}  # use Redis in production

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    user_id = data['from']
    message = data['body']
    
    if user_id not in sessions:
        sessions[user_id] = AutoStreamAgent()
    
    response = sessions[user_id].chat(message, thread_id=user_id)
    
    # send via WhatsApp API
    send_whatsapp_message(user_id, response)
    return {'status': 'ok'}

@app.route('/webhook', methods=['GET'])
def verify():
    # Meta webhook verification
    return request.args.get('hub.challenge')
```

3. Deploy to a server with HTTPS (required by Meta)

4. Register webhook URL in Meta Business settings

**Key considerations:**
- Use Redis or database for session storage (in-memory won't survive restarts)
- Implement session timeouts (clear after 30min inactivity)
- Add webhook signature verification for security
- Handle rate limits from WhatsApp API

## Project Structure

```
autostream-agent/
├── agent.py              # main LangGraph agent
├── intent_detection.py   # intent classification 
├── rag_pipeline.py       # knowledge base search
├── tools.py              # mock_lead_capture function
├── config.py             # settings
├── knowledge_base/
│   └── product_info.json # pricing & policies
├── requirements.txt
└── .env.example
```

## Features

**Intent Detection** - Classifies into: greeting, pricing_inquiry, product_inquiry, high_intent_lead, support_question, farewell

**RAG** - Searches JSON knowledge base for pricing/feature/policy info

**Lead Capture** - When high intent detected, collects name → email → platform, then calls `mock_lead_capture(name, email, platform)`
