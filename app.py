# FILE: app.py

import os, json, re, io
from flask import Flask, render_template, jsonify, request, send_file
from google.cloud import firestore
from dotenv import load_dotenv
import google.generativeai as genai
from openpyxl import Workbook
from fpdf import FPDF


# ── CONFIG ───────────────────────────────────────────────────────────────────────
load_dotenv()
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
db  = firestore.Client()
app = Flask(__name__)

# ── HELPERS ──────────────────────────────────────────────────────────────────────
_FENCE_RE = re.compile(r"```(?:json)?|```", re.I)
def _strip_fences(text: str) -> str: return _FENCE_RE.sub("", text).strip()
def _normalise_ai_json(obj: dict) -> dict:
    questions = obj.get("quiz_questions") or obj.get("quizQuestions") or []
    if not isinstance(questions, list):
        questions = []
    return {"lesson_html": obj.get("lesson_html") or obj.get("lessonHtml") or "","quiz_questions": questions}

# ── PAGES ────────────────────────────────────────────────────────────────────────
@app.route("/")
def home(): return render_template("index.html")

@app.route("/onboarding")
def onboarding():
    styles = [
        {"style_name": "The Mentor", "explanation": "Imagine you have a friendly, experienced guide. This style uses analogies and stories to explain concepts, focusing on the 'why' behind the advice. It's encouraging and patient."},
        {"style_name": "The Analyst", "explanation": "This style is for the data-driven learner. It presents information with a focus on numbers, charts, and logical steps. It's precise, structured, and prioritizes factual accuracy."},
        {"style_name": "The Strategist", "explanation": "This style thinks about the big picture and long-term goals. It frames advice in the context of a client's overall financial plan and future objectives. It's forward-looking and outcome-oriented."}
    ]
    return render_template("onboarding.html", styles=styles)

# ── API: DATA LOADING ────────────────────────────────────────────────────────────
# THIS IS THE REPLACEMENT FOR THE ENTIRE get_library_and_history FUNCTION

@app.route("/get_library_and_history", methods=["POST"])
def get_library_and_history():
    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id: return jsonify({"error": "User ID is required."}), 400
    
    # Fetch lesson attempt history
    lesson_history_docs = db.collection("Users").document(user_id).collection("lesson_attempts").order_by("started_at", direction=firestore.Query.DESCENDING).stream()
    history_by_lesson = {}
    for doc in lesson_history_docs:
        d = doc.to_dict()
        lesson_id = d.get("lesson_id")
        if lesson_id not in history_by_lesson:
            history_by_lesson[lesson_id] = []
        history_by_lesson[lesson_id].append({"attempt_id": doc.id, "title": d.get("title"), "score": d.get("score"), "questions_total": d.get("questions_total"), "started_at": d.get("started_at").isoformat()})
    
    # Fetch the main library content and separate it
    library_docs = db.collection("ContentMaster").stream()
    official_library = []
    user_creations = []
    for doc in library_docs:
        doc_dict = doc.to_dict()
        title = doc_dict.get("title")
        if title:
            lesson_id = doc.id
            lesson_data = {"id": lesson_id, "title": title, "attempts": history_by_lesson.get(lesson_id, [])}
            # NEW: Check for the ai_generated flag
            if doc_dict.get("ai_generated"):
                user_creations.append(lesson_data)
            else:
                official_library.append(lesson_data)

    # Fetch final quiz history
    final_quiz_history = []
    final_quiz_docs = db.collection("Users").document(user_id).collection("final_quiz_attempts").order_by("started_at", direction=firestore.Query.DESCENDING).stream()
    for doc in final_quiz_docs:
        d = doc.to_dict()
        final_quiz_history.append({
            "attempt_id": doc.id,
            "title": d.get("title"),
            "score": d.get("score"),
            "questions_total": d.get("questions_total"),
            "started_at": d.get("started_at").isoformat()
        })
    # Return two separate lists for the library
    return jsonify({
        "library": official_library, 
        "user_creations": user_creations, 
        "final_quiz_history": final_quiz_history
    })

