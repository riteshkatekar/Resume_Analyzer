# import streamlit as st
# from streamlit_extras.add_vertical_space import add_vertical_space
# import os
# import json
# from dotenv import load_dotenv
# from helper import configure_genai, get_gemini_response, extract_pdf_text, prepare_prompt

# def init_session_state():
#     """Initialize session state variables."""
#     if 'processing' not in st.session_state:
#         st.session_state.processing = False


# def main():
#     # Load environment variables
#     load_dotenv()
    
#     # Initialize session state
#     init_session_state()
    
#     # Configure Generative AI
#     api_key = os.getenv("GOOGLE_API_KEY")
#     if not api_key:
#         st.error("Please set the GOOGLE_API_KEY in your .env file")
#         return
        
#     try:
#         configure_genai(api_key)
#     except Exception as e:
#         st.error(f"Failed to configure API: {str(e)}")
#         return

#     # Sidebar
#     with st.sidebar:
#         st.title("🎯 Smart ATS")
#         st.subheader("About")
#         st.write("""
#         This smart ATS helps you:
#         - Evaluate resume-job description match
#         - Identify missing keywords
#         - Get personalized improvement suggestions
#         """)

#     # Main content
#     st.title("📄 Smart ATS Resume Analyzer")
#     st.subheader("Optimize Your Resume for ATS")
    
#     # Input sections with validation
#     jd = st.text_area(
#         "Job Description",
#         placeholder="Paste the job description here...",
#         help="Enter the complete job description for accurate analysis"
#     )
    
#     uploaded_file = st.file_uploader(
#         "Resume (PDF)",
#         type="pdf",
#         help="Upload your resume in PDF format"
#     )

#     # Process button with loading state
#     if st.button("Analyze Resume", disabled=st.session_state.processing):
#         if not jd:
#             st.warning("Please provide a job description.")
#             return
            
#         if not uploaded_file:
#             st.warning("Please upload a resume in PDF format.")
#             return
            
#         st.session_state.processing = True
        
#         try:
#             with st.spinner("📊 Analyzing your resume..."):
#                 # Extract text from PDF
#                 resume_text = extract_pdf_text(uploaded_file)
                
#                 # Prepare prompt
#                 input_prompt = prepare_prompt(resume_text, jd)
                
#                 # Get and parse response
#                 response = get_gemini_response(input_prompt)
#                 response_json = json.loads(response)
                
#                 # Display results
#                 st.success("✨ Analysis Complete!")
                
#                 # Match percentage
#                 match_percentage = response_json.get("JD Match", "N/A")
#                 st.metric("Match Score", match_percentage)
                
#                 # Missing keywords
#                 st.subheader("Missing Keywords")
#                 missing_keywords = response_json.get("MissingKeywords", [])
#                 if missing_keywords:
#                     st.write(", ".join(missing_keywords))
#                 else:
#                     st.write("No critical missing keywords found!")
                
#                 # Profile summary
#                 st.subheader("Profile Summary")
#                 st.write(response_json.get("Profile Summary", "No summary available"))
                
#         except Exception as e:
#             st.error(f"An error occurred: {str(e)}")
            
#         finally:
#             st.session_state.processing = False

# if __name__ == "__main__":
#     main()


import streamlit as st
from dotenv import load_dotenv
import os
import json
from helper import (
    configure_genai,
    extract_file_text,
    prepare_prompt_for_analysis,
    call_gemini,
    parse_and_validate_analysis,
    heuristic_report_fallback,
    extract_top_bullets,
    rewrite_bullets_with_model,
)

load_dotenv()

# ---------- UI helpers ----------
def init_state():
    if "processing" not in st.session_state:
        st.session_state.processing = False
    if "last_report" not in st.session_state:
        st.session_state.last_report = None

init_state()

st.set_page_config(page_title="Smart ATS — Improved Analyzer", layout="wide")
st.title("📄 Smart ATS — Resume Analyzer (Resumeworded-style output, improved)")

# Sidebar controls
with st.sidebar:
    st.header("Model & Keys")
    api_key = os.getenv("GOOGLE_API_KEY", "")
    model_env = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")
    selected_model = st.selectbox(
        "Gemini model",
        options=["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"],
        index=0 if "flash" in model_env else 1,
    )
    temperature = st.slider("Temperature (0→deterministic, 1→creative)", 0.00, 1.00, 0.15, 0.01)
    max_output_tokens = st.slider("Max output tokens (model response)", 400, 3000, 1200, 100)
    st.markdown("---")
    st.write("API Key loaded:", "✅" if api_key else "❌")
    st.caption("Add `GOOGLE_API_KEY` to .env and restart the app if not loaded.")

if not api_key:
    st.error("GOOGLE_API_KEY not found in environment (.env). Add it and restart.")
    st.stop()

# Configure generative API (safe to call multiple times)
try:
    configure_genai(api_key)
except Exception as e:
    st.error(f"Failed to configure Gemini SDK: {e}")
    st.stop()

# ---------- Main UI: only drag & drop file inputs ----------
st.subheader("Step 1: Drag & drop files (Resume and Job Description)")
col1, col2 = st.columns(2)

with col1:
    resume_file = st.file_uploader(
        "Upload Resume (PDF, DOCX, TXT) — drag & drop here",
        type=["pdf", "docx", "txt"],
        help="Preferred: text-based PDF or DOCX. Scanned images may not extract text well."
    )

