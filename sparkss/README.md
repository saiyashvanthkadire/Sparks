# Streak Spark

Streak Spark is a personal wellness and productivity web application built with Flask. It includes AI-powered features for analyzing images for health insights and providing food recommendations based on your mood, weather, and health goals.

## Features

-   **User Authentication**: Secure login and signup system using Firebase Authentication.
-   **AI Medical Assist**: Upload an image (e.g., of a skin condition) and get a descriptive analysis from an AI model (GPT-4o). *Disclaimer: This is for educational purposes only and is not a medical diagnosis.*
-   **AI Food Assist**: Get personalized food recommendations based on your current mood, the weather, and your health goals.
-   **Save for Later**: Save AI-generated food recommendations as notes in your personal dashboard.
-   **Daily Planner**: Manage daily tasks, habits, and notes.

## Tech Stack

-   **Backend**: Python, Flask
-   **Frontend**: HTML, CSS, JavaScript
-   **Database**: Google Firestore for application data.
-   **AI**: OpenAI API (GPT-4o) for image analysis and recommendations.
-   **Authentication**: Firebase Authentication.

## Setup and Installation

Follow these steps to get the application running locally.

### 1. Clone the Repository

First, initialize a git repository and commit these files. Then you can push it to a remote repository like GitHub.

```bash
git init
git add .
git commit -m "Initial commit"
```

### 2. Create a Virtual Environment

It's recommended to use a virtual environment to manage project dependencies.

```bash
# For Windows
python -m venv venv
venv\Scripts\activate

# For macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Install all the required Python packages using pip.

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

The application requires several API keys and configuration variables. Create a file named `.env` in the root of the project directory and add the following, replacing the placeholder values with your actual credentials.

```env
# Flask
FLASK_SECRET_KEY='a_very_secure_random_string'

# OpenAI
OPENAI_API_KEY='sk-...'

# Firebase
# You can get these from your Firebase project settings
FIREBASE_WEB_API_KEY='...'
FIREBASE_PROJECT_ID='your-firebase-project-id'

# Path to your Firebase service account JSON file.
# Download this from Project Settings > Service accounts in your Firebase console.
FIREBASE_SERVICE_ACCOUNT_PATH='path/to/your/serviceAccountKey.json'
```

### 5. Run the Application

Start the Flask development server.

```bash
flask run
```

The application will be available at `http://127.0.0.1:5000`.
