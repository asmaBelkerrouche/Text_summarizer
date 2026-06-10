import os
import re
import uuid
import hashlib
import time
from datetime import datetime
from pathlib import Path
from functools import lru_cache, wraps

from flask import Flask, render_template, request, jsonify, g
from flask_cors import CORS
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from dotenv import load_dotenv
import spacy
import pytextrank
import nltk
import requests
from bs4 import BeautifulSoup
import PyPDF2
import pdfplumber
from docx import Document
import tiktoken

# Download required NLTK data
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('punkt_tab', quiet=True)

load_dotenv()

app = Flask(__name__)
CORS(app)

# ==================== PERFORMANCE CONFIGURATION ====================
# Compression for faster network transfer
Compress(app)

# Cache configuration (10x speedup for repeated texts)
cache_config = {
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutes
    'CACHE_THRESHOLD': 100  # Max 100 items in cache
}
cache = Cache(app, config=cache_config)

# Rate limiting (prevent abuse) - FIXED SYNTAX
limiter = Limiter(
    get_remote_address,  # This should be the first positional argument
    app=app,
    default_limits=["100 per minute", "1000 per hour"],
    storage_uri="memory://"
)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year

# Create necessary folders
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)

# ==================== LOAD OPTIMIZED MODELS ====================
print("Loading optimized NLP models...")
start_time = time.time()

# Load SpaCy with minimal components for speed
try:
    # Load only what we need (faster loading)
    nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "attribute_ruler"])
    nlp.add_pipe("textrank", last=True)
    print(f"✓ SpaCy + TextRank loaded in {time.time() - start_time:.2f}s")
except Exception as e:
    print(f"⚠ Error loading SpaCy: {e}")
    print("Please run: python -m spacy download en_core_web_sm")
    nlp = None

# Token counter
try:
    tokenizer = tiktoken.get_encoding("cl100k_base")
    print("✓ Tokenizer loaded")
except:
    tokenizer = None

print(f"✓ Total startup time: {time.time() - start_time:.2f}s")

# ==================== PERFORMANCE DECORATORS ====================

def timing_decorator(f):
    """Measure function performance"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        elapsed = time.time() - start
        print(f"⚡ {f.__name__} took {elapsed:.3f}s")
        return result
    return wrapper

def get_text_hash(text):
    """Generate hash for caching"""
    return hashlib.md5(text.encode()[:10000]).hexdigest()  # Hash first 10k chars only

# ==================== OPTIMIZED TEXT PROCESSING ====================

def clean_text(text):
    """Ultra-fast text cleaning"""
    # One-pass regex for speed
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s\.\!\?\,]', '', text)
    return text.strip()[:50000]  # Limit to 50k chars for performance

def extract_text_from_pdf(file_path):
    """Fast PDF extraction"""
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            # Process only first 50 pages for speed
            for page in pdf.pages[:50]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                if len(text) > 100000:  # Stop at 100k chars
                    break
    except Exception as e:
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages[:50]:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                    if len(text) > 100000:
                        break
        except Exception as e2:
            return ""
    return text[:100000]  # Limit size

def extract_text_from_docx(file_path):
    """Fast DOCX extraction"""
    try:
        doc = Document(file_path)
        text = '\n'.join([p.text for p in doc.paragraphs[:200] if p.text.strip()])
        return text[:50000]
    except Exception as e:
        return ""

def extract_text_from_url(url):
    """Fast URL extraction with timeout"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, timeout=5, headers=headers)  # 5s timeout
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove junk elements fast
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()
        
        # Get paragraphs quickly
        text_parts = []
        for tag in soup.find_all(['p', 'article'])[:50]:  # Limit to 50 tags
            text = tag.get_text(strip=True)
            if len(text) > 50:
                text_parts.append(text)
        
        if text_parts:
            text = ' '.join(text_parts)
        else:
            text = soup.get_text()
        
        title = soup.title.string if soup.title and soup.title.string else "Untitled"
        
        # Clean once
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text[:50000], title[:200]
    except Exception as e:
        raise Exception(f"URL extraction failed: {str(e)}")

