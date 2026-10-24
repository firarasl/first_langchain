from langchain_ollama import ChatOllama

# ollama pull llama3
llm = ChatOllama(
    model="llama3",
    temperature=0,
)

messages = [
    (
        "system",
        "You are a helpful assistant that translates English to German.",
    ),
    ("human", "I love programming"),
]

ai_msg = llm.invoke(messages)
print(ai_msg)