@app.route("/get_lesson_attempt", methods=["POST"])
def get_lesson_attempt():
    data = request.get_json()
    user_id, attempt_id = data.get("user_id"), data.get("attempt_id")
    try:
        attempt_ref = db.collection("Users").document(user_id).collection("lesson_attempts").document(attempt_id)
        attempt_doc = attempt_ref.get()
        if not attempt_doc.exists: return jsonify({"error": "Attempt not found."}), 404
        d = attempt_doc.to_dict()
        
        default_focus = {"smart_focus_needed": False, "missed_concepts": [], "explanation": ""}
        smart_focus_data = d.get("smart_focus", default_focus)

        results_package = {
            "lesson_id": d.get("lesson_id"),
            "content": d.get("lesson_content"),
            "user_answers": d.get("user_answers"),
            "score": d.get("score"),
            "questions_total": d.get("questions_total"),
            "smart_focus": smart_focus_data
        }
        return jsonify(results_package)
    except Exception as e:
        print(f"[get_lesson_attempt] Firestore error: {e}")
        return jsonify({"error": "Could not retrieve lesson history."}), 500

@app.route("/get_source_material", methods=["POST"])
def get_source_material():
    data = request.get_json()
    lesson_id = data.get("lesson_id")
    if not lesson_id: return jsonify({"error": "Lesson ID is required."}), 400
    try:
        doc_ref = db.collection("ContentMaster").document(lesson_id)
        doc = doc_ref.get()
        if not doc.exists: return jsonify({"error": "Source material not found"}), 404
        return jsonify(doc.to_dict())
    except Exception as e:
        print(f"[get_source_material] Firestore error: {e}")
        return jsonify({"error": "Could not retrieve source material."}), 500

# ── USER/PROFILE API ─────────────────────────────────────────────────────────────
@app.route("/create_user", methods=["POST"])
def create_user():
    data = request.get_json()
    uid = data.get("uid")
    if not uid: return jsonify({"status": "error", "message": "User ID required."}), 400
    doc_ref = db.collection("Users").document(uid)
    if not doc_ref.get().exists:
        doc_ref.set({"displayName" : data.get("displayName"),"email" : data.get("email"),"created_at"  : firestore.SERVER_TIMESTAMP,"learningStyle": None})
        return jsonify({"status": "success", "is_new_user": True, "needs_onboarding": True})
    user_data = doc_ref.get().to_dict()
    needs_onboarding = "learningStyle" not in user_data or user_data.get("learningStyle") is None
    return jsonify({"status": "success", "is_new_user": False, "needs_onboarding": needs_onboarding})

@app.route("/save_preference", methods=["POST"])
def save_preference():
    data = request.get_json()
    uid, style = data.get("uid"), data.get("style")
    if not uid or not style: return jsonify({"status": "error", "message": "UID and style are required."}), 400
    try:
        db.collection("Users").document(uid).update({"learningStyle": style})
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"[save_preference] Firestore error: {e}")
        return jsonify({"status": "error", "message": "Could not save preference."}), 500

