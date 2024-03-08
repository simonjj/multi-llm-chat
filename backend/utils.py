from llama_index.core import SummaryIndex
import os

from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core.llms import ChatMessage

from llama_index.readers.web import TrafilaturaWebReader
from trafilatura.spider import focused_crawler

import requests
from urllib.parse import urlparse
from llama_index.core import SimpleDirectoryReader
from llama_index.llms.ollama import Ollama

from typing import List
from fastapi import HTTPException





def get_llm(name = "openai", settings = None):
    if not settings:
        raise HTTPException(status_code=400, detail="Please provide settings")
    if name == "openai":
        llm = AzureOpenAI(
            engine=settings.MODEL_DEPLOYMENT_NAME,
            model="gpt-35-turbo",
            temperature=0.0,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION)

    elif name == "llama2":
        llm = Ollama(
            model="llama2", 
            request_timeout=180.0, 
            base_url=settings.OLLAMA_BASE_URL, 
            temperature=0.0)

    elif name == "mistral":
        llm = Ollama(
            model="mistral", 
            request_timeout=180.0, 
            base_url=settings.OLLAMA_BASE_URL, 
            temperature=0.0)
        
    elif name == "mixtral":
        llm = Ollama(
            model="mistral", 
            request_timeout=180.0, 
            base_url=settings.OLLAMA_BASE_URL, 
            temperature=0.0)
        
    elif name == "phi":
        llm = Ollama(
            model="phi", 
            request_timeout=180.0, 
            base_url=settings.OLLAMA_BASE_URL, 
            temperature=0.0)
    else:
        print("ERROR: Print model %s is not supported" % name)
    return llm


def get_fetch_urls(urls):
    fetch_list = []
    for url in urls:
        to_visit, known_urls = focused_crawler(url[1], max_seen_urls=10, max_known_urls=100000)
        print(f"visit ${to_visit}   known ${known_urls}")
        # this is a workaround for now because to_visit list seems empty so we grab some from known
        if not to_visit:
            for url in known_urls:
                response = requests.head(url)
                if response.status_code == 200: fetch_list.append(url)
        fetch_list = fetch_list + list(to_visit)

    documents = []
    reader = TrafilaturaWebReader()
    for url in fetch_list[0:11]:
        print("fetching %s" % url)
        try:
            td = reader.load_data([url])
        except:
            print("error with %s" % url)
        documents = documents + td
    print("fetched a total of %s documents" % len(documents))    
    return documents


def get_download_files(urls):
    for dir in ["pdf", "csv"]:
        if not os.path.exists(os.path.join(".", dir)):
            os.makedirs(dir)
            
    all_files = []
    for url in urls:
        type = url[0]
        furl = url[1]
        response = requests.get(furl)
        if response.status_code == 200:
            path = urlparse(furl).path
            name = path.split("/")[-1]
            destination = os.path.join(".", type, name)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT)
            with open(fd, 'wb') as output_file:
                output_file.write(response.content)
                all_files.append(destination)
        else:
            print(f"ERROR: respone status was {response.status}")
    if all_files:
        reader = SimpleDirectoryReader(input_files=all_files, num_files_limit=10)    
        return reader.load_data()
    else:
        return None

                       
def determine_types(urls):
    def _get_content_type(c_url):
        response = requests.head(c_url)
        return response.headers.get('Content-Type')
    fetch_urls = []
    for url in urls:
        content_type = _get_content_type(url)
        if 'text/csv' in content_type:
            print(f'URL {url} points to a CSV file.')
            fetch_urls.append(['csv', url])
        elif 'application/pdf' in content_type:
            print(f'URL {url} points to a PDF file.')
            fetch_urls.append(['pdf', url])
        elif 'text/html' in content_type:
            print(f"URL {url} points to a web page.")
            fetch_urls.append(['web', url])
        else:
            print('This URL points to %s of content.' % content_type)
    return fetch_urls

              
def ingest_urls(urls):
    url_types = determine_types(urls)
    print("Categorized URLs as follows: %s" % url_types)
    download_urls = [url for url in url_types if url[0] != "web"]      
    print("Downloading the following urls: %s" % download_urls)
    download_docs = get_download_files(download_urls)
    fetch_urls = [url for url in url_types if url[0] == "web"]
    print("Fetching the following urls: %s" % fetch_urls)
    download_urls = get_fetch_urls(fetch_urls)
    if download_docs and download_urls:
        return download_docs + download_urls
    elif download_docs:
        return download_docs
    elif download_urls:
        return download_urls
    else:
        return None


def prep_context(urls, prompt=None, llm = None):
    messages = []
    if prompt:
        initial_prompt = ChatMessage(role="system", content=prompt)
        messages.append(initial_prompt)

    docs = ingest_urls(urls)
    query_engine = None
    if docs:
        index = SummaryIndex.from_documents(docs)
        query_engine = index.as_query_engine(llm, streaming=True)
        return query_engine, messages
    else:
        return None, messages
    


def chat_with_data(query_engine, messages, llm):
    message = None
    while(True):
        print("=" * 15)
        message = input("  >>> ")
        if message == "exit":
            break
        messages.append(ChatMessage(role="user", content=message))
        response = None
        if not query_engine:
            print("Starting a regular chat...")
            response = llm.stream_chat(messages)
            answer = ""
            for r in response:
                seg = r.delta
                print(seg, end="")
                answer += seg
        else:
            print("Starting a Q&A chat...")
            response = query_engine.query(messages[-1].content)
            print(response)
            answer = response

        messages.append(ChatMessage(role="system", content=answer))


def main(urls, prompt = None):
    urls  = urls.split(",")
    print("prepping chat context...")
    query_engine, message_context = prep_context(urls, prompt)
    print("starting chat...")
    chat_with_data(query_engine, message_context)
    
                
