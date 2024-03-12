from llama_index.core import SummaryIndex
from llama_index.core import VectorStoreIndex
import os
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter, FilterCondition, MetadataFilter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings
import qdrant_client
from qdrant_client.http.models import MatchValue, FieldCondition, Filter
from llama_index.core import StorageContext
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core.llms import ChatMessage

from llama_index.readers.web import TrafilaturaWebReader
from trafilatura.spider import focused_crawler
import time
import requests
from urllib.parse import urlparse
from llama_index.core import SimpleDirectoryReader
from llama_index.llms.ollama import Ollama

from typing import List
from fastapi import HTTPException


def get_llm(name = "openai", settings = None):
    if not settings:
        raise HTTPException(status_code=400, detail="Please provide settings")
    # we use the OpenAIEmbedding model for all LLMs
    #Settings.embed_model = OpenAIEmbedding()
    Settings.embed_model = HuggingFaceEmbedding(
        model_name="BAAI/bge-small-en-v1.5"
    )

    if name == "openai":
        llm = AzureOpenAI(
            engine=settings.MODEL_DEPLOYMENT_NAME,
            model="gpt-35-turbo",
            temperature=0.0,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION)
    # all other models we get from Ollama
    else:
        llm = Ollama(
            model=name, 
            request_timeout=180.0, 
            base_url=settings.OLLAMA_BASE_URL, 
            temperature=0.0)
    
    Settings.llm = llm
    return llm, Settings.embed_model


def get_fetch_urls(urls, skip_reading = False):
    fetch_list = []
    # BUG: OR condition is not working 
    # https://github.com/run-llama/llama_index/issues?q=is%3Aissue+is%3Aopen+FilterCondition.OR
    # hence we have to turn crawling off since we can't get the docs later
    """
    for url in urls:
        to_visit, known_urls = focused_crawler(url, max_seen_urls=10, max_known_urls=100000)
        print(f"visit ${to_visit}   known ${known_urls}")
        # this is a workaround for now because to_visit list seems empty so we grab some from known
        if not to_visit:
            for url in known_urls:
                response = requests.head(url)
                if response.status_code == 200: fetch_list.append(url)
        fetch_list = fetch_list + list(to_visit)
        # we want to make sure the original URL is definitely in the list
        if not url in fetch_list:
            print(fetch_list)
            print("adding %s to the list" % url)
            fetch_list.insert(0, url)
    # if we skip reading we know we already have the parent in the vector db
    # we just needed the other URLS as query keys
    if skip_reading:
        return fetch_list
    """
    fetch_list.append(urls[0][1])
    print(f"fetch_list: {fetch_list}")
    documents = []
    reader = TrafilaturaWebReader()
    td= None
    for url in fetch_list[0:10]:
        try:
            td = reader.load_data([url])
        except:
            print("error with %s" % url)
        documents = documents + td
    print("fetched a total of %s documents" % len(documents))    
    return documents


def _get_file_destination(url, type, askey = False):
    path = urlparse(url).path
    name = path.split("/")[-1]
    if not askey:
        return os.path.join(".", type, name)
    else:
        return os.path.join(type, name)


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
            destination = _get_file_destination(furl, type)
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
            # some pdfs apparently have text/html content type
            if url.endswith('.pdf'):
                print(f'URL {url} points to a PDF file.')
                fetch_urls.append(['pdf', url])
            else:
                print(f"URL {url} points to a web page.")
                fetch_urls.append(['web', url])
        else:
            print('This URL points to %s of content.' % content_type)
    return fetch_urls

              
def ingest_urls(url_types):
    print("Categorized URLs as follows: %s" % url_types)

    download_urls = [url for url in url_types if url[0] != "web"]
    if download_urls:      
        print("Downloading the following urls: %s" % download_urls)
        return get_download_files(download_urls)

    fetch_urls = [url for url in url_types if url[0] == "web"]
    if fetch_urls:
        print("Fetching the following urls: %s" % fetch_urls)
        return get_fetch_urls(fetch_urls)
    return None


def get_dbclient(settings):
    client = qdrant_client.QdrantClient(
        url=settings.QDRANT_ENDPOINT
    )
    return client



def is_vector_in_db(qclient, collection_name, key, value):
    print(f"Checking if {key} with value {value} is in the vector store")
    try:
        result = qclient.scroll(collection_name=collection_name,
                            scroll_filter = Filter(must=[
                                            FieldCondition(key=key, match=MatchValue(value=value))
                                                        ]))
        return result[0]
    except:
        return None


def get_preseeded_query_engine(type, urls, index):
    filters = []
    print(f"Getting preseeded query engine for {type} with urls {urls}")
    if type == "web":
        for url in urls:
            filter = MetadataFilter(key="document_id", value=url)
            filters.append(filter)
    else:
        for url in urls:
            file_location =_get_file_destination(url, type, askey=True)
            filter = MetadataFilter(key="file_path", value=file_location)
            filters.append(filter)
    query_engine = index.as_query_engine(
        vector_store_query_mode="default",
        filters=MetadataFilters(filters=filters))
    return query_engine


def get_query_engine(urls, dbclient, collection_name, embed_model = None):
    # see if the urls are already in the vector store
    filter = None
    url_and_types = determine_types(urls)
    vector_store = QdrantVectorStore(client=dbclient, collection_name=collection_name)
    index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
    
    if url_and_types:
        type = url_and_types[0][0]
        urls = [url_and_types[0][1]]
        # we query qdrant for metadata because with query_engine we don't know
        # if we have documents until we inference with the llm
        in_db = None
        if type == "web":
            in_db = is_vector_in_db(dbclient, collection_name, "document_id", urls[0])
        elif type == "csv" or type == "pdf":
            in_db = is_vector_in_db(dbclient, collection_name, "file_path", _get_file_destination(urls[0], type, askey=True))
        if in_db:
            print(f"Found documents in the vector store for {type} with urls {urls}")
            return get_preseeded_query_engine(type, urls, index)

        # we didn't find anything in the vector db so we get it anew
        docs = ingest_urls(url_and_types)
        start = time.time()
        vector_store = QdrantVectorStore(client=dbclient, collection_name=collection_name)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents(docs, embed_model=embed_model, storage_context=storage_context)
        end = time.time()
        exec_time = end - start
        print(f"Indexing/embedding took {exec_time:.1f} seconds")
        return index.as_query_engine()

