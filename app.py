from flask import Flask, render_template, request, jsonify
import asyncio
import json
import os
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.models import AzureAISearchTool, OpenApiAnonymousAuthDetails, OpenApiTool
from semantic_kernel.agents.azure_ai import AzureAIAgent, AzureAIAgentSettings
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Store conversation history in memory
conversation_history = []
event_log = []

async def create_agent(client, name, instructions, tools=None, tool_resources=None):
    """Helper function to create an Azure AI Agent."""
    agent_def = await client.agents.create_agent(
        model=AzureAIAgentSettings.create().model_deployment_name,
        name=name,
        instructions=instructions,
        tools=tools,
        tool_resources=tool_resources,
    )
    return AzureAIAgent(client=client, definition=agent_def)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_message', methods=['POST'])
async def send_message():
    """Handle user messages and fetch AI responses."""
    user_message = request.json.get('message')
    creds = DefaultAzureCredential()
    client = AzureAIAgent.create_client(
        credential=creds,
        conn_str=AzureAIAgentSettings.create().project_connection_string.get_secret_value()
    )
    
    thread = await client.agents.create_thread()
    event_log.append({"event": "Thread Created", "details": f"New thread ID: {thread.id}"})
    
    # Create Routing Coordinator
    routing_instructions = (
            "You are a routing coordinator. When you receive a user's query, analyze it and output a JSON object "
            "that maps agent names to the sub-query they should answer. For example: "
            "{\"movieAgent\": \"Query for movies...\", \"docuAgent\": \"Query for Microsoft licensing products...\"}. "
            "Only include keys for agents that are relevant to the query and do not include any additional text."
        )
    
    routing_agent = await create_agent(client, "CoordinatorRouting", routing_instructions)
    
    # Create Synthesis Coordinator
    synthesis_instructions = (
            "You are a synthesis coordinator. Given the original user query and the responses from the delegated agents, "
            "synthesize a final, coherent, and concise answer for the user. Organize the answer into appropriate sections. "
            "Do not include any JSON or extra markup."
        )
    
    synthesis_agent = await create_agent(client, "CoordinatorSynthesis",synthesis_instructions)
    
    # Create docuAgent (Azure AI Search)
    # Extract the list of connections available in the project client
    connections = await client.connections._list_connections()
    conn_list = connections["value"]
    conn_id = ""

    # From the previous list, find the connection with type Azure AI Search and store its ID in the conn_id variable
    for conn in conn_list:
        metadata = conn["properties"].get("metadata", {})
        if metadata.get("type", "").upper() == "AZURE_AI_SEARCH":
            conn_id = conn["id"]
            break
    
    # Get the index name from the environment variable
    index_id= os.environ.get("AZURE_SEARCH_INDEX_NAME") 
    
    if not conn_id:
        print("No CognitiveSearch connection found. Using empty connection ID.")

    # Instantiate the AzureAISearchTool with the connection ID and index name from the environment variable
        
    docu_instructions = (
            "You are an expert on Microsoft Licensing products. You are integrated with Azure AI Search via the 'azure_search' tool. "
            "Use this tool to retrieve detailed and concise information on various Microsoft products such a windows server, Dynamics, PowerPlatform among others. "
            "If you don´t find any relevant information in the aisearch, please answer with 'I could not find any content for you, sorry.'."
        )
    
    ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name=index_id)      
    docu_agent = await create_agent(
        client, 
        "docuAgent",
        docu_instructions,
        tools=ai_search.definitions,
        tool_resources=ai_search.resources
    )
    
    # Create movieAgent (Cinemas API)
    movie_instructions = (
            "You are an expert in cinema information. Use the provided API tool to retrieve current movies, showtimes, and cinema details." 
            "Respond only with relevant movie or cinema information. Indicate the total number of movies available."
            "Reply only with the first 10 in alphabetical order of the title."
            "If asked about a specific title, search for it in the complete list of movies and use the movie ID to call the endpoint that provides the rest of the information."
        )
    cinemas_api_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "aux", "cinemasapi.json")
    with open(cinemas_api_path, "r") as f:
        cinemas_api_spec = json.load(f)
    auth = OpenApiAnonymousAuthDetails()  # Adjust auth as necessary
    openapi_cinemas_tool = OpenApiTool(
        name="cinemasapi", 
        spec=cinemas_api_spec, 
        description="Access the cinemas API to retrieve movie listings, showtimes, and cinema details.",
        auth=auth)
    
    movie_agent = await create_agent(
        client, "movieAgent",
        movie_instructions,
        tools=openapi_cinemas_tool.definitions
    )
    
    # Step 7: Routing
    await routing_agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=user_message))
    routing_output = ""
    async for content in routing_agent.invoke(thread_id=thread.id):
        routing_output += content.content
    event_log.append({"event": "Routing Decision", "details": routing_output})
    
    routing_decision = json.loads(routing_output)
    agent_responses = {}
    
 # Step 8: Delegation
    for agent_name, subquery in routing_decision.items():
        agent = docu_agent if agent_name == "docuAgent" else movie_agent
        await agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=subquery))
        agent_response = ""
        async for content in agent.invoke(thread_id=thread.id):
            agent_response += content.content
        agent_responses[agent_name] = agent_response

# Step 9: Synthesis
    synthesis_input = json.dumps({"user_query": user_message, "agent_responses": agent_responses}, indent=2)
    await synthesis_agent.add_chat_message(thread_id=thread.id, message=ChatMessageContent(role=AuthorRole.USER, content=synthesis_input))
    final_response = ""
    async for content in synthesis_agent.invoke(thread_id=thread.id):
        final_response += content.content

    # Guarda en el historial cada respuesta con el nombre del agente
    conversation_history.append({"role": "User", "message": user_message})
    for agent_name, response in agent_responses.items():
        conversation_history.append({"role": f"Agent {agent_name}", "message": response})
    # También puedes guardar la respuesta final del coordinador de síntesis si lo deseas:
    conversation_history.append({"role": "Agent CoordinatorSynthesis", "message": final_response})
    
    await client.agents.delete_agent(routing_agent.id)
    await client.agents.delete_agent(synthesis_agent.id)
    await client.agents.delete_agent(docu_agent.id)
    await client.agents.delete_agent(movie_agent.id)
    
    return jsonify({"response": final_response})

@app.route('/get_history', methods=['GET'])
def get_history():
    return jsonify(conversation_history)

@app.route('/get_events', methods=['GET'])
def get_events():
    return jsonify(event_log)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)