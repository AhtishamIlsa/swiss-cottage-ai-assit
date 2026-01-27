# Rebuild FAQ from Google Sheets

## Problem
The current FAQ files have mismatched questions and answers, and include PDF file paths in the source field.

## Solution
Use the new Google Sheets CSV extractor to rebuild all FAQ files from the source data.

## Steps

### 1. Export Google Sheets to CSV
1. Open the Google Sheets: https://docs.google.com/spreadsheets/d/1IQLOOzj0tlf9R3gSXZELTo-uF3Pmt2GY_jNpgb3tyjs/edit?gid=1930017810#gid=1930017810
2. Go to **File > Download > Comma Separated Values (.csv)**
3. Save the file as `swiss_cottages_faqs.csv` in the project root

### 2. Run the Extractor
```bash
cd /var/www/html/rag-baesd-model
python chatbot/google_sheets_faq_extractor.py \
    --csv swiss_cottages_faqs.csv \
    --output docs/faq \
    --vector-store vector_store
```

This will:
- Extract all Q&A pairs from CSV
- Generate properly formatted Markdown files
- Remove PDF source paths (uses "Google Sheets" instead)
- Rebuild the vector store from scratch

### 3. Verify Results
Check a few FAQ files to ensure questions and answers match:
```bash
# Check a specific FAQ
cat docs/faq/General_About_faq_001.md

# Count total FAQs
ls docs/faq/*.md | wc -l
```

### 4. Test the Chatbot
Restart the chatbot and test with:
- "Where can I read verified guest feedback?"
- "Who should I contact for booking?"

## Alternative: Manual CSV Export
If the Google Sheets export doesn't work, you can:
1. Copy the data from Google Sheets
2. Paste into a new CSV file
3. Ensure columns are: Category, #, Question, Answer, Account/Resource, Link
4. Run the extractor on that CSV file

## Notes
- The extractor automatically matches questions with correct answers
- Source field will be "Google Sheets" (no file paths)
- Old vector store is automatically removed before rebuilding
- All FAQ files are regenerated from scratch
