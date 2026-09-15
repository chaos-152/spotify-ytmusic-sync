# 🎵 Spotify ⇄ YouTube Music Sync: Beginner Installation & User Guide

> **Who is this guide for?**  
> Anyone who wants to transfer their playlists between Spotify and YouTube Music. You **do not** need to know any programming or computer science. If you can download a file and click buttons, you can use this tool!

---

## 📑 Quick Navigation
1. [What This Tool Does](#-what-this-tool-does)
2. [What You Need Before Starting](#-what-you-need-before-starting)
3. [Step 1: Download & Open the Project](#-step-1-download--open-the-project)
4. [Step 2: Start the Tool (The 1-Click Launchers)](#-step-2-start-the-tool-the-1-click-launchers)
5. [Step 3: Setting Up Your Free Google Connection (One-Time Setup)](#-step-3-setting-up-your-free-google-connection-one-time-setup)
6. [Step 4: How to Transfer Spotify → YouTube Music (Forward Sync)](#-step-4-how-to-transfer-spotify--youtube-music-forward-sync)
7. [Step 5: How to Transfer YouTube Music → Spotify (Reverse Sync)](#-step-5-how-to-transfer-youtube-music--spotify-reverse-sync)
8. [⚠️ Troubleshooting & Common Questions](#-troubleshooting--common-questions)

---

## 🎯 What This Tool Does

* **Spotify → YouTube Music:** Takes any Spotify playlist and recreates it in your YouTube Music library, matching songs with 99%+ accuracy (avoiding live versions, karaoke, or remix knockoffs).
* **YouTube Music → Spotify:** Takes any YouTube Music playlist, finds the exact matching tracks on Spotify, and gives you a file ready for 1-click import into Spotify.
* **100% Free:** No monthly fees, no subscription walls, and no track limits.

---

## 📋 What You Need Before Starting

1. A computer running **Windows**, **macOS**, or **Linux**.
2. **Python 3.10 or newer** installed on your computer.
   * *Don't have Python?* Download the official installer from [python.org/downloads](https://www.python.org/downloads/).  
   * ⚠️ **Important on Windows:** During installation, check the box that says **"Add Python to PATH"** before clicking Install.
3. A free **Google account** (the one you use for YouTube/YouTube Music).

---

## 🚀 Step 1: Download & Open the Project

1. Download the project ZIP directly from GitHub:  
   👉 **[Click here to directly download the project ZIP](https://github.com/chaos-152/spotify-ytmusic-sync/archive/refs/heads/main.zip)**
2. Find the downloaded file `spotify-ytmusic-sync-main.zip` in your Downloads folder.
3. Right-click it and choose **Extract All** (or double-click to open on Mac).
4. Open the extracted folder. You will see files like `run.bat`, `run.sh`, and folders named `backend` and `frontend`.

---

## ⚡ Step 2: Start the Tool (The 1-Click Launchers)

We created automated launchers that set up everything for you automatically:

### 🪟 If you are on Windows:
1. Double-click the file named **`run.bat`**.
2. A black terminal window will open and automatically prepare everything.
3. Your default web browser will automatically open to:  
   👉 **`http://127.0.0.1:8000`**

### 🍏 If you are on Mac or Linux:
1. Open the **Terminal** app.
2. Drag and drop the `run.sh` file into the terminal window (or type `bash run.sh`) and press **Enter**.
3. Your web browser will automatically open to:  
   👉 **`http://127.0.0.1:8000`**

> 💡 **Keep that terminal window open while using the app!** It acts as the local engine. When you are completely done using the app, you can simply close the terminal window.

---

## 🔑 Step 3: Setting Up Your Free Google Connection (One-Time Setup)

To allow the app to add playlists to your YouTube Music account without charging you anything, Google requires a free personal API key. This takes about **2 minutes**:

1. Open the app in your browser (**`http://127.0.0.1:8000`**).
2. In Section 1, click the grey button: **`⚙️ Setup Google Credentials`**.
3. Follow these 4 quick steps inside Google's free console:
   * Click the link in the popup to open **[Google Cloud Console](https://console.cloud.google.com/)** and sign in with your Google account.
   * Click **Select a project** at the top $\rightarrow$ click **New Project** $\rightarrow$ give it any name (e.g., `My Playlist Sync`) $\rightarrow$ click **Create**.
   * In the top search bar, search for **YouTube Data API v3** $\rightarrow$ click on it $\rightarrow$ click **Enable**.
   * On the left menu, click **OAuth consent screen**:
     * Select **External** $\rightarrow$ click **Create**.
     * Fill in an App name (e.g. `Sync`) and your email address $\rightarrow$ click **Save and Continue**.
     * Under the **Test users** section, click **+ Add Users** and type your own Gmail address $\rightarrow$ click **Save**.
   * On the left menu, click **Credentials** $\rightarrow$ click **+ Create Credentials** at the top $\rightarrow$ select **OAuth client ID**:
     * For *Application type*, choose **TVs and Limited Input devices**.
     * Click **Create**.
4. Google will show you a **Client ID** and a **Client Secret**.
5. Copy and paste them into the popup on your screen $\rightarrow$ click **Save & Configure**.
6. Click the blue button: **Connect YT Music**:
   * A link will appear: `https://www.google.com/device`. Click it.
   * Enter the 8-letter code shown on your screen and click Next.
   * ⚠️ **Google Warning Screen:** Google will say *"Google hasn't verified this app"*.  
     **This is completely normal and safe!** You are the author of this personal key. Simply click **Advanced**, then click **Go to [Project Name] (unsafe)**, and click **Allow**.
   * Return to your app tab — it will now say **Connected** in green!

---

## 📥 Step 4: How to Transfer Spotify → YouTube Music (Forward Sync)

1. Open **[exportify.net](https://exportify.net)** in a new tab.
2. Log into your Spotify account and click **Export** next to any playlist you want to move. It will download a clean `.csv` file to your Downloads folder.
3. Go back to our sync app in your browser.
4. Drag and drop the downloaded `.csv` file into the box in **Section 2**.
5. The playlist name will automatically fill in. Click **Import**.
6. Scroll to **Section 3 ("Your imported playlists")**:
   * *(Optional)* Click **Pre-Sync Preview** to see the exact songs matched, confidence scores, and preview albums before anything touches your YouTube account.
   * Click **Sync now**.
7. Watch the live progress bar! Once finished, a button will appear: **`Open in YT Music ↗`** — click it to see your new playlist directly inside YouTube Music!

---

## 📤 Step 5: How to Transfer YouTube Music → Spotify (Reverse Sync)

Want to move a playlist back into Spotify?

### Step 5A: Set Up Spotify Credentials
1. In the **Move to Spotify** tab, click **`⚙️ Spotify Credentials`**.
2. Click the link to open **[developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)** and log in with your Spotify account.
3. Click **Create App**, give it any name, and under **Redirect URIs**, add:  
   👉 **`http://127.0.0.1:8000/api/spotify/callback`**  
   *(⚠️ Note: Spotify strictly requires the numeric `127.0.0.1` literal; `localhost` is rejected).*
4. Copy the **Client ID** and **Client Secret**, paste them into the popup in our app, and click **Save & Configure**.
5. *(Optional for Direct Sync)* Click **Connect Spotify Account** to allow 1-click playlist creation directly in your library without needing CSV files!

### Step 5B: Put the Tracks into Spotify (Two Easy Ways)

* **Option 1 (Fastest — Spotify Desktop App):**
  1. Open the downloaded CSV file in any text editor or Excel.
  2. Select and copy the list of Spotify URIs (e.g. `spotify:track:4cOdK...`).
  3. Open the Spotify desktop application on your computer.
  4. Create a new empty playlist, click anywhere inside the playlist song area, and press **Ctrl+V** (or **Cmd+V** on Mac).
  5. Spotify natively pastes all tracks into your playlist instantly!

* **Option 2 (Web Importer — Spotlistr):**
  1. Go to **[spotlistr.com](https://www.spotlistr.com)** and log into your Spotify account.
  2. Choose the **Textbox** or **Upload File** tool.
  3. Paste the list of URIs or upload your CSV. Spotlistr adds the verified tracks to a new Spotify playlist for you in 1 click.

> ℹ️ **Note on the Free Fallback (No Spotify Keys):** If you don't configure Spotify developer credentials, you can export a raw text CSV (Song Title + Artist). You can still upload that raw file into Spotlistr or Soundiiz, but please note that the matching will be handled by their internal search engine rather than our 11-factor precision engine.

---

## ⚠️ Troubleshooting & Common Questions

#### Q: After 7 days, my YouTube Music says "Session expired"?
> **Why it happens:** Because your Google Cloud project is in personal "Testing" mode, Google automatically refreshes the authorization token for 7 days.  
> **Fix:** Simply click **Connect YT Music**, open `google.com/device`, and enter the fresh code. It takes 10 seconds and all your playlists stay intact!

#### Q: The browser didn't open automatically when I ran `run.bat` or `run.sh`?
> **Fix:** Open any web browser (Chrome, Edge, Safari, Firefox) and type `http://127.0.0.1:8000` into the address bar.

#### Q: Do my friends need their own Spotify Premium or Google accounts?
> * **For Forward Sync (Spotify → YouTube Music):** It is 100% free for everyone. No Spotify Premium is ever required.
> * **For YouTube connection:** Each person should configure their own free Google Client ID using the 2-minute guide in Step 3 so they don't hit Google's 100-user cap.

#### Q: When clicking "Sync Directly to Spotify", it fails with "403: Forbidden"?
> **Does this require Spotify Premium?** No! Spotify Free accounts can create playlists and add tracks via the API without paying a dime.
> **Why it happens:** When you create an app on the Spotify Developer Dashboard, it starts in **Development Mode**. In Development Mode, Spotify restricts API write actions to:
> 1. The developer account that created the Spotify App.
> 2. Up to 5 additional Spotify accounts explicitly added under **User Management** in the Spotify Developer App dashboard.
> 
> **Fix:**
> 1. Open [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and click your app.
> 2. Click **User Management** (in the top menu or app settings).
> 3. Click **Add User**, enter the user's name and the exact email address associated with their Spotify account, and click Save.
> 4. Log in again with **Connect Spotify Account** and Direct Sync will work immediately!
> *(Alternatively, you can skip Direct Sync entirely: click **Download CSV**, select the Spotify URIs, and press **Ctrl+V** inside the Spotify Desktop app!)*

#### Q: Where are my playlists saved?
> All your imported playlists, tracks, and sync history are saved locally on your own computer in `backend/app.db`. Nothing is sent to any external server.

