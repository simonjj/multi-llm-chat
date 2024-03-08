from llama_index.core import SummaryIndex

# from IPython.display import Markdown, display
import os
import time 


from llama_index.core.llms import ChatMessage


import requests


from dotenv import dotenv_values
from fastapi import FastAPI
from pydantic_settings import BaseSettings

from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

import utils

# download and install dependencies
#OllamaQueryEnginePack = download_llama_pack(
#    "OllamaQueryEnginePack", "./ollama_pack"
#)

class Settings(BaseSettings):
    MODEL_DEPLOYMENT_NAME: str = "None"
    AZURE_OPENAI_ENDPOINT: str = "None"
    OPENAI_API_KEY: str = "None"
    AZURE_OPENAI_API_VERSION: str = "None"
    OLLAMA_BASE_URL: str = "None"

    # ignore any other env variables
    class Config:
        extra = "ignore"


app = FastAPI()

@app.on_event("startup")
async def startup_event():
    mysettings = Settings()
    config = {
        **dotenv_values(".env"),  # load shared development variables
        **dotenv_values(".env.secret"),  # load sensitive variables
        **os.environ,  # override loaded values with environment variables
    }
    print("Using the following settings: %s" % config)
    mysettings = Settings(**config)
    app.state.settings = mysettings


@app.get("/list_llm")
async def list_llm():
    #return {"openai", "llama2", "mistral", "phi", "mixtral"}
     return {"openai", "llama2", "phi"}


@app.post("/set_llm/{name}")
async def set_llm(name: str):
    llm = utils.get_llm(name, app.state.settings)
    #print(dir(llm))
    print("Model %s loaded" % llm.model)
    app.state.llm = llm
    return {"message": f"Set llm to {name}"}


class Query(BaseModel):
    question: str
    urls: List[HttpUrl]


@app.post("/query_chat")
async def query_chat(query: Query):
    # Check if llm instance exists
    if not hasattr(app.state, 'llm'):
        raise HTTPException(status_code=400, detail="Please choose an LLM")
    
    cache = False
    if hasattr(app.state, 'urls') and query.urls == app.state.urls:
            print("Reusing documents...")
            docs = app.state.docs
            cache = True
    if not cache:
            if len(query.urls) != 0:
                print("Fetching documents...")
                urls = [str(u) for u in query.urls]
                docs = utils.ingest_urls(urls)
                app.state.docs = docs
                app.state.urls = query.urls
            else:
                 print("No URLs provided... just using LLM base knowledge...")
                 docs = None
        

    
    llm = app.state.llm
    start, end = 0, 0
    if docs:
        print("Retrieved documents... total of %s" % len(docs))
        index = SummaryIndex.from_documents(docs)
        print("Index created... querying LLM...")
        query_engine = index.as_query_engine(llm, streaming=False)
        start = time.time()
        response = query_engine.query(query.question)
        end = time.time()
    else:
        print("No documents to index... querying LLM...")
        start = time.time()
        response = llm.chat([ChatMessage(role="user", content=query.question)])
        response = {"response" : response.message.content}
        end = time.time()
    print("Query complete...")
    exec_time = end - start
    print(f"The query took {exec_time:.1f} seconds to execute.")
    print(response)
    return {"response": response, "time_taken": f"{exec_time:.1f}"}

