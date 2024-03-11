import gradio as gr
import requests
import os

model_endpoint = os.getenv('BACKEND_URL', 'http://localhost:8080')

def ask_question(question, model, urls):
    requests.post(f"{model_endpoint}/set_llm/{model}")
    if urls:
        urls_list = [url.strip() for url in urls.split(',')]
    else:
        urls_list = []

    api_payload = {
        "question": question,
        "urls": urls_list
    }
    response = requests.post("%s/query_chat" % model_endpoint, json=api_payload)
    res = response.json()
    # llm response is nested, other nodes are source_nodes, template
    answer = res.get('response', "Error: No response found")
    if isinstance(answer, dict):
        answer = answer.get("response", "Error: No response found")
    time = res.get('time_taken', "Error: No time found")
    return answer, time


def get_model_info():
    response = requests.get("%s/info" % model_endpoint)
    info = response.json()
    return info


def list_llm():
    response = requests.get(f"{model_endpoint}/list_llm")
    models = response.json()
    return models


question_input = gr.Textbox("What would you like to know?", label="Ask a question!", lines=1)
prompt_output = gr.Textbox("Here's my answer!", label="Query Result", lines=10)
time_output = gr.Textbox("0.0", label="Inference Time (seconds)", lines=1)
model_selection = gr.Radio(choices=list_llm(), label="Model", value="openai")
url_input = gr.Textbox(lines=1, placeholder="accepted types are CSV, web, PDF", label="Ingest URL")

iface = gr.Interface(
    fn=ask_question,
    inputs=[question_input, model_selection, url_input],
    outputs=[prompt_output, time_output],
    title="Multi-LLM Chat",
    description="Pick your model, ask a question, and get an answer!",
    theme=gr.themes.Soft(),
    allow_flagging="never",
    css='footer{display:none !important}')
iface.launch(inline=True, share=False, server_name="0.0.0.0", server_port=8088)

# description="Type a question and get an answer from the LLM. " + str(get_model_info())