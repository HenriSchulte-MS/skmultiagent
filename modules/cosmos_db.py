import os
import asyncio
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, PartitionKey

# Load environment variables from the .env file
load_dotenv()

COSMOS_ENDPOINT = os.environ.get("COSMOSDB_ENDPOINT")
COSMOS_KEY = os.environ.get("COSMOSDB_KEY")
DATABASE_NAME = os.environ.get("COSMOSDB_DATABASE")
CONTAINER_NAME = os.environ.get("COSMOSDB_CONTAINER")

# Initialize the client, database, and container.
credential = DefaultAzureCredential()
client = CosmosClient(COSMOS_ENDPOINT, credential)
database = client.create_database_if_not_exists(id=DATABASE_NAME)
container = database.create_container_if_not_exists(
    id=CONTAINER_NAME, 
    partition_key=PartitionKey(path="/id")
)

async def get_session(session_id: str):
    """
    Retrieve the session from CosmosDB using session_id.
    """
    def sync_get():
        query = "SELECT * FROM c WHERE c.id=@session_id"
        parameters = [{"name": "@session_id", "value": session_id}]
        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        if items:
            return items[0]
        return None
    return await asyncio.to_thread(sync_get)

async def save_session(session_id: str, session_data: dict):
    """
    Save session information in CosmosDB.
    Store a document with the necessary IDs.
    """
    document = {
        "id": session_id,
        "thread_id": session_data["thread"].id,
        "routing_agent_id": session_data["routing_agent"].id,
        "synthesis_agent_id": session_data["synthesis_agent"].id,
        "docu_agent_id": session_data["docu_agent"].id if session_data["docu_agent"] else None,
        "movie_agent_id": session_data["movie_agent"].id if session_data["movie_agent"] else None,
    }
    def sync_save():
        container.upsert_item(document)
    await asyncio.to_thread(sync_save)

async def delete_session(session_id: str):
    """
    Delete the session stored in CosmosDB using session_id.
    """
    def sync_delete():
        container.delete_item(item=session_id, partition_key=session_id)
    await asyncio.to_thread(sync_delete)

async def get_all_conversations():
    """
    Retrieve all conversations stored in CosmosDB.
    """
    def sync_get_all():
        query = "SELECT c.id, c.name FROM c"
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        return items
    return await asyncio.to_thread(sync_get_all)

async def get_conversation(conversation_id: str):
    """
    Retrieve a specific conversation from CosmosDB using conversation_id.
    """
    def sync_get():
        query = "SELECT * FROM c WHERE c.id=@conversation_id"
        parameters = [{"name": "@conversation_id", "value": conversation_id}]
        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        if items:
            return items[0]
        return None
    return await asyncio.to_thread(sync_get)

async def save_conversation(conversation_id: str, conversation_data: dict):
    """
    Save a conversation in CosmosDB.
    """
    # Use the first 20 characters of the first message as the name if not provided
    name = conversation_data.get("name")
    if not name and conversation_data.get("messages"):
        first_message = conversation_data["messages"][0].get("message", "")
        name = first_message[:25] if first_message else "Unnamed Conversation"
    document = {
        "id": conversation_id,
        "name": name or "Unnamed Conversation",
        "messages": conversation_data.get("messages", [])
    }
    def sync_save():
        container.upsert_item(document)
    await asyncio.to_thread(sync_save)