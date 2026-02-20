import streamlit as st
import gspread
import os
import json
from google.oauth2.service_account import Credentials
import anthropic
from datetime import datetime
import re

# Streamlit page config
st.set_page_config(page_title="VP Sales Job Search Agent", layout="wide")

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=st.secrets.get("ANTHROPIC_API_KEY"))

# Google Sheets setup
def get_gsheet():
    """Connect to Google Sheet using service account credentials"""
    try:
        if st.secrets.get("google_credentials"):
            creds_dict = st.secrets.get("google_credentials")
        else:
            st.error("❌ Google credentials not configured. See setup instructions.")
            return None
        
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        
        # Get sheet by name (you'll update this with your sheet ID)
        sheet_id = st.secrets.get("GOOGLE_SHEET_ID")
        if not sheet_id:
            st.error("❌ GOOGLE_SHEET_ID not configured in secrets.")
            return None
        
        sheet = gc.open_by_key(sheet_id)
        return sheet
    except Exception as e:
        st.error(f"❌ Error connecting to Google Sheets: {e}")
        return None

# Job matching logic
def matches_criteria(job):
    """Check if job matches JR's search criteria"""
    
    # Title matching
    acceptable_titles = ["VP Sales", "VP of Sales", "Head of Sales", "VP Business Development", 
                         "VP, Sales", "VP - Sales", "Vice President Sales", "Vice President of Sales",
                         "Sales VP", "Chief Revenue Officer"]
    
    title_match = any(title.lower() in job.get('title', '').lower() for title in acceptable_titles)
    if not title_match:
        return False, "Title doesn't match criteria"
    
    # Salary matching
    salary = job.get('salary_min', 0)
    location = job.get('location', '').lower()
    
    # Remote or Nevada = $170k minimum
    if 'remote' in location or 'nevada' in location or location == '':
        if salary < 170000:
            return False, f"Salary ${salary} below $170k minimum for remote/Nevada"
    # California is acceptable
    elif 'california' in location or 'ca' in location or 'sf' in location or 'san francisco' in location or 'los angeles' in location or 'la' in location:
        if salary < 170000:
            return False, f"Salary ${salary} below $170k minimum"
    # Other locations need $250k minimum base
    else:
        if salary < 250000:
            return False, f"Salary ${salary} below $250k minimum for out-of-state relocation"
    
    # Company stage matching
    company_stage = job.get('company_stage', '').lower()
    stage_keywords = ['growth', 'series', 'seed', 'early stage', '1st hire', 'first hire', 
                      'first vp', '1st vp', 'scaling', 'pre-series']
    stage_match = any(keyword in company_stage for keyword in stage_keywords)
    
    if not stage_match and job.get('company_stage', ''):
        return False, "Company stage not growth stage or seeking first VP Sales"
    
    return True, "✓ Matches all criteria"

# Email drafting
def draft_email(job):
    """Use Claude to draft personalized outreach email"""
    
    prompt = f"""Draft a compelling but authentic outreach email for JR to send to a hiring manager or recruiter at this company:

Company: {job.get('company_name', 'Company')}
Position: {job.get('title', 'Role')}
Company Description: {job.get('company_description', 'N/A')}
Location: {job.get('location', 'TBD')}
Salary Range: ${job.get('salary_min', 'TBD'):,}

JR's Background:
- 15+ years B2B SaaS VP Sales experience
- Scaled organizations from $0 to $20M ARR
- First US hire at Fortem International, launched multiple trade shows, managed teams across 3 regions
- Founded Young Health Recruitment with exclusive Qatar 2022 FIFA World Cup partnership
- Currently running Jotia Group (10-person software dev team in Nigeria)
- Based in Las Vegas, new father
- Positioning: "Anti-guru operator who shares actual playbooks rather than motivation"

Email guidelines:
- Keep it short (150-200 words max)
- Show you've done research on the company
- Lead with a specific achievement or relevant experience
- Include a clear ask (brief call, coffee)
- Authentic tone - not salesy
- Reference that you bring actual playbooks and frameworks, not theory

Draft the email now:"""

    try:
        message = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error generating email: {e}"

# Main app UI
st.title("🎯 VP Sales Job Search Agent")
st.markdown("*Automated job discovery, matching, and outreach for growth-stage VP Sales roles*")

# Sidebar for configuration
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown("""
    **Your Criteria:**
    - Titles: VP Sales, Head of Sales, VP Business Development
    - Salary: $170k+ (remote/NV), $250k+ (other states)
    - Locations: Remote, Nevada, California (or willing to relocate for $250k+)
    - Stage: Growth stage or seeking 1st VP Sales
    """)
    
    st.markdown("---")
    st.markdown("""
    **📊 Setup Instructions:**
    1. Add API keys to Streamlit secrets (see Deploy tab)
    2. Create Google Sheet from template (see below)
    3. Paste job listings or import from spreadsheet
    4. Agent filters and drafts emails
    5. Approve before logging to sheet
    """)

