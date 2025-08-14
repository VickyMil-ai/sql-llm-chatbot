import gradio as gr
from agent_impr import get_mysql_agent_response
from langchain.memory import ConversationBufferMemory

# Step 1: Append user message immediately
def user(user_input, history):
    if history is None:
        history = []
    history.append({"role": "user", "content": user_input})
    return history, ""  # update chatbot and clear input box

# Step 2: Generate assistant response
def bot(history, memory):
    user_input = history[-1]["content"]

    if memory is None:
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    response = get_mysql_agent_response(user_input, memory)

    if isinstance(response, tuple):
        response = response[0]
    elif isinstance(response, dict):
        response = response.get("output", str(response))

    history.append({"role": "assistant", "content": response})
    return history, memory

with gr.Blocks(theme="soft") as demo:
    gr.Markdown("## Santorini Cruise Chatbot")
    # gr.Markdown("Ask me anything about cruise ship schedules in Santorini!")

    chatbot = gr.Chatbot(
        type='messages',
        show_copy_button=True,
        placeholder="Ask me anything about cruise ship schedules in Santorini!",
        height=600
    )
    state = gr.State([])  # history
    memory_state = gr.State(None)  # ConversationBufferMemory

    with gr.Row():
        txt = gr.Textbox(show_label=False, placeholder="Ask about cruise schedules...", scale=4)
        send_btn = gr.Button("Send", scale=1)

    with gr.Row():
        gr.Examples(
            examples=[
                "Is VIKING SATURN on 29th of December?",
                "How many ships are scheduled tomorrow?"
            ],
            inputs=txt
        )
    
    send_btn.click(user, [txt, state], [chatbot, txt]) \
            .then(bot, [state, memory_state], [chatbot, memory_state])

    txt.submit(user, [txt, state], [chatbot, txt]) \
        .then(bot, [state, memory_state], [chatbot, memory_state])

if __name__ == "__main__":
    demo.launch(share=True) #share=true for public link