# ==================== OPTIMIZED SUMMARIZATION ====================

@timing_decorator
def summarize_textrank(text, ratio=0.3):
    """Ultra-fast TextRank summarization"""
    if not nlp:
        return "Error: NLP model not loaded"
    
    words = text.split()
    if len(words) < 30:
        return text
    
    try:
        # Speed optimization: limit text length
        max_chars = 30000  # Process max 30k chars
        if len(text) > max_chars:
            # Take first 30k chars + last 10k chars (preserves intro and conclusion)
            text = text[:max_chars] + text[-10000:]
        
        # Process text
        doc = nlp(text)
        
        # Get summary
        summary_sentences = list(doc._.textrank.summary(limit_ratio=ratio))
        
        if not summary_sentences:
            sentences = list(doc.sents)[:50]  # Limit to 50 sentences
            num_sentences = max(1, int(len(sentences) * ratio))
            summary_sentences = sentences[:num_sentences]
        
        summary = ' '.join([sent.text.strip() for sent in summary_sentences])
        return summary if summary else text[:500]
    except Exception as e:
        # Ultra-fast fallback
        sentences = text.split('. ')[:30]
        num_sentences = max(1, int(len(sentences) * ratio))
        return '. '.join(sentences[:num_sentences]) + '.'

@timing_decorator
def summarize_lsa(text, ratio=0.3):
    """Fast LSA summarization with caching"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        import numpy as np
        
        # Fast sentence splitting
        sentences = [s.strip() for s in text.replace('!', '.').replace('?', '.').split('. ') 
                    if 20 < len(s.strip()) < 500][:100]  # Limit to 100 sentences
        
        if len(sentences) <= 3:
            return ' '.join(sentences[:3]) + '.'
        
        # Optimized TF-IDF
        vectorizer = TfidfVectorizer(stop_words='english', max_features=500, max_df=0.8)
        tfidf_matrix = vectorizer.fit_transform(sentences)
        
        num_topics = min(2, len(sentences) - 1)
        if num_topics < 1:
            return sentences[0]
        
        svd = TruncatedSVD(n_components=num_topics, random_state=42)
        svd_matrix = svd.fit_transform(tfidf_matrix)
        
        scores = np.sum(svd_matrix, axis=1)
        num_sentences = max(1, int(len(sentences) * min(ratio, 0.5)))  # Cap at 50%
        top_indices = scores.argsort()[-num_sentences:][::-1]
        top_indices = sorted(top_indices)
        
        return '. '.join([sentences[i] for i in top_indices]) + '.'
    except Exception as e:
        return summarize_textrank(text, min(ratio, 0.5))

@timing_decorator
def extract_keywords(text, top_n=8):
    """Fast keyword extraction"""
    if not nlp or len(text) < 100:
        return []
    
    try:
        doc = nlp(text[:3000])  # Process only first 3k chars
        keywords = set()
        
        # Fast entity extraction
        for ent in doc.ents:
            if ent.label_ in ['PERSON', 'ORG', 'GPE', 'PRODUCT'] and len(ent.text) > 2:
                keywords.add(ent.text)
            if len(keywords) >= top_n:
                break
        
        # Add important noun chunks if needed
        if len(keywords) < top_n:
            for chunk in doc.noun_chunks:
                if 2 <= len(chunk.text.split()) <= 4:
                    if any(token.pos_ == 'PROPN' for token in chunk):
                        keywords.add(chunk.text)
                    if len(keywords) >= top_n:
                        break
        
        return list(keywords)[:top_n]
    except Exception:
        return []

# ==================== CACHED FLASK ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/summarize', methods=['POST'])
@limiter.limit("30 per minute")
def summarize_text():
    """Cached, rate-limited summarization endpoint"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        method = data.get('method', 'textrank')
        ratio = float(data.get('ratio', 0.3))
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Quick validation
        text = clean_text(text)
        word_count = len(text.split())
        
        if word_count < 20:
            return jsonify({'error': 'Minimum 20 words required'}), 400
        if word_count > 15000:
            return jsonify({'error': 'Maximum 15,000 words'}), 400
        
        # Check cache manually
        cache_key = f"summary_{hashlib.md5(text.encode()[:10000]).hexdigest()}_{method}_{ratio}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            cached_result['cached'] = True
            return jsonify(cached_result)
        
        # Process based on method
        if method == 'lsa':
            summary = summarize_lsa(text, ratio)
        else:
            summary = summarize_textrank(text, ratio)
        
        keywords = extract_keywords(text)
        
        original_words = word_count
        summary_words = len(summary.split())
        compression = round((1 - summary_words/original_words) * 100, 1) if original_words > 0 else 0
        
        result = {
            'success': True,
            'summary': summary,
            'original_length': original_words,
            'summary_length': summary_words,
            'compression': compression,
            'keywords': keywords,
            'method_used': method,
            'cached': False
        }
        
        # Store in cache
        cache.set(cache_key, result)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/summarize-file', methods=['POST'])
