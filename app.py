import os
import json
import modules.cosmos_db as cosmos_db
from fastapi import FastAPI, Request, Response, HTTPException, Cookie
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.models import AzureAISearchTool, OpenApiAnonymousAuthDetails, OpenApiTool
from semantic_kernel.agents.azure_ai import AzureAIAgent, AzureAIAgentSettings
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole


templates = Jinja2Templates(directory="templates")

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global history (you could move it to CosmosDB as well)
conversation_history = []
event_log = []

async def create_agent(client, name, instructions, tools=None, tool_resources=None):
    """Helper to create an Azure AI Agent."""
    agent_def = await client.agents.create_agent(
        model=AzureAIAgentSettings.create().model_deployment_name,
        name=name,
        instructions=instructions,
        tools=tools,
        tool_resources=tool_resources,
    )
    return AzureAIAgent(client=client, definition=agent_def)

async def init_session(client, session_id: str):
    """
    Initialize the session:
      - create a thread
      - save the agents in CosmosDB associated with session_id
    """
    # Check if the session already exists in CosmosDB
    session_data = await cosmos_db.get_session(session_id)
    if session_data:
        return session_data

    thread = await client.agents.create_thread()
    event_log.append({"event": "Thread Created", "details": f"New thread ID: {thread.id}"})

    # Create coordinator agents
    routing_instructions = (
        "You are a routing coordinator. When you receive a user's query, analyze it and output a JSON object "
        "that maps agent names to the sub-query they should answer. For example: "
        "{\"movieAgent\": \"Query for movies...\", \"docuAgent\": \"Query for Microsoft licensing products...\"}. "
        "Only include keys for agents that are relevant to the query and do not include any additional text."
    )
    synthesis_instructions = (
        "You are a synthesis coordinator. Given the original user query and the responses from the delegated agents, "
        "synthesize a final, coherent, and concise answer for the user. Organize the answer into appropriate sections. "
        "Do not include any JSON or extra markup."
    )
    routing_agent = await create_agent(client, "CoordinatorRouting", routing_instructions)
    synthesis_agent = await create_agent(client, "CoordinatorSynthesis", synthesis_instructions)

    session_data = {
        "thread": thread,
        "routing_agent": routing_agent,
        "synthesis_agent": synthesis_agent,
        "docu_agent": None,
        "movie_agent": None
    }
    await cosmos_db.save_session(session_id, session_data)
    return session_data