# Main tabs
tab1, tab2, tab3 = st.tabs(["🔍 Job Search", "📊 Tracking", "⚙️ Setup"])

with tab1:
    st.markdown("### Add Job Opportunities")
    st.markdown("*Paste jobs from LinkedIn, AngelList, Indeed, etc. Matching jobs are automatically added to your tracker.*")
    
    input_method = st.radio("How would you like to add jobs?", 
                            ["Paste Single Job Details", "Paste CSV/JSON"])
    
    if input_method == "Paste Single Job Details":
        col1, col2 = st.columns(2)
        with col1:
            job_title = st.text_input("Job Title")
            company_name = st.text_input("Company Name")
            salary_min = st.number_input("Minimum Salary", value=170000, step=10000)
        
        with col2:
            location = st.text_input("Location (remote, state, city)")
            company_stage = st.text_input("Company Stage (e.g., Series B, Growth)")
            company_description = st.text_area("Company Description (optional)")
        
        job_url = st.text_input("Job URL (optional)")
        
        if st.button("✅ Add Job"):
            job = {
                'title': job_title,
                'company_name': company_name,
                'salary_min': salary_min,
                'location': location,
                'company_stage': company_stage,
                'company_description': company_description,
                'job_url': job_url,
                'date_added': datetime.now().strftime('%Y-%m-%d')
            }
            
            matches, reason = matches_criteria(job)
            
            if matches:
                sheet = get_gsheet()
                if sheet:
                    try:
                        # Get or create tracking worksheet
                        try:
                            ws = sheet.worksheet("Job Applications")
                        except:
                            ws = sheet.add_worksheet("Job Applications", rows=1000, cols=10)
                        
                        # Add headers if empty
                        if ws.cell(1, 1).value is None:
                            headers = ["Date Added", "Company", "Position", "Location", "Salary", 
                                     "Stage", "Status", "Applied Date", "Notes", "URL"]
                            ws.append_row(headers)
                        
                        # Append job data
                        ws.append_row([
                            job.get('date_added', datetime.now().strftime('%Y-%m-%d')),
                            job.get('company_name'),
                            job.get('title'),
                            job.get('location'),
                            f"${job.get('salary_min'):,}",
                            job.get('company_stage'),
                            "📋 To Apply",
                            "",
                            job.get('company_description', ''),
                            job.get('job_url', '')
                        ])
                        
                        st.success(f"✅ {reason}\n✅ Added to tracker!")
                    except Exception as e:
                        st.error(f"Error logging to sheet: {e}")
            else:
                st.warning(f"⚠️ {reason}")
    
    elif input_method == "Paste CSV/JSON":
        st.info("Paste your jobs data in CSV or JSON format. Matching jobs will be automatically added to your tracker.")
        jobs_text = st.text_area("Paste jobs data here", height=300)
        
        if st.button("📥 Parse & Auto-Add Matching Jobs"):
            try:
                # Try parsing as JSON first
                jobs = json.loads(jobs_text)
                if not isinstance(jobs, list):
                    jobs = [jobs]
            except:
                # Try parsing as CSV
                import csv
                import io
                jobs = list(csv.DictReader(io.StringIO(jobs_text)))
            
            if jobs:
                sheet = get_gsheet()
                if sheet:
                    try:
                        # Get or create tracking worksheet
                        try:
                            ws = sheet.worksheet("Job Applications")
                        except:
                            ws = sheet.add_worksheet("Job Applications", rows=1000, cols=10)
                        
                        # Add headers if empty
                        if ws.cell(1, 1).value is None:
                            headers = ["Date Added", "Company", "Position", "Location", "Salary", 
                                     "Stage", "Status", "Applied Date", "Notes", "URL"]
                            ws.append_row(headers)
                        
                        # Filter and add matching jobs
                        matching_count = 0
                        rejected_count = 0
                        
                        for job in jobs:
                            matches, reason = matches_criteria(job)
                            if matches:
                                ws.append_row([
                                    datetime.now().strftime('%Y-%m-%d'),
                                    job.get('company_name', ''),
                                    job.get('title', ''),
                                    job.get('location', ''),
                                    f"${job.get('salary_min', 0):,}",
                                    job.get('company_stage', ''),
                                    "📋 To Apply",
                                    "",
                                    job.get('company_description', ''),
                                    job.get('job_url', '')
                                ])
                                matching_count += 1
                            else:
                                rejected_count += 1
                        
                        st.success(f"✅ Added {matching_count} matching jobs to tracker!")
                        if rejected_count > 0:
                            st.info(f"ℹ️ {rejected_count} jobs didn't match your criteria")
                    except Exception as e:
                        st.error(f"Error logging to sheet: {e}")
            else:
                st.error("Could not parse jobs data. Try JSON or CSV format.")

