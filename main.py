
import os
import re
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_groq import ChatGroq
from langchain_text_splitters import markdown
from markupsafe import Markup
from prefix import SQL_PREFIX
from boilerplate import (
    marker_boilerplate, 
    holding_period_boilerplate, 
    two_bed_holding_period_boilerplate, 
    javascript_map_boilerplate, 
    building_marker_format_boilerplate, 
    school_marker_format_boilerplate
)
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent
from tools import query_as_list, setup_tools
from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
load_dotenv()


POSTGRES_USER = os.environ["PG_USER"]
POSTGRES_PASSWORD = os.environ["PG_PASSWORD"]
POSTGRES_PORT = os.environ["PG_PORT"]
POSTGRES_DB = os.environ["PG_DB"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]


connection_string = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{POSTGRES_PORT}/{POSTGRES_DB}"

db = SQLDatabase.from_uri(connection_string)
#llm = ChatOllama(model="llama3.1", temperature=0)
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
        api_key=GROQ_API_KEY
)




prefix = SQL_PREFIX.format(
    table_names=db.get_usable_table_names(),
    marker_boilerplate=marker_boilerplate,
    holding_period_boilerplate=holding_period_boilerplate,
    two_bed_holding_period_boilerplate=two_bed_holding_period_boilerplate,
    javascript_map_boilerplate=javascript_map_boilerplate,
    building_marker_format_boilerplate=building_marker_format_boilerplate,
    school_marker_format_boilerplate=school_marker_format_boilerplate,
)

# Append a strict reminder about column names to stop hallucinations
system_prompt_content = f"""
{prefix}

You have tools to look up table names, column schemas, and run SQL queries against a live PostgreSQL database.
ALWAYS use these tools to check the schema and run a real query before answering any question about data.
NEVER answer a data question (sales, prices, dates, counts, etc.) from memory — you must query the database first.
Only describe columns/schema directly, without querying, if the user explicitly asks "what columns/schema do you have."
- NEVER guess column names. For example, in `core_condosale`, the date column is `closing_date`.
"""
system_message = SystemMessage(system_prompt_content)

tools = setup_tools(db, llm)

agent_executor = create_agent(
    model=llm, 
    tools=tools, 
    system_prompt=system_message.content
    )

def print_sql(sql):
    print("""
    The SQL query is:
        {}
        
        """.format(sql))

def extract_and_remove_html(text):
    html_pattern = r"'''html\s*([\s\S]*?)\s*'''"
    match = re.search(html_pattern, text, re.IGNORECASE)

    # First look for any python code
    python_pattern = (
        r'<pre\s+class="codehilite"><code\s+class="language-python">(.*?)</code></pre>'
    )
    md_pattern = r"'''python(.*?)'''"
    python_match = re.search(python_pattern, text, re.DOTALL | re.IGNORECASE)
    md_match = re.search(md_pattern, text, re.DOTALL)
    code_match = python_match or md_match

    if code_match:
        print(text)
        code = code_match.group(1)
        code = code.replace("&quot;", '"')
        code = code.replace("&amp;", "&")
        code = code.replace("&lt;", "<")
        code = code.replace("&gt;", ">")
        code = code.replace("&#39;", "'")
        return None, "PDF Generated!", code

    
    if match:
        html_content = match.group(1).strip()
        text_without_html = re.sub(html_pattern, '', text, flags=re.IGNORECASE).strip()
        return Markup(html_content), text_without_html, False
    else:
        return None, text, False


setup_tools(db, llm)

def process_markdown(text):
    # Convert markdown to HTML using MarkupSafe
    html = markdown.markdown(text, extensions=['extra', 'codehilite'])
    return Markup(html)


# Function to detect malicious patterns
def detect_malicious_code(code):
    # Define a list of regex patterns for dangerous functions or modules
    malicious_patterns = [
        r'import\s+(sys|subprocess|shlex|socket|ctypes|signal|multiprocessing)',  # Importing dangerous modules
        r'os\.(system|popen|remove|rmdir|rename|chmod|chown|kill|fork)',  # Dangerous os methods
        r'subprocess\.(Popen|run|call|check_output)',  # Subprocess methods
        r'eval\(',  # Use of eval()
        r'exec\(',  # Use of exec()
        r'compile\(',  # Use of compile()
        r'shutil\.(copy|move|rmtree)',  # shutil file operations
        r'socket\.',  # Use of sockets for network access
        r'requests\.',  # Use of requests library
        r'urllib\.',  # Use of urllib library
        r'getattr\(', r'setattr\(',  # Reflection
        r'globals\(', r'locals\(',  # Accessing global or local variable scopes
        r'importlib\.',  # Dynamic importing
        r'input\(',  # Use of input() for potentially malicious prompts
        r'os\.exec',  # exec family in os module
        r'ast\.(literal_eval)',  # Use of ast.literal_eval() for dynamic evaluation
    ]

    for pattern in malicious_patterns:
        if re.search(pattern, code):
            print(f"Potentially dangerous pattern detected: {pattern}")
            return True
    return False


def process_question(prompted_question, conversation_history):
    context = "\n".join(
        [
            f"Q: {entry['question']}\nA: {entry['answer']}" 
            for entry in conversation_history
        ]
    )
    consolidated_prompt = f"""
    Previous conversation history:
    {context}

    New question: {prompted_question}

    Answer ONLY the new question above. Use the previous conversation only if the new question directly refers back to it (e.g. "what about that building" or "show me more on that"). If the new question is unrelated to the previous conversation, ignore the previous conversation entirely and answer fresh using the database tools.
    
    """
    prompt = consolidated_prompt if conversation_history else prompted_question
    content = []

    for s in agent_executor.stream({"messages": [HumanMessage(content=prompt)]}):        
        for node_name, node_content in s.items():
            if node_name != "model":   # <-- skip the "tools" node, that's where the schema dump comes from
                continue
            if isinstance(node_content, dict) and "messages" in node_content:
                for msg in node_content["messages"]:
                    if getattr(msg, "content", None):

                        for call in msg.tool_calls:
                            if sql := call.get("args", {}).get("query", None):
                                print(print_sql(sql))                                
                        print(f"\n--- Output from [{node_name}] ---")
                        print(msg.content)
                        html, stripped_text, code = extract_and_remove_html(msg.content)
                        if code and not detect_malicious_code(code):
                            exec(code)
                        content.append(process_markdown(stripped_text))
                        if html:
                            content.append(html)

    return content