@limiter.limit("10 per minute")
def summarize_file():
    """File upload with fast processing"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        method = request.form.get('method', 'textrank')
        ratio = float(request.form.get('ratio', 0.3))
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        ext = file.filename.rsplit('.', 1)[-1].lower()
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.{ext}")
        file.save(temp_path)
        
        # Quick extraction
        if ext == 'pdf':
            text = extract_text_from_pdf(temp_path)
        elif ext == 'docx':
            text = extract_text_from_docx(temp_path)
        elif ext == 'txt':
            with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read(100000)  # Read max 100k chars
        else:
            os.remove(temp_path)
            return jsonify({'error': f'Unsupported file type: {ext}'}), 400
        
        os.remove(temp_path)
        
        if not text or len(text.split()) < 20:
            return jsonify({'error': 'Could not extract enough text'}), 400
        
        text = clean_text(text)
        
        if method == 'lsa':
            summary = summarize_lsa(text, ratio)
        else:
            summary = summarize_textrank(text, ratio)
        
        keywords = extract_keywords(text)
        
        return jsonify({
            'success': True,
            'summary': summary,
            'original_length': len(text.split()),
            'summary_length': len(summary.split()),
            'compression': round((1 - len(summary.split())/len(text.split())) * 100, 1),
            'keywords': keywords,
            'filename': file.filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/summarize-url', methods=['POST'])
@limiter.limit("20 per minute")
def summarize_url():
    """URL summarization with timeout"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        method = data.get('method', 'textrank')
        ratio = float(data.get('ratio', 0.3))
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        text, title = extract_text_from_url(url)
        
        if len(text.split()) < 20:
            return jsonify({'error': 'Not enough content from URL'}), 400
        
        text = clean_text(text)
        
        if method == 'lsa':
            summary = summarize_lsa(text, ratio)
        else:
            summary = summarize_textrank(text, ratio)
        
        keywords = extract_keywords(text)
        
        return jsonify({
            'success': True,
            'title': title,
            'url': url,
            'summary': summary,
            'keywords': keywords,
            'original_length': len(text.split()),
            'summary_length': len(summary.split())
        })
        
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Fast health check"""
    return jsonify({
        'status': 'healthy',
        'cache_enabled': True,
        'rate_limiting': True,
        'compression': True,
        'models_loaded': {
            'spacy': nlp is not None
        }
    })

@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Admin endpoint to clear cache"""
    cache.clear()
    return jsonify({'message': 'Cache cleared'})

# ==================== PERFORMANCE MIDDLEWARE ====================

@app.after_request
def add_performance_headers(response):
    """Add caching headers for static assets"""
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        response.headers['Expires'] = 'Sun, 31 Dec 2034 00:00:00 GMT'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    
    # Production settings
    app.run(
        debug=False,  # Turn off debug for production
        host='0.0.0.0',
        port=port,
        threaded=True  # Handle multiple requests
    )