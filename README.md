# Paramigo Project Summary & State

**Date:** June 23, 2025
**Project ID:** `paramigo-tool-03`
**Status:** The core application and the final quiz feature are fully functional. The primary learning loop (Library -> Lesson -> Quiz -> Results -> Smart Focus) is complete, and a cumulative testing mechanism with history is now in place. The application is robust and ready for production preparation or new feature development.

## 1. Project Overview

**Paramigo** is a personalized, adaptive learning tool designed to train new financial advisors. It transforms a library of existing training content (from Google Docs) into an interactive, persistent learning experience.

The core user experience is a web application where an advisor can:

1.  Log in securely with their Google account.
2.  Choose a learning style during a one-time onboarding, which can be changed later.
3.  Browse a library of training topics and a history of past final quizzes.
4.  Select a topic to view its history or start a new lesson attempt.
5.  Take an AI-generated lesson tailored to their learning style.
6.  Complete a quiz and review their score, question-by-question explanations, and the original lesson content.
7.  If they struggled on a lesson, they are offered a "Smart Focus" opportunity to generate a new, consolidated lesson covering their weak points.
8.  Create, take, and review **Final Cumulative Quizzes** that test knowledge across multiple topics. These final quizzes also have their own persistent history and can be retaken.
9.  All lesson attempts (regular, focused, and final) are saved to the user's history.
10. An "Ask Tutor" feature is available for specific questions during lessons and reviews.

## 2. Architecture

The application uses a client-server architecture with a clear separation of concerns:

- **Frontend (Client-Side):** A single-page application (SPA) experience built with vanilla HTML, CSS, and modern JavaScript (`type="module"`). It manages all UI views dynamically without full page reloads. It is served by the Flask backend but handles all Firebase Authentication on the client side.
- **Backend (Server-Side):** A Python application built with the **Flask** web framework, acting as an API server. It provides data endpoints that the frontend calls to get information or trigger actions. Key responsibilities include:
  - Serving the main `index.html` shell and `onboarding.html` page.
  - Providing API endpoints like `/get_library_and_history`, `/submit_quiz`, `/generate_final_quiz`, and `/submit_final_quiz`.
  - Communicating securely with Google Cloud services (Firestore and Google AI).
- **Database:** **Google Cloud Firestore** in Native Mode acts as our primary database. It is structured into collections:
  - `ContentMaster`: Stores the structured, parsed content from all Google Docs lessons. This is our single source of truth for all training material.
  - `Users`: Stores a profile for each authenticated user, keyed by their Firebase UID. Each user document contains two subcollections:
    - `lesson_attempts`: Stores a permanent record of every single-topic lesson they take (regular and Smart Focus).
    - `final_quiz_attempts`: Stores a permanent record of every cumulative final quiz they take.

## 3. Tech Stack

- **Backend Language:** Python 3
- **Web Framework:** Flask
- **Frontend Languages:** HTML5, CSS3, JavaScript (ESM)
- **Database:** Google Cloud Firestore (NoSQL)
- **Authentication:** Firebase Authentication
- **AI / Generative Models:** Google AI Platform (Gemini 1.5 Flash via `google-generativeai`)
- **Cloud Platform:** Google Cloud Platform (GCP) & Firebase
- **Key Python Libraries:** `flask`, `google-cloud-firestore`, `google-generativeai`, `python-dotenv`
- **Key Frontend Libraries:** `firebase-app.js`, `firebase-auth.js` (v10 Modular SDK)

## 4. Features Implemented So Far

- **Automated Content Pipeline:** A `parser.py` script connects to Google Drive, parses linked Google Docs, and uploads structured content to the `ContentMaster` collection in Firestore.
- **User Authentication & Onboarding:** Robust "Sign in with Google" via Firebase. New users are directed to a one-time onboarding page to select a learning style.
- **Structured Learning Flow:** The main page shows a library of all topics. Clicking a topic opens a "detail" view showing its specific history and an option to start a new attempt.
- **Intelligent "Smart Focus" Generation:** After a regular quiz, the system identifies missed concepts and uses the AI to generate a holistic summary and a button to create a new, consolidated lesson on those weak points.
- **Quiz and History Management:**
  - **Retake Quiz:** Users can retake any regular or final quiz. This creates a new attempt using the exact same questions as the original but shuffles the question order.
  - **Delete Attempt:** Users can permanently delete any past _regular lesson_ attempt from their history.
