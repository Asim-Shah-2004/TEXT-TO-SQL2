import openai
import requests
from django.http import JsonResponse
import pymysql
from django.views.decorators.csrf import csrf_exempt
import pymysql.cursors
import chromadb
import time
from openai import RateLimitError
import json
from openai import OpenAI
import google.generativeai as genai
from pymongo import MongoClient
mongo_client = MongoClient('mongodb://localhost:27017/')
chat_db = mongo_client['chat_history']
history_collection = chat_db['history']


@csrf_exempt
def addDataSource(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        db_name = request.POST.get('db_name')
        db_host = request.POST.get('db_host')
        
        try:
            connection = pymysql.connect(host=db_host,
                                         user=username,
                                         password=password,
                                         db=db_name,
                                         cursorclass=pymysql.cursors.DictCursor)
            
            db = connection.cursor()
            
            schema_query = get_schema_query(db_name)
            db.execute(schema_query)
            schema_result = db.fetchall()
            
            relationship_query = get_relationship_query()
            db.execute(relationship_query)
            relationship_result = db.fetchall()
                
            connection.close()
            store_embeddings(schema_result, "schema_embeddings_MYSQL")
            store_embeddings(relationship_result, "relationship_embeddings_MYSQL")
            
            return JsonResponse({'success': True})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def get_schema_query(db_name):
    return f"""SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '{db_name}'  
    ORDER BY TABLE_NAME, ORDINAL_POSITION;"""

def get_relationship_query():
    return """SELECT 
  `TABLE_SCHEMA`,                          
  `TABLE_NAME`,                            
  `COLUMN_NAME`,                           
  `REFERENCED_TABLE_SCHEMA`,               
  `REFERENCED_TABLE_NAME`,                
  `REFERENCED_COLUMN_NAME`                
FROM
  `INFORMATION_SCHEMA`.`KEY_COLUMN_USAGE`  
WHERE
  `TABLE_SCHEMA` = SCHEMA()                
  AND `REFERENCED_TABLE_NAME` IS NOT NULL;"""

def store_embeddings(data, collection_name):
    texts = [" ".join([str(value) if value else "" for value in row.values()]) for row in data]
    chroma_client = chromadb.Client()
    collection = chroma_client.create_collection(name=collection_name)
    documents = []
    ids = []
    for i, text in enumerate(texts, start=1):
        documents.append(text)
        ids.append(str(i))
    collection.add(documents=documents, ids=ids)
    results = collection.query(
        query_texts=["Display the products that have not been featured in any orders. Include productCode, productName, and productLine."], # Chroma will embed this for you
        n_results=10 # how many results to return
    )
    print(results['documents'])

@csrf_exempt
def queryDataSource(request):
    if request.method == 'POST':
        query_text = request.POST.get('query')

        if not query_text:
            return JsonResponse({'error': 'Query text is required'}, status=400)
        
        try:
            chroma_client = chromadb.Client()
            collection1 = chroma_client.get_collection(name="schema_embeddings_MYSQL")
            
            results1 = collection1.query(
                query_texts=[query_text],
                n_results=10
            )
            
            collection2 = chroma_client.get_collection(name='relationship_embeddings_MYSQL')
            
            results2 = collection2.query(
                query_texts=[query_text],
                n_results=10
            )

            schema_context = str(results1['documents'])
            relationship_context = str(results2['documents'])
            
            context = f"""
                you are an expert MYSQL db developer. Below is the schema and 
                relationship for the same. I will ask you to write more sql queries on top of that.
                Make sure that you will not write any DDL or delete, update queries.
                All the queries has to be of type select. Dont execute these queries 
                just provide us the query . 
                
                Schema context:
                {schema_context}
                
                relationship context:
                {relationship_context}
                
                query:
                {query_text}
            """
            
            print(context)
            
            llm_endpoint = "http://localhost:11434/api/generate"
            headers = {'Content-Type': 'application/json'}
            payload = {
                'model': 'llama3',
                'prompt': context  
            }
    
            response = requests.post(llm_endpoint, headers=headers, data=json.dumps(payload))
            print(response.text)
            
            if response.status_code == 200:
                history_entry = {
                    'user_query': query_text,
                    'ai_response': response.text,
                    'timestamp': time.time()
                }
                history_collection.insert_one(history_entry)
                
                return JsonResponse({'response': response.text})
            else:
                return JsonResponse({'error': 'Unable to get response from the LLM.', 'details': response.text}, status=500)
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def querydatasourceOpenAi(request):
    if request.method == 'POST':
        query_text = request.POST.get('query')

        if not query_text:
            return JsonResponse({'error': 'Query text is required'}, status=400)
        
        try:
            chroma_client = chromadb.Client()
            collection1 = chroma_client.get_collection(name="schema_embeddings_MYSQL")
            
            results1 = collection1.query(
                query_texts=[query_text],
                n_results=10
            )
            
            collection2 = chroma_client.get_collection(name='relationship_embeddings_MYSQL')
            
            results2 = collection2.query(
                query_texts=[query_text],
                n_results=10
            )

            schema_context = str(results1['documents'])
            relationship_context = str(results2['documents'])
            
            context = f"""
                you are an expert MYSQL db developer. Below is the schema and 
                relationship for the same. I will ask you to write more sql queries on top of that.
                Make sure that you will not write any DDL or delete, update queries.
                All the queries has to be of type select. Dont execute these queries 
                just provide us the query . 
                
                Schema context:
                {schema_context}
                
                relationship context:
                {relationship_context}
                
                query:
                {query_text}
            """
            print(context)
            
            client = OpenAI(api_key=API_KEY)

            completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": query_text}
            ]
            )
            
            return JsonResponse({'response': completion.choices[0].message})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    
@csrf_exempt
def querydatasourceGemini(request):
    if request.method == 'POST':
        query_text = request.POST.get('query')

        
        if not query_text:
            return JsonResponse({'error': 'Query text is required'}, status=400)
        
        try:
            chroma_client = chromadb.Client()
            collection1 = chroma_client.get_collection(name="schema_embeddings_MYSQL")
            
            results1 = collection1.query(
                query_texts=[query_text],
                n_results=10
            )
            
            collection2 = chroma_client.get_collection(name='relationship_embeddings_MYSQL')
            
            results2 = collection2.query(
                query_texts=[query_text],
                n_results=10
            )

            schema_context = str(results1['documents'])
            relationship_context = str(results2['documents'])
            
            context = f"""
                you are an expert MYSQL db developer. Below is the schema and 
                relationship for the same. I will ask you to write more sql queries on top of that.
                Make sure that you will not write any DDL or delete, update queries.
                All the queries has to be of type select. Dont execute these queries 
                just provide us the query . 
                
                Schema context:
                {schema_context}
                
                relationship context:
                {relationship_context}
                
                query:
                {query_text}
            """
        
            print(context)
            genai.configure(api_key=GEMINI_API)
            model = genai.GenerativeModel(model_name='gemini-1.5-flash-001',system_instruction=[context])    
            response = model.generate_content(query_text)
            return JsonResponse({'response': response.text})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    