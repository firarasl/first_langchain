from flask import Flask, render_template, request, session
from main import process_question
import os
import uuid 

app = Flask(__name__)

app.secret_key = os.environ["FLASK_SECRET"]
MAX_CONTENT_LENGTH = 3

def get_conversation_history():
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return session["conversation_history"]

def add_to_conversation_history(question, answer):
    history = get_conversation_history()
    history.append({"question": question, "answer": answer})
    if len(history) > MAX_CONTENT_LENGTH:
        history.pop(0)  # Remove the oldest entry if we exceed the max length
    session["conversation_history"] = history

@app.route("/", methods=["GET", "POST"])
def index():
    result = None

    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

        
    if request.method == "POST":

        if request.form.get("sign_out"):
            session.clear()
            return render_template("index.html", result=result)

        question = request.form["question"]
        conversation_history = get_conversation_history()
        result = process_question(question, conversation_history)
        add_to_conversation_history(question, result)
    return render_template("index.html", result=result, gmaps_api_key=os.environ["GOOGLE_MAPS_API_KEY"])

if __name__ == "__main__":
    app.run(debug=True)
