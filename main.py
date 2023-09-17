from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from bson.objectid import ObjectId

from pymongo import MongoClient
from fastapi.staticfiles import StaticFiles
import openai
import os

from markdown_it import MarkdownIt

md = MarkdownIt().enable("table")

openai.api_key = os.getenv("OPENAI_API_KEY")

### KEEP YOUR MONGODB CONNECTION KEY A SECRET!!!
### REPLACE WITH YOUR OWN MONGO DB CONNECTION STRING AND KEEP THE CONNECTION KEY A SECRET!!!
client = MongoClient("mongodb://mongo:ao96zD7GuTAYgXhCVeBg@containers-us-west-48.railway.app:7800")
db = client["htmx_chat"]
collection = db["chat_history"]

app = FastAPI()

def gpt_call(messages):
    response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo-0613",
    messages=messages
)

    return response['choices'][0]['message']['content']

current_chat_id = None
current_chat_messages = []

#load all chat ids
chat_ids = []
print("loading chat ids")
for chat in collection.find():
    chat_ids.append(str(chat["_id"]))



@app.get("/load_history_on_page_load")
async def load_history_on_page_load():
    global current_chat_id
    global current_chat_messages
    
    current_chat_id = None
    current_chat_messages = []
    # Attempt to get the first chat from the collection
    chat = collection.find_one()

    # Check if a chat was found
    if chat is not None:
        # If a chat was found, loop over the collection and create buttons
        buttons = []
        for chat in collection.find():
            chat_id = str(chat["_id"])
            summary = chat["summary"]
            button_html = f"""<button class="bg-gray-600 px-4 py-2 mx-1 my-1 text-white overflow-hidden overflow-ellipsis whitespace-nowrap hover:bg-gray-700 active:bg-gray-800 w-full" hx-get="/load_chat" hx-trigger="click" hx-target=".messages" hx-swap="innerHTML" data-chat-id="{chat_id}" hx-on='htmx:configRequest: event.detail.parameters.chat_id = this.getAttribute("data-chat-id"); document.querySelector(".messages").addEventListener("click", scrollToBottom);' title="{summary}">{summary}</button>"""
            buttons.insert(0, button_html)
        
        # Join all button HTML strings into one string and return
        return HTMLResponse(''.join(buttons))
    else:
        # If no chat was found, return an empty string
        return HTMLResponse('')

@app.get("/clear_chat")
async def clear_chat():
    global current_chat_id
    global current_chat_messages

    current_chat_id = None
    current_chat_messages = []
    return HTMLResponse('<div class="messages"></div>')

@app.post("/new_chat")
async def new_chat(request: Request):
    global current_chat_id
    global current_chat_messages
    data = await request.form()
    message = data["message"]
    print(message)
    role = "user"

    #check if there is a current chat
    if current_chat_id is not None:
        # get the current chat
        current_chat = collection.find_one({"_id": ObjectId(current_chat_id)})
        print("existing chat")
        # get the current chat messages
        current_chat_messages = current_chat["messages"]
        # append the new message to the current chat messages
        current_chat_messages.append({"role": role, "content": message})
        
        # update the current chat with the new messages list with role and the message
        collection.update_one({"_id": ObjectId(current_chat_id)}, {"$set": {"messages": current_chat_messages}})
        # return the user message and the assistant message as html response
        return HTMLResponse(f'<div class="bg-gray-700 px-4 py-2 mx-1 text-white" hx-trigger="load" hx-get="/get_gpt_response" hx-target=".messages" hx-indicator="#indicator" hx-swap="beforeend">{message}</div>')
    else:
        print("no current chat")
        # create a new chat
        new_chat = {"messages": [{"role": role, "content": message}]}

        # insert the new chat into the database
        collection.insert_one(new_chat)
        # set the current chat id to the new chat id
        current_chat_id = str(new_chat["_id"])

        # set the current chat messages to the new chat messages
        current_chat_messages.append({"role": role, "content": message})
        # return the user message and the assistant message as html response
        return HTMLResponse(f'<div class="bg-gray-700 px-4 py-2 mx-1 text-white" hx-trigger="load" hx-get="/get_gpt_response" hx-target=".messages" hx-indicator="#indicator" hx-swap="beforeend">{message}</div>')

@app.get("/get_gpt_response")
async def get_gpt_response():
    global current_chat_id
    global current_chat_messages
    
    assistant_message = gpt_call(current_chat_messages)
    
    # append the assistant message to the current chat messages
    current_chat_messages.append({"role": "assistant", "content": assistant_message})    

    # update the current chat with the new messages list with role and the message
    collection.update_one({"_id": ObjectId(current_chat_id)}, {"$set": {"messages": current_chat_messages}})

    assistant_message = md.render(assistant_message)
    
    #check if current chat id is in chat ids
    if current_chat_id in chat_ids:
        formatted_html = f"""<div class="bg-gray-800 px-4 py-2 mx-1 text-white" hx-script='scrollToBottom()'>{assistant_message}</div>"""
    else:
        formatted_html = f"""<div class="bg-gray-800 px-4 py-2 mx-1 text-white" hx-trigger="load" hx-get="/load_history_button" hx-target=".chat-history" hx-swap="afterbegin" hx-script='scrollToBottom()'>{assistant_message}</div>"""

    return HTMLResponse(formatted_html)

@app.get("/load_history_button")
async def load_history_button():
    global current_chat_id
    global current_chat_messages

    messages = current_chat_messages
    messages.append({"role": "user", "content": "summarize this conversation in maximum of 3 word sentence generally describing what the conversation is about"})
    summary = gpt_call(messages)
    # add the chat summary to mongo db
    collection.update_one({"_id": ObjectId(current_chat_id)}, {"$set": {"summary": summary}})

    #append the new chat id to the chat ids, so we don't have to create the button again
    chat_ids.append(current_chat_id)
    # create buttons with the hcat id as an attribute
    return HTMLResponse(f"""<button class="bg-gray-600 px-4 py-2 mx-1 my-1 text-white overflow-hidden overflow-ellipsis whitespace-nowrap hover:bg-gray-700 active:bg-gray-800 w-full" hx-get="/load_chat" hx-trigger="click" hx-target=".messages" hx-swap="innerHTML" data-chat-id="{current_chat_id}" hx-on='htmx:configRequest: event.detail.parameters.chat_id = this.getAttribute("data-chat-id"); document.querySelector(".messages").addEventListener("htmx:afterOnLoad", scrollToBottom);' title="{summary}">{summary}</button>""")

@app.get("/load_chat")
async def load_chat(request: Request):
    global current_chat_id
    # Extract chat_id from the request's query parameters
    chat_id = request.query_params.get("chat_id")

    # Convert chat_id to ObjectId and Retrieve the chat details from the MongoDB database
    chat = collection.find_one({"_id": ObjectId(chat_id)})
    current_chat_id = chat_id

    if chat is not None:
        # If the chat exists, format and return the chat's messages paying attention to "user" and "assistant" roles and their styling
        formatted_chat = "".join([f"""<div class="bg-gray-700 px-4 py-2 mx-1 text-white">{message["content"]}</div>""" if message["role"] == "user" else f"""<div class="bg-gray-800 px-4 py-2 mx-1 text-white">{md.render(message["content"])}</div>""" for message in chat["messages"]])
        return HTMLResponse(formatted_chat)
    else:
        return HTMLResponse('<div>No chat found with the provided id</div>')



app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
