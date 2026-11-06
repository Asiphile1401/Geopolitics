# Geopolitics Game

Geopolitics Game is a web-based strategy game built with Flask. Choose a country and compete to conquer the other territories against computer-controlled opponents. You can save and return to multiple games, and follow each match through its event log. Optional AI-powered battle commentary is available when an AI service is configured.

## Run the project

You need Python 3.11 or newer and a MongoDB database. MongoDB Atlas works without installing MongoDB locally.

1. Open a terminal in the project folder and create a virtual environment:

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS or Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install the project dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

3. Create a `.env` file in the project folder and add your MongoDB connection string and a secret key:
   ```text
   MONGO_URI=your_mongodb_connection_string
   SECRET_KEY=your_long_random_secret_key
   ```

   `MONGO_URI` is required for the application to start. AI commentary
    set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` in `.env` to use an OpenAI-compatible service. Without these settings, the game uses offline commentary.

4. Start the app:
   ```bash
   python app.py
   ```

5. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser, then register or sign in to play.