@app.route("/start_lesson", methods=["POST"])
def start_lesson():
    data = request.get_json()
    user_id, lesson_id = data.get("user_id"), data.get("lesson_id")
    original_attempt_id = data.get("original_attempt_id")

    try:
        user_doc = db.collection("Users").document(user_id).get()
        learning_style = user_doc.to_dict().get("learningStyle") or "The Mentor"
    except Exception: learning_style = "The Mentor"

    lesson_content = None
    source_title = ""

    if original_attempt_id:
        original_attempt_doc = db.collection("Users").document(user_id).collection("lesson_attempts").document(original_attempt_id).get()
        if original_attempt_doc.exists:
            lesson_content = original_attempt_doc.to_dict().get("lesson_content")
            source_title = original_attempt_doc.to_dict().get("title")
        else:
            return jsonify({"error": "Original attempt not found for retake."}), 404
    else:
        source_doc_ref = db.collection("ContentMaster").document(lesson_id)
        source_doc = source_doc_ref.get()
        if not source_doc.exists: return jsonify({"error": "Lesson not found."}), 404
        
        source_content_full = source_doc.to_dict()
        source_title = source_content_full.get("title")

        def datetime_converter(o):
            if isinstance(o, firestore.firestore.DatetimeWithNanoseconds):
                return o.isoformat()
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

        # --- THIS IS THE FIX ---
        # If the topic is AI-generated, the "source" for the new AI prompt
        # is the content inside the 'lesson_content' field.
        if source_content_full.get("ai_generated"):
            source_for_prompt = source_content_full.get("lesson_content", {})
            prompt = f'You are an expert educator and trainer. Teach in the "{learning_style}" voice using the content provided as your source material. **OUTPUT REQUIREMENTS (pure JSON):** {{"lesson_html": "<string - raw HTML>", "quiz_questions": [{{ "question": "<string>", "options": ["A", "B", "C", "D"], "correct_answer_index": 0, "explanation": "<string>" }}]}} # SOURCE MATERIAL: {json.dumps(source_for_prompt, default=datetime_converter, ensure_ascii=False)}'
        else:
            # For human-made topics, the entire document is the source.
            source_for_prompt = source_content_full
            prompt = f'You are an expert financial trainer. Teach in the "{learning_style}" voice. **OUTPUT REQUIREMENTS (pure JSON):** {{"lesson_html": "<string - raw HTML>", "quiz_questions": [{{ "question": "<string>", "options": ["A", "B", "C", "D"], "correct_answer_index": 0, "explanation": "<string>" }}]}} # SOURCE MATERIAL: {json.dumps(source_for_prompt, default=datetime_converter, ensure_ascii=False)}'
        
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            raw_json = model.generate_content(prompt).text
            lesson_content = _normalise_ai_json(json.loads(_strip_fences(raw_json)))
        except Exception as e:
            print(f"[start_lesson] AI or JSON error: {e}")
            return jsonify({"error": "Lesson generation failed."}), 500

    if not lesson_content: return jsonify({"error": "Failed to get or generate lesson content."}), 500

    try:
        attempt_ref = db.collection("Users").document(user_id).collection("lesson_attempts").document()
        attempt_ref.set({ "lesson_id": lesson_id, "title": source_title, "learning_style": learning_style, "started_at": firestore.SERVER_TIMESTAMP, "status": "in-progress", "lesson_content": lesson_content, "user_answers": {}, "score": None, "questions_total": len(lesson_content.get("quiz_questions", [])) })
        return jsonify({"attempt_id": attempt_ref.id, "content": lesson_content, "lesson_id": lesson_id})
    except Exception as e:
        print(f"[start_lesson] Firestore error: {e}")
        return jsonify({"error": "Could not save new lesson attempt."}), 500

@app.route("/submit_quiz", methods=["POST"])
def submit_quiz():
    data = request.get_json()
    user_id, attempt_id, user_answers, lesson_id = data.get("user_id"), data.get("attempt_id"), data.get("user_answers"), data.get("lesson_id")
    attempt_ref = db.collection("Users").document(user_id).collection("lesson_attempts").document(attempt_id)
    attempt_doc = attempt_ref.get()
    if not attempt_doc.exists: return jsonify({"error": "Lesson attempt not found."}), 404
    
    lesson_content = attempt_doc.to_dict().get("lesson_content", {})
    quiz_questions = lesson_content.get("quiz_questions", [])
    
    score = 0
    missed_concepts = []
    for i, q in enumerate(quiz_questions):
        user_answer_index = user_answers.get(str(i))
        correct_answer_index = q.get("correct_answer_index")
        if user_answer_index is not None and int(user_answer_index) == correct_answer_index:
            score += 1
        else:
            missed_concepts.append(q.get("question"))

    smart_focus_data = {'smart_focus_needed': False, 'missed_concepts': [], 'explanation': ''}
    if missed_concepts:
        learning_style = attempt_doc.to_dict().get("learning_style", "The Mentor")
        sf_prompt = f'A user has completed a quiz and struggled with the concepts underlying the following questions: {json.dumps(missed_concepts)} Your task is to provide a single, cohesive "quick refresher" summary (as plain text, <200 words). This summary should explain the foundational principles or themes that connect these missed concepts. The user\'s learning style is "{learning_style}". Return ONLY the plain text explanation, no markdown.'

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            explanation = model.generate_content(sf_prompt).text.strip()
            smart_focus_data = {
                'smart_focus_needed': True,
                'missed_concepts': missed_concepts,
                'explanation': explanation
            }
        except Exception as e:
            print(f"[smart_focus] AI error: {e}")

    attempt_ref.update({ "status": "completed", "user_answers": user_answers, "score": score, "completed_at": firestore.SERVER_TIMESTAMP, "smart_focus": smart_focus_data })
    
    return jsonify({"lesson_id": lesson_id, "content": lesson_content, "user_answers": user_answers, "score": score, "questions_total": len(quiz_questions), "smart_focus": smart_focus_data})

