This guide will walk you through installing and running CalPal – a Telegram bot that turns casual messages into Google Calendar events using Google’s Gemini AI.

📋 What You’ll Need
A Windows / macOS / Linux computer

A Google account (for Calendar & Gemini)

A Telegram account (for the bot)

About 15 minutes of your time

🧰 Step 1 – Install Python
Go to python.org/downloads

Download the latest Python 3.11 or 3.12 installer.

Run the installer.
✅ Check the box “Add Python to PATH”
✅ Make sure “pip” is selected

Finish the installation.

To verify, open a terminal (Command Prompt or PowerShell) and type:

bash
python --version
You should see something like Python 3.12.x.

📥 Step 2 – Download the Bot Code
Go to the GitHub repo:
https://github.com/omg-o/calander_bot

Click the green “Code” button → Download ZIP.

Extract the ZIP file to a folder, e.g. C:\Users\YourName\Desktop\calander_bot.

Open that folder.

🖥️ Step 3 – Open the Project in VS Code (Recommended)
If you don’t have VS Code, download it from code.visualstudio.com.

Open VS Code.

Click File → Open Folder… → select the calander_bot folder.

Inside VS Code, open a new terminal:
Terminal → New Terminal (or press Ctrl + ``).

🐍 Step 4 – Create a Virtual Environment
In the VS Code terminal, type:

bash
python -m venv .venv
Activate it:

Windows (PowerShell / CMD):

bash
.venv\Scripts\activate
macOS / Linux:

bash
source .venv/bin/activate
Your terminal prompt should now start with (.venv).

📦 Step 5 – Install Dependencies
Make sure you’re in the calander_bot folder (the one with requirements.txt).
Then run:

bash
pip install -r requirements.txt
Wait for everything to install – you’ll see a “Successfully installed …” message.

🔑 Step 6 – Get Your Telegram Bot Token
Open Telegram and search for BotFather.

Send the command /newbot and follow the instructions:

Give your bot a name (e.g., “My CalPal”)

Give it a username (must end with bot, e.g., mycalpal_bot)

BotFather will reply with a token – it looks like:
8899572206:AAG93Nc_AiGqnOVFgvlnrkp6OiWMagxokGA
Copy this token! You’ll need it soon.

🧠 Step 7 – Get a Gemini API Key
Go to Google AI Studio.

Sign in with your Google account.

Click “Create API key”.

Choose “Create API key in new project” (or select an existing project).

Copy the key – it looks like AIza….

⚠️ Important: You must also enable the API service:

Visit the Google Cloud Console.

Make sure the same project is selected.

Go to APIs & Services → Library.

Search for “Generative Language API” and click Enable.

📅 Step 8 – Enable Google Calendar API & Get OAuth Credentials
Go to Google Cloud Console.

Select your project (the one from the previous step).

Navigate to APIs & Services → Library.

Search for “Google Calendar API” → click Enable.

Now go to APIs & Services → Credentials.

Click Create Credentials → OAuth client ID.

Set Application type to “Desktop app”, give it a name (e.g., “CalPal Bot”).

Click Create. A dialog with client ID and secret appears – click Download JSON.

Rename the downloaded file to credentials.json.

Move this credentials.json file into your calander_bot folder (next to bot.py).

⚙️ Step 9 – Configure Environment Variables
In the calander_bot folder, create a new file named .env (exactly this, no extension).
Open it in VS Code and paste:

text
TELEGRAM_TOKEN=8899572206:AAG93Nc_AiGqnOVFgvlnrkp6OiWMagxokGA
GEMINI_API_KEY=AIza...your_gemini_key_here
Replace the token and key with the ones you copied earlier.
No quotes, no spaces around =.

Save the file.

🔐 Step 10 – Authenticate Your Google Account
In the VS Code terminal (with the virtual environment active), run:

bash
python get_token.py
A browser window will open asking you to log in to your Google account.

Grant calendar access.

After you accept, the terminal will say “token.json saved”.
A file token.json will appear in your project folder – this is your permanent calendar access.

🚀 Step 11 – Run the Bot!
In the same terminal, run:

bash
python bot.py
You should see:

text
2026-08-12 ... - Bot started. Press Ctrl+C to stop.
Now go to Telegram, find your bot (by its username), and start a chat.

📱 Step 12 – Test It
Send the bot a message like:

Interview on 15th August at 2pm

Doctor appointment tomorrow morning

Team standup every weekday at 9am

The bot will:

Extract the details using Gemini

Ask you to confirm

Create the event in your Google Calendar 🎉
