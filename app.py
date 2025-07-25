import chainlit as cl
from chainlit import on_chat_start
from agent_with_abbr import get_mysql_agent_response, memory
import asyncio

@on_chat_start
async def start():
    await cl.Message(content="Hi! I'm your AI assistant. You can ask me about the schedule of cruise ships in Santorini! What can I help you with?").send()

@cl.on_message
async def main(message: cl.Message):
    try:
        
        # msg = cl.Message(content="Let me think...")
        # await msg.send()
        
        # Show an intermediate step
        async with cl.Step(name="Thinking", type="custom") as step:
            step.stream_token("Thinking...")
            result = await asyncio.to_thread(get_mysql_agent_response, message.content, memory)

        # Format result
        if isinstance(result, dict):
            response = result.get("output", "No output found")
        else:
            response = str(result)

        # Final user-facing message
        await cl.Message(content=response).send()

    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()
