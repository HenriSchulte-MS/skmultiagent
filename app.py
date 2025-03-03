import asyncio
import json
import os

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.models import AzureAISearchTool, OpenApiAnonymousAuthDetails, OpenApiTool

from semantic_kernel.agents.azure_ai import AzureAIAgent, AzureAIAgentSettings
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def main():
    # Load Azure AI Agent settings
    ai_agent_settings = AzureAIAgentSettings.create()
    
    async with DefaultAzureCredential() as creds, \
         AzureAIAgent.create_client(
            credential=creds,
            conn_str=ai_agent_settings.project_connection_string.get_secret_value()
         ) as client:

        # Create a single thread for the conversation
        thread = await client.agents.create_thread()

        # ----------------------------
        # 1. Create the Routing Coordinator Agent
        # ----------------------------
        routing_instructions = (
            "You are a routing coordinator. When you receive a user's query, analyze it and output a JSON object "
            "that maps agent names to the sub-query they should answer. For example: "
            "{\"movieAgent\": \"Query for movies...\", \"docuAgent\": \"Query for Microsoft licensing products...\"}. "
            "Only include keys for agents that are relevant to the query and do not include any additional text."
        )
        coordinator_routing_def = await client.agents.create_agent(
            model=ai_agent_settings.model_deployment_name,
            name="CoordinatorRouting",
            instructions=routing_instructions
        )
        coordinator_routing = AzureAIAgent(client=client, definition=coordinator_routing_def)

        # ----------------------------
        # 2. Create the Synthesis Coordinator Agent
        # ----------------------------
        synthesis_instructions = (
            "You are a synthesis coordinator. Given the original user query and the responses from the delegated agents, "
            "synthesize a final, coherent, and concise answer for the user. Organize the answer into appropriate sections. "
            "Do not include any JSON or extra markup."
        )
        coordinator_synthesis_def = await client.agents.create_agent(
            model=ai_agent_settings.model_deployment_name,
            name="CoordinatorSynthesis",
            instructions=synthesis_instructions
        )
        coordinator_synthesis = AzureAIAgent(client=client, definition=coordinator_synthesis_def)

        # ----------------------------
        # 3. Use the existing client to get the Azure AI Search connection info
        # ----------------------------
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
        ai_search = AzureAISearchTool(index_connection_id=conn_id, index_name=index_id)

        # ----------------------------
        # 4. Create the docuAgent (Microsoft Partners Incentives) with Azure AI Search integration
        # ----------------------------
        docu_instructions = (
            "You are an expert on Microsoft Licensing products. You are integrated with Azure AI Search via the 'azure_search' tool. "
            "Use this tool to retrieve detailed and concise information on various Microsoft products such a windows server, Dynamics, PowerPlatform among others. "
            "If you don´t find any relevant information in the aisearch, please answer with 'I could not find any content for you, sorry.'."
        )
        docu_def = await client.agents.create_agent(
            model=ai_agent_settings.model_deployment_name,
            name="docuAgent",
            instructions=docu_instructions,
            tools=ai_search.definitions,
            tool_resources=ai_search.resources,
        )
        docu_agent = AzureAIAgent(client=client, definition=docu_def)

        # ----------------------------
        # 5. Create the movieAgent with API integration (Cinemas API)
        # ----------------------------
        # Load the cinemasapi.json file from the "aux" folder
        cinemas_api_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "aux", "cinemasapi.json")
        with open(cinemas_api_path, "r") as f:
            cinemas_api_spec = json.load(f)
        auth = OpenApiAnonymousAuthDetails()  # Adjust auth as necessary
        openapi_cinemas_tool = OpenApiTool(
            name="cinemasapi",
            spec=cinemas_api_spec,
            description="Access the cinemas API to retrieve movie listings, showtimes, and cinema details.",
            auth=auth
        )
        movie_instructions = (
            "You are an expert in cinema information. Use the provided API tool to retrieve current movies, showtimes, and cinema details." 
            "Respond only with relevant movie or cinema information. Indicate the total number of movies available."
            "Reply only with the first 10 in alphabetical order of the title."
            "If asked about a specific title, search for it in the complete list of movies and use the movie ID to call the endpoint that provides the rest of the information."
        )
        movie_def = await client.agents.create_agent(
            model=ai_agent_settings.model_deployment_name,
            name="movieAgent",
            instructions=movie_instructions,
            tools=openapi_cinemas_tool.definitions  # integrate the API tool
        )
        movie_agent = AzureAIAgent(client=client, definition=movie_def)

        # ----------------------------
        # 6. Receive User Input (free-form)
        # ----------------------------
        user_query = (
            "Hello, I'd like to know what movies are showing this week and also give me some information about Microsoft PowerPlatform licencising."
        )
        print("User Input:")
        print(user_query)
        print("-" * 60)

        # ----------------------------
        # 7. Routing Phase: Coordinator determines delegation
        # ----------------------------
        await coordinator_routing.add_chat_message(
            thread_id=thread.id,
            message=ChatMessageContent(role=AuthorRole.USER, content=user_query)
        )
        routing_output = ""
        async for content in coordinator_routing.invoke(thread_id=thread.id):
            routing_output += content.content

        print("Coordinator Routing Output:")
        print(routing_output)
        print("-" * 60)

        # Parse the routing output as JSON
        try:
            routing_decision = json.loads(routing_output)
        except Exception as e:
            print("Error parsing routing output as JSON:", e)
            routing_decision = {}

        # ----------------------------
        # 8. Delegation Phase: Call specialized agents based on routing decision
        # ----------------------------
        agent_responses = {}

        if "movieAgent" in routing_decision:
            movie_subquery = routing_decision["movieAgent"]
            await movie_agent.add_chat_message(
                thread_id=thread.id,
                message=ChatMessageContent(role=AuthorRole.USER, content=movie_subquery)
            )
            movie_response = ""
            async for content in movie_agent.invoke(thread_id=thread.id):
                movie_response += content.content
            agent_responses["movieAgent"] = movie_response

        if "docuAgent" in routing_decision:
            docu_subquery = routing_decision["docuAgent"]
            await docu_agent.add_chat_message(
                thread_id=thread.id,
                message=ChatMessageContent(role=AuthorRole.USER, content=docu_subquery)
            )
            docu_response = ""
            async for content in docu_agent.invoke(thread_id=thread.id):
                docu_response += content.content
            agent_responses["docuAgent"] = docu_response

        # ----------------------------
        # 9. Synthesis Phase: Coordinator synthesizes the final answer
        # ----------------------------
        synthesis_input = {
            "user_query": user_query,
            "agent_responses": agent_responses
        }
        synthesis_message = json.dumps(synthesis_input, indent=2)
        await coordinator_synthesis.add_chat_message(
            thread_id=thread.id,
            message=ChatMessageContent(role=AuthorRole.USER, content=synthesis_message)
        )
        final_response = ""
        async for content in coordinator_synthesis.invoke(thread_id=thread.id):
            final_response += content.content

        print("Final Response from Coordinator:")
        print(final_response)

        # ----------------------------
        # 10. Cleanup: Delete the thread and agents to free resources
        # ----------------------------
        #await client.agents.delete_thread(thread.id)
        await client.agents.delete_agent(coordinator_routing.id)
        await client.agents.delete_agent(coordinator_synthesis.id)
        await client.agents.delete_agent(docu_agent.id)
        await client.agents.delete_agent(movie_agent.id)

if __name__ == "__main__":
    asyncio.run(main())
