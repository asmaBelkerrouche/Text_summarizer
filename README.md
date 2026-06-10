markdown

# <p align="center">Text Summarizer</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-ff69b4.svg">
  <img src="https://img.shields.io/badge/Flask-3.0.0-pink.svg">
  <img src="https://img.shields.io/badge/SpaCy-3.7.2-hotpink.svg">
  <img src="https://img.shields.io/badge/Made%20with-Love-ff1493.svg">
</p>

<p align="center">
  <b>Turn long text into short, sweet summaries</b>
  <br>
  <i>Fast • Production-Ready</i>
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| Text Summarization | TextRank + LSA algorithms |
| File Upload | PDF, DOCX, TXT support |
| URL Extraction | Summarize any article |
| Keyword Extraction | Automatic topic detection |
| Dark/Light Mode | Eye-friendly interface |
| Caching | 10x faster repeated requests |

---

## Quick Start

```bash
# 1. Clone & enter
git clone https://github.com/asmaBelkerrouche/text-summarizer.git
cd text-summarizer

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download SpaCy model
python -m spacy download en_core_web_sm

# 5. Run
python app.py

Open: http://localhost:5000
API Endpoints
bash

POST /api/summarize      # Text summarization
POST /api/summarize-file # File upload
POST /api/summarize-url  # URL extraction
GET  /api/health         # Health check

Tech Stack

    Flask - Backend framework

    SpaCy + TextRank - NLP summarization

    scikit-learn - LSA algorithm

    Flask-Caching - Performance boost

    HTML/CSS/JS - Modern UI

Performance
Text Size	Time	Cached
200 words	0.3s	0.05s
1000 words	0.8s	0.05s
5000 words	2.1s	0.05s



MIT © esloqeeus
