from llama_index.core import SummaryIndex

# from IPython.display import Markdown, display
import os
import time 
import json

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
    QDRANT_ENDPOINT: str = "None"
    QDRANT_COLLECTION: str = "None"

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
    print("Using the following settings:")
    mysettings = Settings(**config)
    print("+------------------------------------+")
    print("MODEL_DEPLOYMENT_NAME: %s" % mysettings.MODEL_DEPLOYMENT_NAME)
    print("AZURE_OPENAI_ENDPOINT: %s" % mysettings.AZURE_OPENAI_ENDPOINT)
    print("OPENAI_API_KEY: ....%s" % mysettings.OPENAI_API_KEY[-5:])
    print("AZURE_OPENAI_API_VERSION: %s" % mysettings.AZURE_OPENAI_API_VERSION)
    print("OLLAMA_BASE_URL: %s" % mysettings.OLLAMA_BASE_URL)
    print("QDRANT_ENDPOINT: %s" % mysettings.QDRANT_ENDPOINT)
    print("QDRANT_COLLECTION: %s" % mysettings.QDRANT_COLLECTION)
    print("+------------------------------------+")
    app.state.settings = mysettings


@app.get("/list_llm")
async def list_llm():
    response = requests.get(f"{app.state.settings.OLLAMA_BASE_URL}/api/tags")
    model_list = []
    if response.status_code == 200:
        models = response.json()['models']
        for model in models:
            model_list.append(model['name'].replace(":latest", ""))
        print("Found the following Ollama models: %s" % model_list)
        # always support openai
        model_list.append("openai")
        return model_list
    else:
        raise HTTPException(status_code=400, detail="Could not fetch LLM list")


@app.post("/set_llm/{name}")
async def set_llm(name: str):
    llm, embed_model = utils.get_llm(name, app.state.settings)
    #print(dir(llm))
    print("Model %s loaded" % llm.model)
    app.state.llm = llm
    app.state.embed_model = embed_model
    return {"message": f"Set llm to {name}"}


class Query(BaseModel):
    question: str
    urls: List[HttpUrl]


@app.post("/query_chat")
async def query_chat(query: Query):
    # Check if llm instance exists
    if not hasattr(app.state, 'llm'):
        raise HTTPException(status_code=400, detail="Please choose an LLM")
    end, start = 0, 0
    response = "Error: No response found"
    if query.urls:
        # we only support one URL for now because otherwise merging the fecthed documents is harder
        urls = [str(u) for u in query.urls][:1]
        app.state.dbclient = utils.get_dbclient(app.state.settings)
        query_engine = utils.get_query_engine(urls, app.state.dbclient, app.state.settings.QDRANT_COLLECTION, app.state.embed_model)
        start = time.time()
        print("Querying LLM...")
        response = query_engine.query(query.question)
        end = time.time()
    else:
        llm = app.state.llm
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