@app.route("/start_multi_concept_lesson", methods=["POST"])
def start_multi_concept_lesson():
    data = request.get_json()
    user_id, concepts, parent_lesson_id = data.get("user_id"), data.get("concepts"), data.get("parent_lesson_id")
    if not all([user_id, concepts, parent_lesson_id]):
        return jsonify({"error": "User ID, a list of concepts, and parent lesson ID are required."}), 400

    try:
        user_doc = db.collection("Users").document(user_id).get()
        learning_style = user_doc.to_dict().get("learningStyle") or "The Mentor"
    except Exception: learning_style = "The Mentor"
    
    title = f"Focused Lesson on Key Concepts"
    prompt = f"""
    You are an expert financial trainer. Your task is to create a single, cohesive, foundational micro-lesson that addresses all the concepts a user struggled with.
    The user's learning style is "{learning_style}".
    The user struggled with the concepts underlying these questions:
    {json.dumps(concepts)}

    Instead of teaching to each question one-by-one, synthesize the underlying principles into a single lesson. Teach the "why" behind these concepts to build a stronger foundation.

    **OUTPUT REQUIREMENTS (pure JSON):**
    {{
      "lesson_html": "<string - A detailed HTML explanation of the foundational concepts, as if it were a full lesson. Use tags like <h2>, <p>, <ul> etc.>",
      "quiz_questions": [
        {{ "question": "<A question that tests the synthesized foundational knowledge>", "options": ["A", "B", "C", "D"], "correct_answer_index": 0, "explanation": "<Detailed explanation for this specific question>" }},
        {{ "question": "<A second, different question testing the core principles>", "options": ["A", "B", "C", "D"], "correct_answer_index": 1, "explanation": "<Detailed explanation for this specific question>" }}
      ]
    }}
    """
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        raw_json = model.generate_content(prompt).text
        lesson_content = _normalise_ai_json(json.loads(_strip_fences(raw_json)))
    except Exception as e:
        print(f"[start_multi_concept_lesson] AI or JSON error: {e}")
        return jsonify({"error": "Focused lesson generation failed."}), 500

    try:
        attempt_ref = db.collection("Users").document(user_id).collection("lesson_attempts").document()
        attempt_ref.set({
            "lesson_id": parent_lesson_id, 
            "title": title, 
            "learning_style": learning_style,
            "started_at": firestore.SERVER_TIMESTAMP, 
            "status": "in-progress",
            "lesson_content": lesson_content, 
            "user_answers": {}, 
            "score": None,
            "questions_total": len(lesson_content.get("quiz_questions", []))
        })
        return jsonify({"attempt_id": attempt_ref.id, "content": lesson_content, "lesson_id": parent_lesson_id})
    except Exception as e:
        print(f"[start_multi_concept_lesson] Firestore error: {e}")
        return jsonify({"error": "Could not save focused lesson."}), 500

