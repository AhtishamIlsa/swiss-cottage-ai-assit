# Quick Start Guide

## Running the RAG Chatbot

```bash
./run_rag_chatbot.sh
```

## What to Expect

1. **First 10 seconds**: Script checks dependencies
2. **Next 30-60 seconds**: Model loading (you'll see many "load:" messages - this is NORMAL)
3. **When ready**: You'll see "You can now view your Streamlit app in your browser"
4. **Browser opens**: Chatbot interface appears

## The "Errors" You See Are NOT Errors

All those messages like:
- `load: control token...`
- `llama_model_loader:...`
- `load_tensors: layer X...`

These are **informational messages** from llama.cpp showing model loading progress.
They are **NOT errors**. The model is loading correctly.

## If It Seems Stuck

The model loading takes time because:
- Model file is 4.5 GB
- Loading 32 layers into memory
- This is a one-time process per session

**Just wait for the "You can now view" message!**

## Testing the Application

Once the browser opens, try asking:
- "What is Swiss Cottages?"
- "Tell me about the cottages"
- "What facilities are available?"

The chatbot will retrieve relevant FAQs and answer your questions.