@app.post("/send_message")
async def send_message(request: Request, response: Response, session_id: str = Cookie(None)):
    """
    Endpoint to handle the user's message.
    Use session_id (stored in a cookie) to identify the session and reuse the agents.
    """
    body = await request.json()
    user_message = body.get("message")
    if not user_message:
        raise HTTPException(status_code=400, detail="No message provided")
    
    # If session_id does not exist, create one (e.g., using a UUID)
    if session_id is None:
        import uuid
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)
    
    creds = DefaultAzureCredential()
    client = AzureAIAgent.create_client(
        credential=creds,
        conn_str=AzureAIAgentSettings.create().project_connection_string.get_secret_value()
    )
    
    # Initialize or retrieve the session from CosmosDB
    agents = await init_session(client, session_id)
    thread = agents["thread"]

    # Routing
    routing_agent = agents["routing_agent"]
    await routing_agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=user_message))
    routing_output = ""
    async for content in routing_agent.invoke(thread_id=thread.id):
        routing_output += content.content
    event_log.append({"event": "Routing Decision", "details": routing_output})
    routing_decision = json.loads(routing_output)
    agent_responses = {}

    # Delegation
    for agent_name, subquery in routing_decision.items():
        if agent_name == "docuAgent" and not agents["docu_agent"]:
            # Create docuAgent if it does not exist
            connections = await client.connections._list_connections()
            conn_list = connections["value"]
            conn_id = ""
            for conn in conn_list:
                metadata = conn["properties"].get("metadata", {})
                if metadata.get("type", "").upper() == "AZURE_AI_SEARCH":
                    conn_id = conn["id"]
                    break
            index_id = os.environ.get("AZURE_SEARCH_INDEX_NAME")
            if not conn_id:
                print("No CognitiveSearch connection found. Using empty connection ID.")
            docu_instructions = (
                "You are an expert on Microsoft Licensing products. You are integrated with Azure AI Search via the 'azure_search' tool. "
                "Use this tool to retrieve detailed and concise information on various Microsoft products such a windows server, Dynamics, PowerPlatform among others. "
                "If you don´t find any relevant information in the aisearch, please answer with 'I could not find any content for you, sorry.'."
            )
            ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name=index_id)
            agents["docu_agent"] = await create_agent(
                client,
                "docuAgent",
                docu_instructions,
                tools=ai_search.definitions,
                tool_resources=ai_search.resources
            )
            await cosmos_db.save_session(session_id, agents)
        elif agent_name == "movieAgent" and not agents["movie_agent"]:
            # Create movieAgent if it does not exist
            movie_instructions = (
                "You are an expert in cinema information. Use the provided API tool to retrieve current movies, showtimes, and cinema details." 
                "Respond only with relevant movie or cinema information. Indicate the total number of movies available. "
                "Reply only with the first 10 in alphabetical order of the title. "
                "If asked about a specific title, search for it in the complete list of movies and use the movie ID to call the endpoint that provides the rest of the information."
            )
            cinemas_api_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "static", "openAPIjson", "cinemasapi.json")
            with open(cinemas_api_path, "r") as f:
                cinemas_api_spec = json.load(f)
            auth = OpenApiAnonymousAuthDetails()
            openapi_cinemas_tool = OpenApiTool(
                name="cinemasapi",
                spec=cinemas_api_spec,
                description="Access the cinemas API to retrieve movie listings, showtimes, and cinema details.",
                auth=auth
            )
            agents["movie_agent"] = await create_agent(
                client,
                "movieAgent",
                movie_instructions,
                tools=openapi_cinemas_tool.definitions
            )
            await cosmos_db.save_session(session_id, agents)

        agent = agents["docu_agent"] if agent_name == "docuAgent" else agents["movie_agent"]
        if agent:
            await agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=subquery))
            agent_response = ""
            async for content in agent.invoke(thread_id=thread.id):
                agent_response += content.content
            agent_responses[agent_name] = agent_response
            event_log.append({"event": f"{agent_name} Response", "details": agent_response})

    # Synthesis
    synthesis_agent = agents["synthesis_agent"]
    synthesis_input = json.dumps({"user_query": user_message, "agent_responses": agent_responses}, indent=2)
    await synthesis_agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=synthesis_input))
    final_response = ""
    async for content in synthesis_agent.invoke(thread_id=thread.id):
        final_response += content.content

    # Retrieve the existing conversation or create a new one
    conversation = await cosmos_db.get_conversation(session_id)
    if not conversation:
        conversation = {
            "id": session_id,
            "name": user_message[:20],  # Use the first 20 characters of the user's first message
            "messages": []
        }

    # Ensure the 'messages' key is present
    if "messages" not in conversation:
        conversation["messages"] = []

    # Update the conversation with the new message
    conversation["messages"].append({"role": "User", "message": user_message})
    for agent_name, response_text in agent_responses.items():
        conversation["messages"].append({"role": f"Agent {agent_name}", "message": response_text})
    conversation["messages"].append({"role": "Agent CoordinatorSynthesis", "message": final_response})

    # Save the conversation in CosmosDB
    await cosmos_db.save_conversation(session_id, conversation)

    return JSONResponse(content={"response": final_response})

@app.post("/end_session")
async def end_session(session_id: str = Cookie(None)):
    """
    Endpoint to end the session. We delete the associated agents in CosmosDB and free up resources.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID not found")
    
    # Retrieve the session from CosmosDB
    session_data = await cosmos_db.get_session(session_id)
    if not session_data:
        return JSONResponse(content={"message": "No session found"})

    creds = DefaultAzureCredential()
    client = await AzureAIAgent.create_client(
        credential=creds,
        conn_str=AzureAIAgentSettings.create().project_connection_string.get_secret_value()
    )
    
    # Delete the agents
    await client.agents.delete_agent(session_data["routing_agent"].id)
    await client.agents.delete_agent(session_data["synthesis_agent"].id)
    await client.agents.delete_agent(session_data["docu_agent"].id)
    await client.agents.delete_agent(session_data["movie_agent"].id)
    await cosmos_db.delete_session(session_id)
    return JSONResponse(content={"message": "Session ended and agents deleted"})

@app.get("/get_history")
def get_history():
    # Endpoint to get the conversation history
    return JSONResponse(content=conversation_history)

@app.get("/get_events")
def get_events():
    # Endpoint to get the event log
    return JSONResponse(content=event_log)

@app.get("/get_conversations")
async def get_conversations():
    # Endpoint to get all conversations
    conversations = await cosmos_db.get_all_conversations()
    return JSONResponse(content=conversations)

@app.post("/load_conversation")
async def load_conversation(request: Request):
    # Endpoint to load a specific conversation
    body = await request.json()
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="No conversation ID provided")
    conversation = await cosmos_db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return JSONResponse(content=conversation)

@app.post("/save_conversation")
async def save_conversation(request: Request):
    # Endpoint to save a specific conversation
    body = await request.json()
    conversation_id = body.get("conversation_id")
    conversation_data = body.get("conversation_data")
    if not conversation_id or not conversation_data:
        raise HTTPException(status_code=400, detail="Invalid data")
    await cosmos_db.save_conversation(conversation_id, conversation_data)
    return JSONResponse(content={"message": "Conversation saved"})

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    # Endpoint to render the index.html template
    return templates.TemplateResponse("index.html", {"request": request})