@app.route("/delete_attempt", methods=["POST"])
def delete_attempt():
    data = request.get_json()
    user_id, attempt_id = data.get("user_id"), data.get("attempt_id")
    if not user_id or not attempt_id: return jsonify({"status": "error", "message": "User and attempt ID are required."}), 400
    try:
        db.collection("Users").document(user_id).collection("lesson_attempts").document(attempt_id).delete()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"[delete_attempt] Firestore error: {e}")
        return jsonify({"status": "error", "message": "Could not delete attempt."}), 500

@app.route("/ask_tutor", methods=["POST"])
def ask_tutor():
    data = request.get_json()
    question, context = data.get("question"), data.get("context")
    if not question or not context: return jsonify({"error": "A question and lesson context are required."}), 400
    prompt = f"You are a helpful AI Tutor for financial advisors. Answer the user's question based *only* on the provided lesson context. If the question cannot be answered from the context, politely state that you can only answer questions directly related to the current lesson material.\n\n# LESSON CONTEXT:\n{context}\n\n# USER'S QUESTION:\n{question}"
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        answer = model.generate_content(prompt).text.strip()
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"[ask_tutor] AI generation error: {e}")
        return jsonify({"error": "Sorry, I had a problem generating an answer."}), 500
    
@app.route("/delete_custom_topic", methods=["POST"])
def delete_custom_topic():
    data = request.get_json()
    user_id, topic_id = data.get("user_id"), data.get("topic_id")
    if not all([user_id, topic_id]): 
        return jsonify({"error": "User ID and Topic ID are required."}), 400

    try:
        # Use a transaction or a batch to ensure atomicity
        batch = db.batch()

        # 1. Delete the master document from ContentMaster
        master_ref = db.collection("ContentMaster").document(topic_id)
        batch.delete(master_ref)

        # 2. Find and delete all lesson attempts associated with this topic for the user
        attempts_query = db.collection("Users").document(user_id).collection("lesson_attempts").where("lesson_id", "==", topic_id)
        for doc in attempts_query.stream():
            batch.delete(doc.reference)
        
        # 3. Commit all the deletions at once
        batch.commit()
        
        return jsonify({"status": "success", "message": f"Topic {topic_id} and all its attempts have been deleted."})
    except Exception as e:
        print(f"[delete_custom_topic] Error: {e}")
        return jsonify({"error": "Failed to delete the custom topic and its history."}), 500


# ── API: DYNAMIC CONTENT & TOOLS ───────────────────────────────────────────────
@app.route("/create_custom_topic", methods=["POST"])
def create_custom_topic():
    data = request.get_json()
    user_id, topic_title = data.get("user_id"), data.get("topic_title")
    if not all([user_id, topic_title]): return jsonify({"error": "User ID and topic title are required."}), 400
    
    try:
        user_doc = db.collection("Users").document(user_id).get()
        learning_style = user_doc.to_dict().get("learningStyle") or "The Mentor"
    except Exception: learning_style = "The Mentor"

    prompt = f'You are an expert educator and trainer. Create a complete lesson about "{topic_title}". The lesson should be comprehensive and well-structured. Teach in the "{learning_style}" voice. **OUTPUT REQUIREMENTS (pure JSON):** {{"lesson_html": "<string - raw HTML>", "quiz_questions": [{{ "question": "<string>", "options": ["A", "B", "C", "D"], "correct_answer_index": 0, "explanation": "<string>" }}]}}'
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        raw_text = _strip_fences(response.text)
        
        try:
            lesson_content = _normalise_ai_json(json.loads(raw_text))
        except json.JSONDecodeError:
            print(f"[create_custom_topic] FAILED TO PARSE AI RESPONSE. AI likely returned an error page or non-JSON text.")
            print(f"RAW AI RESPONSE WAS: {raw_text}")
            return jsonify({"error": "The AI was unable to generate this topic, possibly due to safety filters or an internal error. Please try a different topic."}), 500

    except Exception as e:
        print(f"[create_custom_topic] AI generation error: {e}")
        return jsonify({"error": "An unexpected error occurred while generating the topic."}), 500
        
    if not lesson_content.get("lesson_html"): return jsonify({"error": "AI failed to generate lesson content."}), 500

    try:
        # Use a batch to perform both writes at once
        batch = db.batch()
        
        # 1. Create the master topic document
        doc_id = re.sub(r'[^a-z0-9]+', '-', topic_title.lower()).strip('-')
        master_ref = db.collection("ContentMaster").document(doc_id)
        source_doc_data = {
            "title": topic_title,
            "ai_generated": True,
            "date_updated": firestore.SERVER_TIMESTAMP,
            "lesson_content": lesson_content
        }
        batch.set(master_ref, source_doc_data)
        
        # 2. Create the first lesson_attempt document
        attempt_ref = db.collection("Users").document(user_id).collection("lesson_attempts").document()
        attempt_data = {
            "lesson_id": doc_id, 
            "title": topic_title, 
            "learning_style": learning_style,
            "started_at": firestore.SERVER_TIMESTAMP, 
            "status": "in-progress",
            "lesson_content": lesson_content, 
            "user_answers": {}, 
            "score": None,
            "questions_total": len(lesson_content.get("quiz_questions", []))
        }
        batch.set(attempt_ref, attempt_data)
        
        # 3. Commit both writes to the database
        batch.commit()
        
        # 4. Return everything the frontend needs in one go
        return jsonify({
            "lesson_id": doc_id,
            "attempt_id": attempt_ref.id,
            "content": lesson_content
        })
    except Exception as e:
        print(f"[create_custom_topic] Firestore save error: {e}")
        return jsonify({"error": "Could not save new custom topic."}), 500
    
