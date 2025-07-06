/* FILE: static/js/main.js
   Paramigo Front-End  —  FULL MERGE  •  24 Jun 2025
   ─────────────────────────────────────────────────────────────────────────
   ▸ Restores Firebase auth & the entire SPA workflow
   ▸ Adds source-material accordion, Create-Topic, flashcards, export
   ▸ Modernises utilities & CSS hooks
*/

/* ───── 1.  ES-MODULE IMPORTS & FIREBASE SETUP ────────────────────────── */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import {
  getAuth,
  onAuthStateChanged,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyB4EJ5fu2ZGn3YG6NerCZRHfLj3F1mvpww",
  authDomain: "paramigo-tool-03.firebaseapp.com",
  projectId: "paramigo-tool-03",
  storageBucket: "paramigo-tool-03.firebasestorage.app",
  messagingSenderId: "626376082375",
  appId: "1:626376082375:web:7b0edfa3319c258d900fe2",
  measurementId: "G-5C44175E71",
};
const fbApp = initializeApp(firebaseConfig);
const auth = getAuth(fbApp);

/* ───── 2.  DOM HELPERS & BASE UTILITIES ──────────────────────────────── */
const $ = (sel, p = document) => p.querySelector(sel);
const $$ = (sel, p = document) => [...p.querySelectorAll(sel)];
const el = (tag, cls = "", txt = "") => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt) n.textContent = txt;
  return n;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  return r.json();
}

/* Ensure options field is always an array (defensive) */
function normalizeOptions(opt) {
  if (Array.isArray(opt)) return opt;
  if (typeof opt === "string") {
    const matches = opt.match(/[A-Z]\)[^A-Z]*/g);
    return (matches || opt.split(/[;,]/)).map((s) => s.trim());
  }
  return [];
}

function formatSourceMaterialAsHtml(source) {
  // NEW: Handle AI-generated source material, which has a different structure.
  if (source.ai_generated && source.lesson_content) {
    let html = "<h3>AI-Generated Lesson Content</h3>";
    html += source.lesson_content.lesson_html;
    return html;
  }

  // Fallback for original, human-written source material.
  let html = "";
  if (source.goal) {
    html += `<h3>Goal</h3><p>${source.goal}</p>`;
  }
  if (source.outcomes && source.outcomes.length) {
    html += `<h3>Outcomes</h3><ul>${source.outcomes
      .map((o) => `<li>${o}</li>`)
      .join("")}</ul>`;
  }
  if (source.talking_points) {
    html += `<h3>Talking Points</h3><p>${source.talking_points}</p>`;
  }
  if (source.philosophy) {
    html += `<h3>Philosophy</h3><p>${source.philosophy}</p>`;
  }
  if (source.resources && source.resources.length) {
    html += `<h3>Resources</h3><ul>${source.resources
      .map((r) => `<li>${r}</li>`)
      .join("")}</ul>`;
  }
  if (source.tasks && source.tasks.length) {
    html += `<h3>Tasks</h3><dl>${source.tasks
      .map(
        (t) => `<dt><strong>${t.title}</strong></dt><dd>${t.description}</dd>`
      )
      .join("")}</dl>`;
  }
  if (source.other_notes) {
    html += `<h3>Other Notes</h3><p>${source.other_notes}</p>`;
  }
  return html || "<p>No structured source material found.</p>";
}

/* ───── 3.  GLOBAL STATE & DOM REFERENCES ─────────────────────────────── */
let currentUser = null;
let currentAttemptId = null;
let currentLessonId = null;
let currentLessonContext = null;
let libraryData = [];
let currentFinalQuizQuestions = [];
let FLASHCARDS = [];

const loginContainer = $("#login-container");
const appContainer = $("#app-container");
const userNameSpan = $("#user-name");
const flashcardTopicModal = $("#flashcard-topic-modal");
const flashcardTopicSelectionList = $("#flashcard-topic-selection-list");
const generateFlashcardsBtnModal = $("#generate-flashcards-btn-modal");
const cancelFlashcardsBtnModal = $("#cancel-flashcards-btn-modal");
const selectAllFlashcardTopicsCheckbox = $(
  "#select-all-flashcard-topics-checkbox"
);