with col2:
    jd_file = st.file_uploader(
        "Upload Job Description (PDF, DOCX, TXT) — drag & drop here",
        type=["pdf", "docx", "txt"],
        help="Upload the JD file; analysis will be based on this JD."
    )

st.markdown("---")
st.info("When both files are uploaded, click **Analyze Resume**. The app will produce an improved, portfolio-quality analysis and JSON report.")

analyze_btn = st.button("Analyze Resume", disabled=st.session_state.processing)

# ---------- Analyze action ----------
if analyze_btn:
    if not resume_file:
        st.warning("Please upload a Resume file.")
    elif not jd_file:
        st.warning("Please upload the Job Description file.")
    else:
        st.session_state.processing = True
        try:
            with st.spinner("Extracting text from uploaded files..."):
                resume_text = extract_file_text(resume_file)
                jd_text = extract_file_text(jd_file)

            # Build strict prompt
            prompt = prepare_prompt_for_analysis(resume_text, jd_text)
            st.write("Prompt prepared. Sending to model...")

            # Call Gemini
            raw_model_output = call_gemini(
                prompt,
                model=selected_model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )

            # Try to parse + validate JSON returned by model
            try:
                report = parse_and_validate_analysis(raw_model_output)
                source = "model"
            except Exception as e:
                # If parsing failed, fallback to heuristic local report while logging the model error
                st.warning(f"Model JSON parsing failed (using local fallback). Reason: {e}")
                report = heuristic_report_fallback(resume_text, jd_text)
                source = "heuristic"

            # Save report in session
            st.session_state.last_report = {"report": report, "source": source, "raw_model_output": raw_model_output}

            # ---------- Display results ----------
            st.success("Analysis ready")
            st.subheader("JD Match Score")
            try:
                score_display = f"{int(report.get('JD Match', 0))}%"
            except Exception:
                score_display = str(report.get("JD Match", "N/A"))
            st.metric("JD Match", score_display)

            # Strengths & Weaknesses
            st.subheader("Strengths (what looks good)")
            strengths = report.get("Strengths", [])
            if strengths:
                for s in strengths:
                    st.write("- " + s)
            else:
                st.write("No explicit strengths found.")

            st.subheader("Weaknesses / Gaps (priority-wise)")
            weaknesses = report.get("Weaknesses", [])
            if weaknesses:
                for i, w in enumerate(weaknesses, 1):
                    st.write(f"{i}. {w}")
            else:
                st.write("No explicit weaknesses found.")

            # Missing keywords
            st.subheader("High-impact missing keywords (from JD)")
            missing = report.get("MissingKeywords", [])
            if missing:
                st.write(", ".join(missing[:60]))
            else:
                st.write("No missing keywords detected.")

            # Action plan (ordered)
            st.subheader("Prioritized Action Plan (top recommendations)")
            action_plan = report.get("ActionPlan", [])
            if action_plan:
                for i, step in enumerate(action_plan[:10], 1):
                    st.write(f"{i}. {step}")
            else:
                st.write("No action plan generated.")

            # Section scores
            st.subheader("Section-wise scores")
            section_scores = report.get("SectionScores", {})
            if section_scores:
                st.json(section_scores)
            else:
                st.write("No section scores available.")

            # Top rewritten bullets (if included)
            rewritten = report.get("RewrittenBullets", [])
            if rewritten:
                st.subheader("Suggested rewritten bullets (model-assisted)")
                for b in rewritten[:8]:
                    st.write("- " + b)

            # Download final JSON
            st.markdown("---")
            st.download_button(
                "Download analysis JSON",
                data=json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
                file_name="smart_ats_analysis.json",
                mime="application/json",
            )

            # Offer targeted rewrite action: rewrite top bullets from resume
            st.markdown("### Optional: targeted bullet rewriting")
            top_bullets = extract_top_bullets(resume_text, top_n=8)
            if top_bullets:
                st.write("Top bullets detected:")
                for i, b in enumerate(top_bullets, 1):
                    st.write(f"{i}. {b}")

                if st.button("Rewrite top bullets (model-assisted)"):
                    with st.spinner("Rewriting bullets..."):
                        try:
                            rewritten_list = rewrite_bullets_with_model(
                                top_bullets,
                                model=selected_model,
                                temperature=temperature,
                                max_output_tokens=800,
                            )
                            st.success("Top bullets rewritten — review and incorporate into your resume.")
                            for i, b in enumerate(rewritten_list, 1):
                                st.write(f"{i}. {b}")
                        except Exception as e:
                            st.error(f"Bullet rewrite failed: {e}")
            else:
                st.info("No clear bullets found for rewriting.")

            st.caption(f"Report generated by: {source} (if 'heuristic', model output was malformed and a strong local fallback was used).")

        except Exception as e:
            st.error(f"Unexpected error during analysis: {e}")
        finally:
            st.session_state.processing = False

# Show last report if available
if st.session_state.last_report:
    st.markdown("---")
    st.subheader("Last analysis snapshot (raw model output preview)")
    st.code(str(st.session_state.last_report.get("raw_model_output", ""))[:2000] + ("..." if len(str(st.session_state.last_report.get("raw_model_output", "")))>2000 else ""))