@app.route("/generate_flashcards_lesson", methods=["POST"])
def generate_flashcards_lesson():
    data = request.get_json()
    user_id, attempt_id, count = data.get("user_id"), data.get("attempt_id"), data.get("count", 10)
    if not all([user_id, attempt_id]): return jsonify({"error": "User and Attempt ID required."}), 400
    try:
        attempt_doc = db.collection("Users").document(user_id).collection("lesson_attempts").document(attempt_id).get()
        if not attempt_doc.exists: return jsonify({"error": "Lesson attempt not found."}), 404
        lesson_context = attempt_doc.to_dict().get("lesson_content", {}).get("lesson_html", "")
        
        prompt = f'Based on the following lesson, generate exactly {count} flashcards as a JSON array. Each object must have a "question" and "answer" key. Output only the raw JSON array. ### LESSON: {lesson_context}'
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)

        # --- THIS IS THE FIX ---
        # Add robust error handling in case the AI returns an HTML error page.
        try:
            cards = json.loads(_strip_fences(response.text))
        except json.JSONDecodeError:
            print(f"[generate_flashcards_lesson] FAILED TO PARSE AI RESPONSE.")
            print(f"RAW AI RESPONSE WAS: {response.text}")
            return jsonify({"error": "The AI was unable to generate flashcards from this content."}), 500
        
        return jsonify({"cards": cards})
    except Exception as e:
        print(f"[generate_flashcards_lesson] Error: {e}")
        return jsonify({"error": "Failed to generate flashcards from lesson."}), 500
@app.route("/generate_flashcards_topics", methods=["POST"])
def generate_flashcards_topics():
    data = request.get_json()
    topic_ids, count = data.get("topic_ids"), data.get("count", 20)
    if not topic_ids: return jsonify({"error": "At least one Topic ID is required."}), 400
    
    all_content = []
    for topic_id in topic_ids:
        doc = db.collection("ContentMaster").document(topic_id).get()
        if doc.exists: all_content.append(doc.to_dict())

    if not all_content: return jsonify({"error": "No content found for topics."}), 404
    
    prompt = f'Based on the following combined lesson material, generate {count} flashcards as a JSON array. Each object must have a "question" and "answer" key. Output only the raw JSON array. ### MATERIAL: {json.dumps(all_content)}'
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        cards = json.loads(_strip_fences(response.text))
        return jsonify({"cards": cards})
    except Exception as e:
        print(f"[generate_flashcards_topics] Error: {e}")
        return jsonify({"error": "Failed to generate flashcards from topics."}), 500

