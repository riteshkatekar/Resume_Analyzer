# import google.generativeai as genai
# import PyPDF2 as pdf
# import json

# def configure_genai(api_key):
#     """Configure the Generative AI API with error handling."""
#     try:
#         genai.configure(api_key=api_key)
#     except Exception as e:
#         raise Exception(f"Failed to configure Generative AI: {str(e)}")
    

# def get_gemini_response(prompt):
#     """Generate a response using Gemini with enhanced error handling and response validation."""
#     try:
#         model = genai.GenerativeModel('gemini-1.5-flash')
#         response = model.generate_content(prompt)
        
#         # Ensure response is not empty
#         if not response or not response.text:
#             raise Exception("Empty response received from Gemini")
            
#         # Try to parse the response as JSON
#         try:
#             response_json = json.loads(response.text)
            
#             # Validate required fields
#             required_fields = ["JD Match", "MissingKeywords", "Profile Summary"]
#             for field in required_fields:
#                 if field not in response_json:
#                     raise ValueError(f"Missing required field: {field}")
                    
#             return response.text
            
#         except json.JSONDecodeError:
#             # If response is not valid JSON, try to extract JSON-like content
#             import re
#             json_pattern = r'\{.*\}'
#             match = re.search(json_pattern, response.text, re.DOTALL)
#             if match:
#                 return match.group()
#             else:
#                 raise Exception("Could not extract valid JSON response")
                
#     except Exception as e:
#         raise Exception(f"Error generating response: {str(e)}")

# def extract_pdf_text(uploaded_file):
#     """Extract text from PDF with enhanced error handling."""
#     try:
#         reader = pdf.PdfReader(uploaded_file)
#         if len(reader.pages) == 0:
#             raise Exception("PDF file is empty")
            
#         text = []
#         for page in reader.pages:
#             page_text = page.extract_text()
#             if page_text:
#                 text.append(page_text)
                
#         if not text:
#             raise Exception("No text could be extracted from the PDF")
            
#         return " ".join(text)
        
#     except Exception as e:
#         raise Exception(f"Error extracting PDF text: {str(e)}")
    


# def prepare_prompt(resume_text, job_description):
#     """Prepare the input prompt with improved structure and validation."""
#     if not resume_text or not job_description:
#         raise ValueError("Resume text and job description cannot be empty")
        
#     prompt_template = """
#     Act as an expert ATS (Applicant Tracking System) specialist with deep expertise in:
#     - Technical fields
#     - Software engineering
#     - Data science
#     - Data analysis
#     - Big data engineering
    
#     Evaluate the following resume against the job description. Consider that the job market 
#     is highly competitive. Provide detailed feedback for resume improvement.
    
#     Resume:
#     {resume_text}
    
#     Job Description:
#     {job_description}
    
#     Provide a response in the following JSON format ONLY:
#     {{
#         "JD Match": "percentage between 0-100",
#         "MissingKeywords": ["keyword1", "keyword2", ...],
#         "Profile Summary": "detailed analysis of the match and specific improvement suggestions"
#     }}
#     """
    
#     return prompt_template.format(
#         resume_text=resume_text.strip(),
#         job_description=job_description.strip()
#     )

import os
import re
import json
import time
from typing import Optional, Dict, Any, List
from collections import Counter
from io import BytesIO

import google.generativeai as genai
import PyPDF2
import docx

# ---------- configure ----------
def configure_genai(api_key: str):
    if not api_key:
        raise ValueError("API key missing")
    genai.configure(api_key=api_key)