- **AI Tutor:** A floating chat window allows users to ask questions about the current lesson content.
- **Final Cumulative Quizzes (Stateful):**
  - **Topic Selection:** A modal allows users to select multiple topics for a cumulative quiz, with a "Select All / Deselect All" option for convenience.
  - **AI Generation:** A dedicated backend endpoint (`/generate_final_quiz`) fetches content for all selected topics and uses the AI to generate a unique, consolidated quiz.
  - **Persistent History:** Each final quiz attempt is saved to a dedicated `final_quiz_attempts` collection in Firestore, appearing in a "Final Quiz History" section on the main library page.
  - **Review & Retake:** Users can review past final quiz results and retake any final quiz, just like a regular lesson.

## 5. Outstanding Tasks or Next Steps

The core application is functionally complete and refined. The logical next steps would focus on production readiness or adding major new features.

- **Production Deployment:** Configure the application to run on a production-grade WSGI server (like Gunicorn) and host it on a service like Google App Engine or Cloud Run.
- **UI/UX Refinement:** Further polish the CSS, improve loading states, and potentially add more engaging animations or transitions between views.
- **Enhanced User Dashboard:** The "Topic Detail" view could be expanded into a full dashboard showing metrics like overall score average, most challenging topics, and progress over time.
- **Content Versioning:** Implement a feature where users are notified if a lesson they completed has been updated in the `ContentMaster` library.

## 6. Important Design Decisions

- **Stateful Backend / Generate-and-Store Model:** We deliberately chose to store every lesson attempt and final quiz in the database. This enables a rich, persistent user history at the cost of increased database storage.
- **Client-Side View Management:** The frontend acts as a Single-Page Application (SPA), providing a faster, more fluid user experience.
- **Integrated History:** We decided to associate "Smart Focus" lessons with the parent topic's ID to keep the history organized. Final quizzes have their own separate history list on the main page.
- **Frontend Resilience (The Radio Button Fix):** We implemented a `normalizeOptions()` helper function in the frontend JavaScript. This function defensively checks if the quiz options received from the AI are a string instead of an array, and if so, it intelligently parses the string into a proper array. This makes the UI resilient to malformed AI responses and prevents rendering bugs.
- **Stateful Final Quizzes:** We made a key decision to make the Final Quiz feature stateful, giving it its own history, review, and retake capabilities, which mirrors the functionality of regular lessons and makes the feature much more useful.

## 7. Assumptions or Constraints

- **Assumption:** The source Google Docs will maintain a consistent structure that the `parser.py` script can rely on.
- **Constraint:** The application is currently configured for local development and has not been hardened or optimized for a production environment.
- **Constraint:** The AI model (Gemini 1.5 Flash) is fast and cost-effective but may occasionally produce malformed JSON. Our `normalizeOptions()` frontend function and `_normalise_ai_json()` backend function are designed to mitigate these issues.

## 8. Naming Conventions and Folder Structure

The project is organized in a standard Flask structure:

```
paramigo/
├── static/
│   └── style.css         # All CSS styles
├── templates/
│   ├── index.html        # The single HTML shell for the entire app
│   └── onboarding.html   # The learning style selection page
├── .env                  # Stores secret keys (e.g., GOOGLE_API_KEY)
├── app.py                # Main Flask web server and all API endpoints
└── ...                   (other files like parser.py, client_secret.json, etc.)
```

- **API Routes:** Backend routes are prefixed with `/` and follow a clear verb-noun structure (e.g., `/get_library_and_history`, `/generate_final_quiz`).
- **CSS/JS:** All CSS is in `static/style.css`. All JavaScript is contained within a single `<script type="module">` block in `index.html`.

## 9. Anything Else Important to Carry Forward

The most critical lesson learned during development has been the need for a resilient frontend that does not blindly trust the structure of API responses, especially from a generative AI.

- The implementation of the `normalizeOptions()` function is a prime example of this lesson and a pattern we should remember. It defensively checks and cleans incoming data at the point of rendering, preventing UI bugs.
- Debugging by printing the raw AI response in the backend terminal remains the most effective strategy for solving generation issues.

## 10. My preferred working style and rules to remember about how I like to work together

- **DO NOT LIE. DO NOT OMIT CODE.** This is the most important rule. You must provide the complete, top-to-bottom code for every file you are asked to produce. Do not use placeholders, summaries, or comments like "Omitted for brevity." This is a critical matter of trust and functionality.
- **Be Honest About Mistakes:** If I ask if you omitted something, be truthful. It is better to admit a mistake and fix it than to deny it.
- **Structure and Clarity:** I prefer a step-by-step, methodical approach. The "Plan -> Action -> What to Do Next" format works well.
- **Complete Files:** When providing code, always provide the entire file content, not just the changed snippets. This prevents copy-paste errors and ensures we are always working from a complete and correct baseline.
- **Acknowledge the User's Frustration:** When a bug is persistent or a mistake is repeated, it's important to acknowledge the user's frustration and the severity of the issue before moving on to the solution.