@app.route("/export_flashcards", methods=["POST"])
def export_flashcards():
    data = request.get_json()
    file_format, title, cards = data.get("format"), data.get("title"), data.get("cards")
    if not all([file_format, title, cards]): return jsonify({"error": "Format, title, and cards are required."}), 400
    
    if file_format == "xlsx":
        output = io.BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Flashcards"
        sheet.append(["Question", "Answer"])
        for card in cards:
            sheet.append([card.get("question", ""), card.get("answer", "")])
        workbook.save(output)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"{title}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif file_format == "pdf":
        output = io.BytesIO()
        pdf = FPDF(font_cache_dir=None)
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        
        for i, card in enumerate(cards):
            question = card.get("question", "")
            answer = card.get("answer", "")
            
            pdf.set_font("Helvetica", 'B', 12)
            # THIS IS THE FIX: The `new_x="LMARGIN"` parameter tells the library it's
            # okay to break long words if necessary, preventing the crash.
            pdf.multi_cell(0, 10, f"Q{i+1}: {question}", new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("Helvetica", '', 12)
            pdf.multi_cell(0, 10, f"A: {answer}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

        pdf_bytes = pdf.output()
        output.write(pdf_bytes)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"{title}.pdf", mimetype='application/pdf')

    return jsonify({"error": "Unsupported format"}), 400

# ── API: FINAL CUMULATIVE QUIZ (STATEFUL) ────────────────────────────────────────
@app.route("/generate_final_quiz", methods=["POST"])
def generate_final_quiz():
    data = request.get_json()
    user_id, topic_ids, question_count = data.get("user_id"), data.get("topic_ids"), data.get("question_count")
    if not all([user_id, topic_ids, question_count]): return jsonify({"error": "User ID, Topic IDs, and question count are required."}), 400

    all_content = []
    topic_titles = []
    try:
        for topic_id in topic_ids:
            doc = db.collection("ContentMaster").document(topic_id).get()
            if doc.exists:
                doc_dict = doc.to_dict()
                all_content.append(doc_dict)
                topic_titles.append(doc_dict.get("title", "Unknown Topic"))
    except Exception as e:
        print(f"[generate_final_quiz] Firestore error: {e}")
        return jsonify({"error": "Could not retrieve source content."}), 500
    if not all_content: return jsonify({"error": "No content found for the selected topics."}), 404

    prompt = f"""
    You are an expert financial training examiner. Your task is to create a cumulative final quiz.
    Generate exactly {question_count} unique and challenging quiz questions based on the combined source material provided below.
    The questions should synthesize information across the different topics where possible. Do not simply copy questions from the source.
    **OUTPUT REQUIREMENTS (pure JSON):** {{"quiz_questions": [{{ "question": "<string>", "options": ["A", "B", "C", "D"], "correct_answer_index": 0, "explanation": "<string>" }}]}}
    # COMBINED SOURCE MATERIAL: {json.dumps(all_content, ensure_ascii=False)}
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        raw_json = model.generate_content(prompt).text
        quiz_data = json.loads(_strip_fences(raw_json))
        final_questions = quiz_data.get("quiz_questions", [])
        if not final_questions: raise ValueError("AI did not return any questions.")
    except Exception as e:
        print(f"[generate_final_quiz] AI or JSON error: {e}")
        return jsonify({"error": "Final quiz generation failed."}), 500

    title = f"Final Quiz on {len(topic_titles)} Topics" if len(topic_titles) > 1 else f"Final Quiz: {topic_titles[0]}"
    try:
        attempt_ref = db.collection("Users").document(user_id).collection("final_quiz_attempts").document()
        attempt_ref.set({
            "title": title,
            "topic_ids": topic_ids,
            "quiz_questions": final_questions,
            "questions_total": len(final_questions),
            "started_at": firestore.SERVER_TIMESTAMP,
            "status": "in-progress",
            "score": None,
            "user_answers": {}
        })
        return jsonify({"attempt_id": attempt_ref.id, "quiz_questions": final_questions})
    except Exception as e:
        print(f"[generate_final_quiz] Firestore save error: {e}")
        return jsonify({"error": "Could not save the new final quiz."}), 500

@app.route("/submit_final_quiz", methods=["POST"])
def submit_final_quiz():
    data = request.get_json()
    user_id, attempt_id, user_answers = data.get("user_id"), data.get("attempt_id"), data.get("user_answers")
    if not all([user_id, attempt_id, user_answers]): return jsonify({"error": "User ID, Attempt ID, and answers are required."}), 400

    attempt_ref = db.collection("Users").document(user_id).collection("final_quiz_attempts").document(attempt_id)
    try:
        attempt_doc = attempt_ref.get()
        if not attempt_doc.exists: return jsonify({"error": "Final quiz attempt not found."}), 404
        
        quiz_data = attempt_doc.to_dict()
        quiz_questions = quiz_data.get("quiz_questions", [])
        
        score = 0
        for i, q in enumerate(quiz_questions):
            user_answer_index = user_answers.get(str(i))
            correct_answer_index = q.get("correct_answer_index")
            if user_answer_index is not None and int(user_answer_index) == correct_answer_index:
                score += 1
        
        attempt_ref.update({
            "user_answers": user_answers,
            "score": score,
            "status": "completed",
            "completed_at": firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({
            "title": quiz_data.get("title"),
            "user_answers": user_answers,
            "score": score,
            "questions_total": len(quiz_questions),
            "quiz_questions": quiz_questions
        })
    except Exception as e:
        print(f"[submit_final_quiz] Error: {e}")
        return jsonify({"error": "Failed to score final quiz."}), 500

@app.route("/get_final_quiz_attempt", methods=["POST"])
def get_final_quiz_attempt():
    data = request.get_json()
    user_id, attempt_id = data.get("user_id"), data.get("attempt_id")
    if not user_id or not attempt_id: return jsonify({"error": "User and Attempt ID required."}), 400
    try:
        doc = db.collection("Users").document(user_id).collection("final_quiz_attempts").document(attempt_id).get()
        if not doc.exists: return jsonify({"error": "Final quiz attempt not found"}), 404
        return jsonify(doc.to_dict())
    except Exception as e:
        print(f"[get_final_quiz_attempt] Error: {e}")
        return jsonify({"error": "Could not retrieve final quiz attempt."}), 500

@app.route("/retake_final_quiz", methods=["POST"])
def retake_final_quiz():
    data = request.get_json()
    user_id, original_attempt_id = data.get("user_id"), data.get("original_attempt_id")
    if not user_id or not original_attempt_id: return jsonify({"error": "User and Original Attempt ID required."}), 400

    try:
        # Get the original quiz data
        original_doc_ref = db.collection("Users").document(user_id).collection("final_quiz_attempts").document(original_attempt_id)
        original_doc = original_doc_ref.get()
        if not original_doc.exists: return jsonify({"error": "Original final quiz not found."}), 404
        original_data = original_doc.to_dict()

        # Create a new attempt document with the same questions
        new_attempt_ref = db.collection("Users").document(user_id).collection("final_quiz_attempts").document()
        new_attempt_ref.set({
            "title": original_data.get("title") + " (Retake)",
            "topic_ids": original_data.get("topic_ids"),
            "quiz_questions": original_data.get("quiz_questions"),
            "questions_total": original_data.get("questions_total"),
            "started_at": firestore.SERVER_TIMESTAMP,
            "status": "in-progress",
            "score": None,
            "user_answers": {}
        })
        
        return jsonify({
            "attempt_id": new_attempt_ref.id,
            "quiz_questions": original_data.get("quiz_questions")
        })
    except Exception as e:
        print(f"[retake_final_quiz] Error: {e}")
        return jsonify({"error": "Could not create retake quiz."}), 500

# ── MAIN ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)