const views = {
  library: $("#lesson-library-view"),
  topicDetail: $("#topic-detail-view"),
  lesson: $("#lesson-taking-view"),
  results: $("#results-view"),
  finalQuiz: $("#final-quiz-view"),
};
const tutorButton = $("#tutor-button");
const tutorChatContainer = $("#tutor-chat-container");
const tutorChatHistory = $("#tutor-chat-history");
const tutorInput = $("#tutor-input");

const finalQuizModal = $("#final-quiz-modal");
const topicSelectionList = $("#topic-selection-list");
const generateFinalQuizBtn = $("#generate-final-quiz-btn");
const cancelFinalQuizBtn = $("#cancel-final-quiz-btn");
const questionCountInput = $("#question-count-input");
const selectAllTopicsCheckbox = $("#select-all-topics-checkbox");

/* ───── 4.  VIEW HELPERS ──────────────────────────────────────────────── */
function showView(name) {
  Object.values(views).forEach((v) => (v.style.display = "none"));
  views[name].style.display = "block";
  tutorButton.style.display =
    name === "lesson" || name === "results" ? "block" : "none";
  window.scrollTo(0, 0);
}
window.showView = showView;

/* ───── 5. LIBRARY & DASHBOARD RENDERING ─────────────────────────────── */
async function initializeAppForUser(user) {
  currentUser = user;
  // Now expects three lists from the backend
  const { library, user_creations, final_quiz_history } = await post(
    "/get_library_and_history",
    { user_id: user.uid }
  );

  const safeUserCreations = user_creations || [];
  libraryData = [...(library || []), ...safeUserCreations]; // Combine for other parts of the app

  const dynamicArea = $("#library-dynamic-area", views.library);
  if (!dynamicArea)
    return console.error("Critical error: #library-dynamic-area not found!");

  const renderTopicList = (topics, isUserCreated = false) => {
    return topics
      .map(
        (t) => `
      <li class="lesson-item" onclick="showTopicDetail('${t.id}')">
        <span class="lesson-title">${t.title}</span>
        ${
          t.attempts.length
            ? '<span class="lesson-item-indicator">✔ Started</span>'
            : ""
        }
        ${
          isUserCreated
            ? `<button class="delete-topic-btn" onclick="event.stopPropagation(); deleteCustomTopic('${t.id}', '${t.title}')">Delete</button>`
            : ""
        }
      </li>
    `
      )
      .join("");
  };

  let libraryHtml =
    "<h2>Lesson Library</h2><p>Select a topic to begin or review your history.</p>";
  libraryHtml += `<ul id="lesson-list">${renderTopicList(library || [])}</ul>`;

  if (safeUserCreations.length > 0) {
    libraryHtml += `
      <hr style="margin:2em 0">
      <h3>Your Created Topics</h3>
      <ul id="user-creations-list">${renderTopicList(
        safeUserCreations,
        true
      )}</ul>
    `;
  }

  // ===== [THIS IS THE NEW CODE BLOCK] =====
  // Inject the button between the created topics and the final quiz history.
  libraryHtml += `
    <hr style="margin:2em 0; border-top: 1px solid var(--c-border);">
    <button id="final-quiz-button" class="btn-outline" style="width:100%; text-align:center;">
        Take a Final Quiz
    </button>
  `;
  // ========================================

  if (final_quiz_history?.length) {
    libraryHtml += `
      <hr style="margin:2em 0; border-top: 1px solid var(--c-border);">
      <h3>Final Quiz History</h3>
      <ul id="final-quiz-history-list">
        ${final_quiz_history
          .map(
            (h) => `
          <li class="attempt-item" onclick="reviewFinalQuiz('${h.attempt_id}')">
            <strong>${h.title}</strong><br>
            Score: ${
              h.score !== null
                ? `${h.score}/${h.questions_total}`
                : "In Progress"
            }<br>
            <small>${new Date(h.started_at).toLocaleString()}</small>
          </li>
        `
          )
          .join("")}
      </ul>`;
  }

  dynamicArea.innerHTML = libraryHtml;

  // This event listener will now find the button we just injected into the HTML.
  if ($("#final-quiz-button")) {
    $("#final-quiz-button").addEventListener("click", showFinalQuizModal);
  }

  showView("library");
}