with tab2:
    st.markdown("### 📊 Application Tracking")
    st.markdown("*Click 'Apply Now' to open the job link. Update 'Applied Date' when you apply.*")
    
    sheet = get_gsheet()
    if sheet:
        try:
            ws = sheet.worksheet("Job Applications")
            data = ws.get_all_records()
            
            if data:
                # Display metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Opportunities", len(data))
                with col2:
                    applied = sum(1 for row in data if row.get('Applied Date'))
                    st.metric("Applied", applied)
                with col3:
                    try:
                        avg_salary = sum(int(row['Salary'].replace('$', '').replace(',', '')) for row in data if row.get('Salary')) / len(data) if data else 0
                        st.metric("Avg Salary", f"${avg_salary:,.0f}")
                    except:
                        st.metric("Avg Salary", "—")
                with col4:
                    remote_count = sum(1 for row in data if 'remote' in row.get('Location', '').lower())
                    st.metric("Remote", remote_count)
                
                st.markdown("---")
                
                # Display jobs with Apply button
                st.markdown("### Your Opportunities")
                
                for idx, row in enumerate(data):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"**{row.get('Company', 'Company')}** — {row.get('Position', 'Position')}")
                        st.markdown(f"📍 {row.get('Location', 'Location')} • 💰 {row.get('Salary', 'TBD')} • {row.get('Status', '—')}")
                    
                    with col2:
                        if row.get('URL'):
                            st.markdown(f"[🔗 Apply Now]({row.get('URL')})")
                        else:
                            st.markdown("*(No URL)*")
                    
                    with col3:
                        applied_date = row.get('Applied Date', '')
                        if applied_date:
                            st.markdown(f"✅ {applied_date}")
                        else:
                            st.markdown("⏳ Pending")
                    
                    st.markdown("---")
            else:
                st.info("No opportunities tracked yet. Go to Job Search tab to add jobs.")
        except Exception as e:
            st.info(f"Tracking sheet not yet created. Go to Job Search tab to add your first job!")

with tab3:
    st.markdown("### ⚙️ Setup & Deployment Instructions")
    
    st.markdown("""
    ## Step 1: Get Your API Keys
    
    ### Anthropic API Key
    1. Go to https://console.anthropic.com
    2. Create an API key
    3. Save it securely
    
    ### Google Sheets Access
    1. Go to https://console.cloud.google.com
    2. Create a new project
    3. Enable Google Sheets API and Google Drive API
    4. Create a Service Account
    5. Download JSON credentials file
    6. Keep the JSON content ready (you'll paste it below)
    
    ## Step 2: Deploy to Streamlit Cloud
    
    1. Create a GitHub repo with these files:
       - `job_search_agent.py` (this app)
       - `requirements.txt` (dependencies)
       - `.streamlit/secrets.toml` (your API keys)
    
    2. Go to https://streamlit.io/cloud
    3. Click "New app" → Select your repo
    4. Add these secrets in the Streamlit dashboard:
       - `ANTHROPIC_API_KEY`: Your API key
       - `GOOGLE_CREDENTIALS`: Your Google Service Account JSON (as JSON)
       - `GOOGLE_SHEET_ID`: Your Google Sheet ID (from URL)
    
    ## Step 3: Create Google Sheet
    
    1. Copy this template: [Link to template below]
    2. Share it with your Service Account email
    3. Get the Sheet ID from the URL (between /d/ and /edit)
    4. Add it to secrets as `GOOGLE_SHEET_ID`
    
    ## Step 4: Run Locally (Optional)
    
    ```bash
    pip install -r requirements.txt
    streamlit run job_search_agent.py
    ```
    
    Set secrets in `.streamlit/secrets.toml`:
    ```toml
    ANTHROPIC_API_KEY = "your-key"
    GOOGLE_SHEET_ID = "your-sheet-id"
    
    [google_credentials]
    type = "service_account"
    project_id = "..."
    # ... rest of JSON
    ```
    
    ## Troubleshooting
    
    - **"Google credentials not configured"** → Add GOOGLE_CREDENTIALS to Streamlit secrets
    - **"GOOGLE_SHEET_ID not configured"** → Add sheet ID to secrets
    - **Email drafts not generating** → Check ANTHROPIC_API_KEY is valid
    """)
    
    st.markdown("---")
    
    st.markdown("### 📋 Google Sheet Template")
    st.info("""
    **Create a blank Google Sheet and share with your Service Account email.**
    
    The app will automatically create a "Job Applications" worksheet with these columns:
    - Date Added
    - Company
    - Position
    - Location
    - Salary
    - Stage
    - Status
    - Email Sent
    - Email
    - URL
    """)
    
    st.markdown("### 📦 Requirements.txt Contents")
    with st.expander("View requirements.txt"):
        st.code("""streamlit==1.28.1
gspread==5.10.0
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.2.0
google-cloud-storage==2.10.0
anthropic==0.7.1""")

st.markdown("---")
st.markdown("*Built for VP Sales job search • Last updated: Feb 2025*")
