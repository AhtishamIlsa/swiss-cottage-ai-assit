# Streamlit Cloud Deployment Guide

## ✅ Files Created

1. **`streamlit_app.py`** - Entry point for Streamlit Cloud
2. **`requirements.txt`** - Python dependencies (auto-generated from Poetry)

## 📋 Deployment Steps

### 1. Connect Repository to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your repository: `AhtishamIlsa/swiss-cottage-ai-assit`
5. Set the **Main file path** to: `streamlit_app.py`
6. Set the **Branch** to: `main`

### 2. Configure Environment Variables

In Streamlit Cloud, add these **Secrets** (Settings → Secrets):

```toml
GROQ_API_KEY = "your-groq-api-key-here"
MODEL_NAME = "llama-3.1-8b-instant"
USE_GROQ = "true"
SYNTHESIS_STRATEGY = "create-and-refine"
```

### 3. Important: Vector Store & Model Files

⚠️ **Current Issue**: Your vector store and model files are in `.gitignore` and won't be deployed.

**Options:**

#### Option A: Upload Vector Store to GitHub (Recommended for small stores)
1. Temporarily remove `vector_store/` from `.gitignore`
2. Commit and push the vector store
3. Re-add to `.gitignore` after deployment

#### Option B: Use Cloud Storage (Recommended for large files)
1. Upload vector store to Google Drive / S3 / etc.
2. Download and extract on first app run
3. Add download logic to `streamlit_app.py`

#### Option C: Build Vector Store on Streamlit Cloud
1. Include FAQ documents in the repository
2. Build vector store on first run (slower startup)

### 4. Deploy

Click **"Deploy"** in Streamlit Cloud. The app will:
- Install dependencies from `requirements.txt`
- Run `streamlit_app.py`
- Use environment variables from Secrets

## 🔧 Troubleshooting

### Issue: "Vector store not found"
- **Solution**: Follow Option A, B, or C above

### Issue: "Model not found"
- **Solution**: The app uses Groq API by default (no local models needed)
- Make sure `GROQ_API_KEY` is set in Secrets

### Issue: "Repository not connected"
- **Solution**: 
  1. Make sure you're signed in with the correct GitHub account
  2. Check repository visibility (public or private with access)
  3. Try disconnecting and reconnecting the repository

## 📝 Notes

- Streamlit Cloud has a 1GB limit for free tier
- Vector stores and models can be large - consider cloud storage
- The app will use Groq API by default (fast, no local models)
- Make sure `.env` is in `.gitignore` (already done)