/* ───── 6.  LESSON FLOW ──────────────────────────────────────────────── */
async function startLesson(lessonId, originalAttemptId = null) {
  views.lesson.innerHTML = "<h2>Loading Lesson…</h2>";
  showView("lesson");
  try {
    const payload = { user_id: currentUser.uid, lesson_id: lessonId };
    if (originalAttemptId) payload.original_attempt_id = originalAttemptId;

    const data = await post("/start_lesson", payload);
    currentAttemptId = data.attempt_id;
    currentLessonId = data.lesson_id;
    currentLessonContext = data.content;
    renderLesson(data.content, data.lesson_id);
  } catch (e) {
    views.lesson.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
window.startLesson = startLesson;

/* MAIN LESSON RENDERER (adds accordion & flashcards) */
async function renderLesson(content, lessonId) {
  const root = views.lesson;
  const { lesson_html, quiz_questions } = content;

  /* Lesson body */
  root.innerHTML = `<div>${lesson_html}</div>`;

  /* -- FEATURE: Accordion with raw source material -- */
  try {
    const src = await post("/get_source_material", {
      user_id: currentUser.uid,
      lesson_id: lessonId,
    });
    const acc = el("div", "accordion");
    const head = el("button", "accordion-head", "Show Source Material");
    const body = el("div", "accordion-body"); // Changed from <pre> to <div>

    // FIX: Use the new formatter function
    body.innerHTML = formatSourceMaterialAsHtml(src);

    body.style.display = "none";
    head.onclick = () => {
      const open = body.style.display === "block";
      body.style.display = open ? "none" : "block";
      head.textContent = open ? "Show Source Material" : "Hide Source Material";
    };
    acc.append(head, body);
    root.append(acc);
  } catch (err) {
    console.warn("Accordion error:", err.message);
  }

  /* Flashcards button */
  const fcBtn = el("button", "btn-primary", "Generate Flashcards");
  fcBtn.style.marginTop = "1.5em";
  fcBtn.onclick = genFlashcardsLesson;
  root.append(fcBtn);

  /* Quiz */
  const shuffled = [...quiz_questions].sort(() => Math.random() - 0.5);
  const quizHtml = shuffled
    .map((q, i) => {
      const origIndex = quiz_questions.indexOf(q);
      const opts = normalizeOptions(q.options)
        .map(
          (o, j) =>
            `<label><input type="radio" name="${origIndex}" value="${j}" required><span>${o}</span></label>`
        )
        .join("");
      return `<div class="quiz-question"><h4>${i + 1}. ${
        q.question
      }</h4><div class="quiz-options">${opts}</div></div>`;
    })
    .join("");

  root.insertAdjacentHTML(
    "beforeend",
    `<form id="quiz-form" style="margin-top:2em">
        <h3>Check Your Understanding</h3>
        ${quizHtml}
        <button type="button" class="btn-primary" onclick="submitQuiz()">Submit & Score My Quiz</button>
     </form>
     <button class="back-to-library" onclick="showTopicDetail('${lessonId}')" style="margin-top:1em;background:#6c757d">Cancel and Go Back</button>`
  );
}

/* Submit quiz */
async function submitQuiz() {
  const formData = new FormData($("#quiz-form"));
  const userAnswers = Object.fromEntries(formData.entries());
  views.results.innerHTML = "<h2>Scoring…</h2>";
  showView("results");
  try {
    const data = await post("/submit_quiz", {
      user_id: currentUser.uid,
      attempt_id: currentAttemptId,
      user_answers: userAnswers,
      lesson_id: currentLessonId,
    });
    currentLessonContext = data.content;
    renderResultsView(data, currentAttemptId);
  } catch (e) {
    views.results.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
window.submitQuiz = submitQuiz;

/* Render quiz RESULTS with Source Material Accordion */
/* Render quiz RESULTS with Source Material Accordion */
async function renderResultsView(data, attemptId) {
  const {
    lesson_id,
    content,
    user_answers,
    score,
    questions_total,
    smart_focus,
  } = data;

  // Start building the HTML
  let html = `<h2>Reviewing: ${content.title || "Lesson"}</h2>`;

  // Fetch and format the source material before rendering
  try {
    const src = await post("/get_source_material", {
      user_id: currentUser.uid,
      lesson_id: lesson_id,
    });
    // Build the accordion HTML as a string
    html += `
      <div class="accordion">
        <button class="accordion-head" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'block' ? 'none' : 'block'">Show Source Material</button>
        <div class="accordion-body" style="display: none;">${formatSourceMaterialAsHtml(
          src
        )}</div>
      </div>
    `;
  } catch (err) {
    console.warn("Accordion error:", err.message);
  }

  // Add the AI-Generated Lesson and Score Summary
  html += `
    <details class="lesson-accordion"><summary>Click to review AI-Generated Lesson</summary><div>${content.lesson_html}</div></details>
    <hr style="margin:2em 0">
    <div class="results-summary"><h3>Your Score: ${score} / ${questions_total}</h3></div>
  `;

  // Render the question-by-question results
  html += content.quiz_questions
    .map((q, i) => {
      const opts = normalizeOptions(q.options)
        .map((o, j) => {
          let cls = "option",
            icon = "⚪";
          if (j === q.correct_answer_index) {
            cls += " correct";
            icon = "✅";
          } else if (String(j) === user_answers[i]) {
            cls += " incorrect-selection";
            icon = "❌";
          }
          return `<div class="${cls}"><span class="icon">${icon}</span> ${o}</div>`;
        })
        .join("");
      return `<div class="results-question"><h4>${i + 1}. ${
        q.question
      }</h4><div class="results-options">${opts}</div><div class="explanation"><strong>Explanation:</strong> ${
        q.explanation
      }</div></div>`;
    })
    .join("");

  // Add the Smart Focus prompt if needed
  if (smart_focus?.smart_focus_needed) {
    const list = smart_focus.missed_concepts
      .map((c) => `<li><strong>${c}</strong></li>`)
      .join("");
    html += `
      <div class="smart-focus-prompt">
        <h3>💡 Smart Focus Opportunity</h3>
        <p>Looks like you struggled with:</p><ul>${list}</ul>
        <hr>
        <p><strong>Quick refresher:</strong> ${smart_focus.explanation}</p>
        <button id="generate-focus-lesson-btn">Generate a lesson on these</button>
      </div>`;
  }

  // Add the final action buttons
  html += `
    <div class="results-actions">
      <button onclick="showTopicDetail('${lesson_id}')">← Back to Topic</button>
      <button onclick="startLesson('${lesson_id}','${attemptId}')">Retake Quiz</button>
      <button class="delete-btn" onclick="deleteAttempt('${attemptId}','${lesson_id}')">Delete Attempt</button>
    </div>`;

  // Set the final HTML and add event listeners
  views.results.innerHTML = html;

  $("#generate-focus-lesson-btn")?.addEventListener("click", () =>
    startMultiConceptLesson(smart_focus.missed_concepts, lesson_id)
  );
}

/* Delete attempt */
async function deleteAttempt(attemptId, lessonId) {
  if (!confirm("Really delete this attempt?")) return;
  await post("/delete_attempt", {
    user_id: currentUser.uid,
    attempt_id: attemptId,
  });
  await initializeAppForUser(currentUser);
  showTopicDetail(lessonId);
}
window.deleteAttempt = deleteAttempt;

// Permanently deletes a custom topic and all its history
async function deleteCustomTopic(topicId, topicTitle) {
  if (
    !confirm(
      `Are you sure you want to permanently delete the topic "${topicTitle}" and all of your attempts? This cannot be undone.`
    )
  ) {
    return;
  }
  try {
    await post("/delete_custom_topic", {
      user_id: currentUser.uid,
      topic_id: topicId,
    });
    // Refresh the library view to show the topic is gone
    await initializeAppForUser(currentUser);
  } catch (e) {
    alert(`Failed to delete topic: ${e.message}`);
  }
}
window.deleteCustomTopic = deleteCustomTopic;

/* Review past attempt */
async function reviewLesson(attemptId) {
  views.results.innerHTML = "<h2>Loading…</h2>";
  showView("results");
  try {
    const data = await post("/get_lesson_attempt", {
      user_id: currentUser.uid,
      attempt_id: attemptId,
    });
    currentLessonContext = data.content;
    currentLessonId = data.lesson_id;
    renderResultsView(data, attemptId);
  } catch (e) {
    views.results.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
window.reviewLesson = reviewLesson;

/* ───── 7.  SMART-FOCUS LESSON ────────────────────────────────────────── */
async function startMultiConceptLesson(concepts, parentLessonId) {
  views.lesson.innerHTML = "<h2>Generating Focused Lesson…</h2>";
  showView("lesson");
  try {
    const data = await post("/start_multi_concept_lesson", {
      user_id: currentUser.uid,
      concepts,
      parent_lesson_id: parentLessonId,
    });
    currentAttemptId = data.attempt_id;
    currentLessonId = data.lesson_id;
    currentLessonContext = data.content;
    renderLesson(data.content, data.lesson_id);
  } catch (e) {
    views.lesson.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
window.startMultiConceptLesson = startMultiConceptLesson;

/* ───── 8.  FLASHCARDS (lesson & multi-topic) ─────────────────────────── */
function showCards(cards, heading) {
  $("#flash-modal")?.remove();
  const ov = el("div", "modal-ov");
  ov.id = "flash-modal";
  const md = el("div", "modal");
  md.append(el("h3", "", heading));

  const deck = el("div", "deck");
  cards.forEach((c) => {
    const card = el("div", "card");
    const front = el("div", "face front", c.question);
    const back = el("div", "face back", c.answer);
    card.append(front, back);
    card.onclick = () => card.classList.toggle("flip");
    deck.append(card);
  });
  md.append(deck);

  const exp = el("div", "export");
  const pdf = el("button", "btn-outline", "PDF");
  const xls = el("button", "btn-outline", "Spreadsheet");

  // FIX: Pass the button element to the export function for loading state
  pdf.onclick = (e) => exportCards("pdf", heading, e.target);
  xls.onclick = (e) => exportCards("xlsx", heading, e.target);

  exp.append(pdf, xls);
  md.append(exp);

  const closeBtn = el("button", "close", "×");

  // FIX: Make close button and background overlay work correctly
  closeBtn.onclick = () => ov.remove();
  ov.onclick = () => ov.remove();
  md.onclick = (e) => e.stopPropagation(); // Prevents click inside modal from closing it

  md.append(closeBtn);
  ov.append(md);
  document.body.append(ov);
}

async function genFlashcardsLesson() {
  // FIX: Add loading state to the button that was clicked ('this')
  const btn = this;
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating...";

  try {
    const { cards } = await post("/generate_flashcards_lesson", {
      user_id: currentUser.uid,
      attempt_id: currentAttemptId,
      count: 12,
    });
    FLASHCARDS = cards;
    showCards(cards, "Flashcards");
  } catch (e) {
    alert("Flashcard error: " + e.message);
  } finally {
    // Always restore the button after the attempt
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function genFlashcardsTopics(ids) {
  // FIX: Add loading state to the library flashcard button
  const btn = $("#library-flashcards-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating...";

  try {
    const { cards } = await post("/generate_flashcards_topics", {
      user_id: currentUser.uid,
      topic_ids: ids,
      count: 25,
    });
    FLASHCARDS = cards;
    showCards(cards, "Multi-Topic Flashcards");
  } catch (e) {
    alert("Flashcard error: " + e.message);
  } finally {
    // Always restore the button after the attempt
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function exportCards(format, title, btn) {
  // FIX: Add loading state to the export button
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Exporting...";

  try {
    const blob = await (
      await fetch("/export_flashcards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format, title, cards: FLASHCARDS }),
      })
    ).blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      title.replace(/\s+/g, "_") + (format === "pdf" ? ".pdf" : ".xlsx");
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Export failed: " + e.message);
  } finally {
    // Always restore the button after the attempt
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

/* ───── 9.  FINAL QUIZ (stateful) ─────────────────────────────────────── */
function showFinalQuizModal() {
  topicSelectionList.innerHTML = libraryData
    .map(
      (t) =>
        `<label><input type="checkbox" name="final-quiz-topic" value="${t.id}"> ${t.title}</label>`
    )
    .join("");
  finalQuizModal.style.display = "flex";
}
function hideFinalQuizModal() {
  finalQuizModal.style.display = "none";
}
async function generateFinalQuiz() {
  const selected = Array.from($$('input[name="final-quiz-topic"]:checked')).map(
    (c) => c.value
  );
  const count = parseInt(questionCountInput.value, 10);
  if (!selected.length) return alert("Select at least one topic.");
  if (count < 5 || count > 20) return alert("Request 5-20 questions.");

  hideFinalQuizModal();
  views.finalQuiz.innerHTML = "<h2>Generating Final Quiz…</h2>";
  showView("finalQuiz");

  try {
    const data = await post("/generate_final_quiz", {
      user_id: currentUser.uid,
      topic_ids: selected,
      question_count: count,
    });
    currentAttemptId = data.attempt_id;
    currentFinalQuizQuestions = data.quiz_questions;
    renderFinalQuizView(currentFinalQuizQuestions);
  } catch (e) {
    views.finalQuiz.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
function renderFinalQuizView(questions) {
  const shuffled = [...questions].sort(() => Math.random() - 0.5);
  const quizHtml = shuffled
    .map((q, i) => {
      const orig = questions.indexOf(q);
      const opts = normalizeOptions(q.options)
        .map(
          (o, j) =>
            `<label><input type="radio" name="${orig}" value="${j}" required><span>${o}</span></label>`
        )
        .join("");
      return `<div class="quiz-question"><h4>${i + 1}. ${
        q.question
      }</h4><div class="quiz-options">${opts}</div></div>`;
    })
    .join("");

  views.finalQuiz.innerHTML = `
    <h2>Cumulative Final Quiz</h2>
    <form id="final-quiz-form">${quizHtml}
      <button type="button" class="btn-primary" onclick="submitFinalQuiz()">Submit Final Quiz</button>
    </form>
    <button class="back-to-library" onclick="showView('library')" style="margin-top:1em;background:#6c757d">Cancel</button>`;
}
async function submitFinalQuiz() {
  const ans = Object.fromEntries(new FormData($("#final-quiz-form")).entries());
  views.finalQuiz.innerHTML = "<h2>Scoring…</h2>";
  showView("finalQuiz");
  try {
    const data = await post("/submit_final_quiz", {
      user_id: currentUser.uid,
      attempt_id: currentAttemptId,
      user_answers: ans,
    });
    renderFinalQuizResults(data);
  } catch (e) {
    views.finalQuiz.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
function renderFinalQuizResults(data) {
  const { quiz_questions, user_answers, score, questions_total, title } = data;
  let html = `<h2>Final Quiz Results: ${title}</h2>
              <div class="results-summary"><h3>Your Score: ${score}/${questions_total}</h3></div>`;

  html += quiz_questions
    .map((q, i) => {
      const opts = normalizeOptions(q.options)
        .map((o, j) => {
          let cls = "option",
            icon = "⚪";
          if (j === q.correct_answer_index) {
            cls += " correct";
            icon = "✅";
          } else if (String(j) === user_answers[i]) {
            cls += " incorrect-selection";
            icon = "❌";
          }
          return `<div class="${cls}"><span class="icon">${icon}</span> ${o}</div>`;
        })
        .join("");
      return `<div class="results-question"><h4>${i + 1}. ${
        q.question
      }</h4><div class="results-options">${opts}</div><div class="explanation"><strong>Explanation:</strong> ${
        q.explanation
      }</div></div>`;
    })
    .join("");

  html += `<button class="back-to-library" onclick="showView('library')" style="margin-top:2em">← Back to Library</button>`;
  views.finalQuiz.innerHTML = html;
}
window.renderFinalQuizView = renderFinalQuizView;

// ** OMISSION FIXED: This function was missing in the previous response **
async function reviewFinalQuiz(attemptId) {
  views.finalQuiz.innerHTML = "<h2>Loading Past Results...</h2>";
  showView("finalQuiz");
  try {
    const data = await post("/get_final_quiz_attempt", {
      user_id: currentUser.uid,
      attempt_id: attemptId,
    });
    renderFinalQuizResults(data);
  } catch (e) {
    views.finalQuiz.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
  }
}
window.reviewFinalQuiz = reviewFinalQuiz;

/* Final-quiz modal wiring */
generateFinalQuizBtn.addEventListener("click", generateFinalQuiz);
cancelFinalQuizBtn.addEventListener("click", hideFinalQuizModal);
selectAllTopicsCheckbox.addEventListener("change", (e) => {
  $$('input[name="final-quiz-topic"]').forEach(
    (c) => (c.checked = e.target.checked)
  );
});

/* ───── 10.  CREATE-TOPIC WORKFLOW ────────────────────────────────────── */
$("#create-topic-btn").onclick = async () => {
  const title = prompt("Enter a custom topic title:");
  if (!title) return;

  const btn = $("#create-topic-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Creating...";

  try {
    const data = await post("/create_custom_topic", {
      user_id: currentUser.uid,
      topic_title: title,
    });

    currentAttemptId = data.attempt_id;
    currentLessonId = data.lesson_id;
    currentLessonContext = data.content;

    // --- THIS IS THE FIX ---
    // Manually add the new topic to our local libraryData array.
    // This makes the "Cancel and Go Back" button work immediately without
    // needing to re-fetch the entire library from the server.
    libraryData.push({
      id: data.lesson_id,
      title: title,
      attempts: [], // It's a new topic, so it has no completed attempts yet.
    });

    renderLesson(data.content, data.lesson_id);
    showView("lesson");
  } catch (e) {
    alert(e.message);
    showView("library");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
};

/* ───── 11.  FLASHCARDS FROM LIBRARY (multi-topic) ────────────────────── */
function showFlashcardTopicModal() {
  flashcardTopicSelectionList.innerHTML = libraryData
    .map(
      (t) =>
        `<label><input type="checkbox" name="flashcard-topic" value="${t.id}"> ${t.title}</label>`
    )
    .join("");
  flashcardTopicModal.style.display = "flex";
}

// This new function hides the modal
function hideFlashcardTopicModal() {
  flashcardTopicModal.style.display = "none";
}

// This new function runs when the user clicks "Generate Flashcards" INSIDE the modal
async function generateFlashcardsFromModal() {
  const selectedIds = Array.from(
    $$('input[name="flashcard-topic"]:checked')
  ).map((c) => c.value);
  if (!selectedIds.length) {
    return alert("Please select at least one topic.");
  }

  hideFlashcardTopicModal(); // Close the modal
  await genFlashcardsTopics(selectedIds); // Call the existing generation function
}

// --- Event Listeners to wire everything up ---

// The main library button now calls the function to SHOW the modal
$("#library-flashcards-btn").onclick = showFlashcardTopicModal;

// The buttons inside the modal are now wired up
generateFlashcardsBtnModal.addEventListener(
  "click",
  generateFlashcardsFromModal
);
cancelFlashcardsBtnModal.addEventListener("click", hideFlashcardTopicModal);
selectAllFlashcardTopicsCheckbox.addEventListener("change", (e) => {
  $$('input[name="flashcard-topic"]').forEach(
    (c) => (c.checked = e.target.checked)
  );
});
/* ───── 12.  AI-TUTOR CHAT (unchanged) ────────────────────────────────── */
function toggleTutor() {
  const hidden =
    tutorChatContainer.style.display === "none" ||
    !tutorChatContainer.style.display;
  tutorChatContainer.style.display = hidden ? "flex" : "none";
}
window.toggleTutor = toggleTutor;

function addMessageToHistory(msg, type) {
  const m = el("div", `chat-message ${type}-message`, msg);
  tutorChatHistory.append(m);
  tutorChatHistory.scrollTop = tutorChatHistory.scrollHeight;
}
window.addMessageToHistory = addMessageToHistory;

async function sendTutorMessage() {
  const q = tutorInput.value.trim();
  if (!q || !currentLessonContext) return;
  addMessageToHistory(q, "user");
  tutorInput.value = "";
  addMessageToHistory("Typing…", "tutor");
  try {
    const { answer } = await post("/ask_tutor", {
      question: q,
      context: JSON.stringify(currentLessonContext),
    });
    tutorChatHistory.lastChild.remove(); // remove "Typing…"
    addMessageToHistory(answer, "tutor");
  } catch {
    tutorChatHistory.lastChild.remove();
    addMessageToHistory("Sorry, I had trouble connecting.", "tutor");
  }
}
window.sendTutorMessage = sendTutorMessage;
tutorInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendTutorMessage();
  }
});

/* ───── 13.  AUTH CONTROLS ───────────────────────────────────────────── */
$("#login-btn").addEventListener("click", () =>
  signInWithPopup(auth, new GoogleAuthProvider())
);
$("#logout-btn").addEventListener("click", (e) => {
  e.preventDefault();
  signOut(auth);
});

onAuthStateChanged(auth, async (user) => {
  loginContainer.style.display = user ? "none" : "block";
  appContainer.style.display = user ? "block" : "none";
  if (user) {
    const { needs_onboarding } = await post("/create_user", {
      uid: user.uid,
      displayName: user.displayName,
      email: user.email,
    });
    if (needs_onboarding) {
      window.location.href = "/onboarding";
      return;
    }
    userNameSpan.textContent = user.displayName || "User";
    await initializeAppForUser(user);
  } else {
    currentUser = null;
    libraryData = [];
  }
});

/* ───── 14.  BOOTSTRAP (nothing else to do) ──────────────────────────── */
console.log("Paramigo front-end initialised.");