# ---------- file text extraction (pdf/docx/txt) ----------
def extract_pdf_text(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    reader = PyPDF2.PdfReader(BytesIO(data))
    pages = []
    for p in reader.pages:
        txt = p.extract_text()
        if txt:
            pages.append(txt)
    if not pages:
        raise Exception("PDF text extraction returned empty (maybe scanned image?)")
    return "\n".join(pages).strip()


def extract_docx_text(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    bio = BytesIO(data)
    doc = docx.Document(bio)
    paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(paras).strip()


def extract_txt_text(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    if isinstance(data, bytes):
        try:
            return data.decode("utf-8", errors="ignore").strip()
        except Exception:
            return data.decode("latin-1", errors="ignore").strip()
    return str(data)


def extract_file_text(uploaded_file) -> str:
    """
    Single helper that selects the right extractor by filename extension or content-type.
    Supports .pdf, .docx, .txt
    """
    name = getattr(uploaded_file, "name", "").lower()
    if name.endswith(".pdf"):
        return extract_pdf_text(uploaded_file)
    if name.endswith(".docx"):
        return extract_docx_text(uploaded_file)
    # treat everything else as plain text
    return extract_txt_text(uploaded_file)


# ---------- prompt builder (strict JSON) ----------
def prepare_prompt_for_analysis(resume_text: str, jd_text: str) -> str:
    """
    Create a strict instruction prompting the model to return a JSON object ONLY.
    Provide an example JSON exactly matching structure and types to avoid messy outputs.
    """
    example = {
        "JD Match": 85,  # integer 0-100
        "Strengths": ["Concise technical summary", "Quantified achievements in projects", "Relevant skills: Python, SQL"],
        "Weaknesses": ["Few quantified metrics", "Missing cloud keywords", "No clear summary tailored to JD"],
        "MissingKeywords": ["AWS", "Spark", "Kafka"],
        "ActionPlan": [
            "Add AWS, Spark under Skills and show a 1-line achievement using them",
            "Quantify accomplishments with numbers (e.g., 'reduced latency by 30%')",
            "Shorten Summary to 2 lines focusing on JD keywords"
        ],
        "SectionScores": {"skills": 80, "experience": 70, "education": 90, "projects": 75, "summary": 60},
        "RewrittenBullets": [
            "Improved ETL throughput by 40% using Spark and optimized SQL queries.",
            "Designed and deployed AWS Lambda functions to automate report generation."
        ]
    }

    prompt = f"""
You are an expert ATS reviewer and professional resume coach. Compare the candidate resume below against the job description and produce ONLY a VALID JSON OBJECT (no extra commentary, no leading/trailing text).

Resume:
{resume_text}

Job Description:
{jd_text}

Return EXACTLY one JSON object with the following keys and types:
- "JD Match": integer between 0 and 100 (percentage).
- "Strengths": array of short strings (3-8 items) listing strongest points.
- "Weaknesses": array of short strings (3-8 items) listing highest-priority weaknesses/gaps.
- "MissingKeywords": array of short strings (keywords/phrases present in JD but absent in resume).
- "ActionPlan": ordered array of short actionable steps (1-8 items), top priority first.
- "SectionScores": object mapping section name -> integer score 0-100 (keys: skills, experience, education, projects, summary)
- "RewrittenBullets": array of suggested improved bullets (max 10) (strings)

Provide a JSON object exactly like this EXAMPLE (matching keys and value types). Example:
{json.dumps(example, indent=2)}

Important: Output must be parseable with a standard JSON parser. Do NOT add any additional commentary or text. Keep lists concise and human-actionable.
"""
    return prompt


# ---------- call model and robust retrieval ----------
def call_gemini(prompt: str, model: str = "gemini-1.5-flash", temperature: float = 0.15, max_output_tokens: int = 1200, retries: int = 2) -> str:
    last_err = None
    for attempt in range(retries + 1):
        try:
            model_obj = genai.GenerativeModel(model)
            resp = model_obj.generate_content(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
            if not resp or not getattr(resp, "text", None):
                raise Exception("Empty model response")
            return resp.text
        except Exception as e:
            last_err = e
            time.sleep(1.2 * (attempt + 1))
            continue
    raise Exception(f"Model call failed after {retries+1} attempts: {last_err}")


# ---------- robust JSON extraction helpers ----------
def extract_json_substring(text: str) -> Optional[str]:
    """
    Attempt to find the first balanced JSON object in `text` by scanning braces.
    Returns substring or None.
    """
    if not text:
        return None
    idx = text.find("{")
    while idx != -1:
        stack = []
        for i in range(idx, len(text)):
            ch = text[i]
            if ch == "{":
                stack.append("{")
            elif ch == "}":
                if stack:
                    stack.pop()
                    if not stack:
                        return text[idx:i+1]
                else:
                    # unmatched closing brace: stop this start index
                    break
        idx = text.find("{", idx + 1)
    return None


def parse_and_validate_analysis(raw_text: str) -> Dict[str, Any]:
    """
    Try direct JSON parse; if fails, try balanced-substring extraction; if still fails, raise.
    After parsing, perform type normalization and validation.
    """
    # 1) direct parse
    try:
        obj = json.loads(raw_text)
    except Exception:
        # 2) attempt to find JSON substring
        json_sub = extract_json_substring(raw_text)
        if not json_sub:
            raise Exception("No JSON object found in model output")
        try:
            obj = json.loads(json_sub)
        except Exception as e:
            raise Exception(f"Extracted JSON substring failed to parse: {e}")

    # Validate required keys
    required = ["JD Match", "Strengths", "Weaknesses", "MissingKeywords", "ActionPlan", "SectionScores", "RewrittenBullets"]
    for k in required:
        if k not in obj:
            raise Exception(f"Missing required key in model JSON: {k}")

    # Normalize JD Match to int 0-100
    try:
        jm = obj.get("JD Match")
        if isinstance(jm, str) and jm.strip().endswith("%"):
            jm_val = int(re.sub(r"[^\d]", "", jm))
        else:
            jm_val = int(float(jm))
        jm_val = max(0, min(100, jm_val))
        obj["JD Match"] = jm_val
    except Exception:
        obj["JD Match"] = 0

    # ensure arrays of strings
    for arr_key in ["Strengths", "Weaknesses", "MissingKeywords", "ActionPlan", "RewrittenBullets"]:
        val = obj.get(arr_key, [])
        if isinstance(val, str):
            # try splitting
            # split by newline or comma
            parts = [p.strip() for p in re.split(r'[\n,]+', val) if p.strip()]
            obj[arr_key] = parts
        elif isinstance(val, list):
            obj[arr_key] = [str(x).strip() for x in val if str(x).strip()]
        else:
            obj[arr_key] = []

    # normalize SectionScores
    ss = obj.get("SectionScores", {})
    if not isinstance(ss, dict):
        obj["SectionScores"] = {}
    else:
        # ensure integer scores 0-100 for expected keys
        expected = ["skills", "experience", "education", "projects", "summary"]
        for k in expected:
            v = ss.get(k, 0)
            try:
                ss[k] = max(0, min(100, int(float(v))))
            except Exception:
                ss[k] = 0
        obj["SectionScores"] = {k: ss[k] for k in expected}

    return obj


# ---------- strong heuristic fallback (if model fails) ----------
def tokenize(text: str) -> List[str]:
    t = re.sub(r'[^A-Za-z0-9\+#\.\- ]+', ' ', text)
    toks = [w.lower() for w in t.split() if len(w) > 1]
    return toks


def top_keywords(tokens: List[str], top_n: int = 60) -> List[str]:
    c = Counter(tokens)
    stop = set(["and","or","the","with","using","experience","years","year","in","for","of","a","an","to","is","on","by"])
    items = [k for k,_ in c.most_common(top_n) if k not in stop]
    return items


def heuristic_report_fallback(resume_text: str, jd_text: str) -> Dict[str, Any]:
    """
    Construct a reasonable report locally using token overlap and heuristics.
    This ensures you always get a good-looking JSON even when the model fails.
    """
    r_toks = tokenize(resume_text)
    jd_toks = tokenize(jd_text)

    jd_top = top_keywords(jd_toks, top_n=80)
    res_top = top_keywords(r_toks, top_n=120)

    overlap = list(set(jd_top).intersection(set(res_top)))
    missing = [k for k in jd_top if k not in res_top][:40]

    jd_match_percent = 0
    if jd_top:
        jd_match_percent = int(100 * len(overlap) / max(1, len(jd_top)))

    # Strength heuristics
    strengths = []
    if len(res_top) > 20:
        strengths.append("Resume contains many technical keywords")
    if re.search(r'\b\d+%|\b\d{2,}\b', resume_text):
        strengths.append("Some quantified achievements present")
    if "summary" in resume_text.lower() or len(resume_text.splitlines())>5:
        strengths.append("Profile summary / long introduction present")

    # Weakness heuristics
    weaknesses = []
    if not any(re.search(r'\b\d+\%|\b\d{2,}\b', s) for s in res_top):
        weaknesses.append("Few quantified, numeric achievements")
    if len(missing) > 0:
        weaknesses.append("Missing several high-impact JD keywords (see MissingKeywords)")
    if len(res_top) < 10:
        weaknesses.append("Skills section seems sparse or unstructured")

    # Section scores approximate
    section_scores = {
        "skills": min(90, max(10, len(res_top) * 3)),
        "experience": 50 + min(40, sum(1 for _ in re.finditer(r'\b(?:experience|responsibilities|worked)', resume_text.lower()))*10),
        "education": 70 if re.search(r'\b(university|college|bachelor|master|b\.tech|bsc|msc|mba|phd)\b', resume_text.lower()) else 40,
        "projects": 60 if re.search(r'\b(project|project:)\b', resume_text.lower()) else 30,
        "summary": 60 if len(resume_text.splitlines())>3 else 40
    }

    # action plan (prioritized)
    action_plan = []
    if missing:
        action_plan.append("Add the top missing JD keywords into your Skills and Experience where relevant (e.g., 'AWS', 'Spark').")
    action_plan.append("Quantify accomplishments (add numbers/percentages to achievements).")
    action_plan.append("Create a 2-line tailored summary at the top referencing the JD's top requirements.")
    action_plan.append("Convert any image-only resume to a text-based PDF / DOCX for ATS readability.")
    action_plan = action_plan[:6]

    # top bullets rewrite simple heuristic (just pick lines starting with '-' or numbers)
    rewritten_bullets = []
    bullets = re.findall(r'(^[\-\•\*\d\.\)]\s*[A-Z].{20,200}$)', resume_text, flags=re.MULTILINE)
    if not bullets:
        # simple fallback: find sentences with 'led' or 'developed' and keep
        cand = re.findall(r'([A-Z][^\.]{30,200}\b(?:led|designed|built|improved|reduced|increased|implemented)[^\.]{0,80}\.)', resume_text, flags=re.IGNORECASE)
        bullets = cand[:6]
    for b in bullets[:6]:
        # simple normalization: shorten to first sentence
        s = b.strip()
        s = re.sub(r'^[\-\•\*\d\.\)\s]+', '', s)
        rewritten_bullets.append(s[:140])

    report = {
        "JD Match": jd_match_percent,
        "Strengths": strengths or ["Concise resume content present"],
        "Weaknesses": weaknesses or ["No glaring weaknesses detected"],
        "MissingKeywords": missing,
        "ActionPlan": action_plan,
        "SectionScores": section_scores,
        "RewrittenBullets": rewritten_bullets,
    }
    return report


# ---------- helpers for bullet extraction & model-assisted rewrite ----------
def extract_top_bullets(resume_text: str, top_n: int = 8) -> List[str]:
    # find typical bullet lines
    bullets = []
    for line in resume_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*")) or re.match(r'^\d+[\.\)]\s+', stripped):
            clean = re.sub(r'^[\-\•\*\d\.\)\s]+', '', stripped)
            if len(clean) > 20:
                bullets.append(clean)
    if not bullets:
        # fallback: find long sentences with action verbs
        cand = re.findall(r'([A-Z][^\.]{30,200}\b(?:led|designed|built|improved|reduced|increased|implemented|developed)[^\.]{0,80}\.)', resume_text, flags=re.IGNORECASE)
        bullets = [c.strip() for c in cand]
    return bullets[:top_n]


def rewrite_bullets_with_model(bullets: List[str], model: str = "gemini-1.5-flash", temperature: float = 0.15, max_output_tokens: int = 800) -> List[str]:
    if not bullets:
        return []
    prompt = "You are an expert resume editor. Rewrite the bullets to be achievement-oriented, ATS-friendly, and concise. Return a JSON array of rewritten bullets only.\n\nBullets:\n" + "\n".join(f"- {b}" for b in bullets)
    raw = call_gemini(prompt, model=model, temperature=temperature, max_output_tokens=max_output_tokens)
    # try to parse JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed]
    except Exception:
        # try to extract JSON substring
        sub = extract_json_substring(raw)
        if sub:
            try:
                parsed = json.loads(sub)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed]
            except Exception:
                pass
    # last fallback: return shortened original bullets (improved heuristics could be added)
    return [b.strip()[:160] for b in bullets]
