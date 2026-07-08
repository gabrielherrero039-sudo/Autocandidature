"""
AutoCandidature IA — Recherche intelligente multi-sources
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Jooble API  → agrège 140 000 sites (LinkedIn, Indeed, WTTJ, Monster…)
• Adzuna API  → Indeed FR, Cadremploi, Reed, Monster (clé gratuite)
• SerpAPI     → Google Jobs (optionnel, meilleure qualité)
• Claude IA   → élargit la recherche aux titres connexes du domaine
• Recherches parallèles sur tous les termes en même temps
"""

import io, re, time, json
import concurrent.futures
import requests
import streamlit as st
import anthropic

# ══════════════════════════════════════════════════════════════════
# UTILITAIRES CV
# ══════════════════════════════════════════════════════════════════

def extract_pdf(data):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        pass
    try:
        import PyPDF2
        r = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n\n".join(p.extract_text() or "" for p in r.pages)
    except Exception:
        return ""

def extract_docx_text(data):
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""

def load_cv_file(f):
    data = f.read()
    if f.name.lower().endswith(".pdf"):  return extract_pdf(data)
    if f.name.lower().endswith(".docx"): return extract_docx_text(data)
    return data.decode("utf-8", errors="ignore")

def export_docx(content):
    try:
        import docx as dx
        doc = dx.Document()
        for line in content.split("\n"):
            s = line.strip()
            if   s.startswith("# "):  doc.add_heading(s[2:], level=1)
            elif s.startswith("## "): doc.add_heading(s[3:], level=2)
            elif s == "":             doc.add_paragraph("")
            else:
                p = doc.add_paragraph()
                for part in re.split(r"(\*\*[^*]+\*\*)", s):
                    if part.startswith("**") and part.endswith("**"):
                        p.add_run(part[2:-2]).bold = True
                    else:
                        p.add_run(part)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    except Exception:
        return None

def clean_html(t):
    t = re.sub(r"<[^>]+>", " ", str(t))
    return re.sub(r"\s+", " ", t).strip()

def fmt_salary(mn, mx, cur="€"):
    try:
        if mn and mx:   return f"{int(float(mn)):,} – {int(float(mx)):,} {cur}"
        if mn:          return f"À partir de {int(float(mn)):,} {cur}"
        if mx:          return f"Jusqu'à {int(float(mx)):,} {cur}"
    except Exception:   pass
    return ""

# ══════════════════════════════════════════════════════════════════
# EXPANSION DU DOMAINE PAR CLAUDE
# ══════════════════════════════════════════════════════════════════

def expand_keywords(keyword: str, api_key: str, model: str) -> list[str]:
    """
    Demande à Claude de générer des titres de postes connexes
    pour élargir la recherche dans le même domaine.
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"Génère 4 titres de postes alternatifs ou similaires à « {keyword} » "
                    "pour une recherche d'emploi en France. "
                    "Réponds UNIQUEMENT avec les titres séparés par des virgules, sans explication ni numérotation."
                )
            }]
        )
        raw = msg.content[0].text
        return [k.strip() for k in raw.split(",") if k.strip()][:4]
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════
# SOURCES DE RECHERCHE
# ══════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}

# ── Jooble (140 000 sites, clé gratuite) ─────────────────────────

def search_jooble(keywords: str, location: str, jooble_key: str,
                  radius: int = 50, page: int = 1) -> list[dict]:
    if not jooble_key:
        return []
    try:
        payload = {
            "keywords": keywords,
            "location": location,
            "radius":   radius,
            "page":     page,
            "resultonpage": 20,
        }
        r = requests.post(
            f"https://jooble.org/api/{jooble_key}",
            json=payload,
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("jobs", []):
            raw_salary = clean_html(item.get("salary", ""))
            jobs.append({
                "source":      "Jooble",
                "title":       item.get("title", ""),
                "company":     item.get("company", "N/A"),
                "location":    item.get("location", location),
                "description": clean_html(item.get("snippet", "")),
                "url":         item.get("link", ""),
                "salary":      raw_salary,
                "contract":    item.get("type", ""),
                "posted":      item.get("updated", "")[:10],
                "is_remote":   "remote" in item.get("title","").lower()
                               or "télétravail" in item.get("title","").lower(),
                "missions":    [],
            })
        return jobs
    except Exception as e:
        st.warning(f"Jooble : {e}")
        return []

# ── Adzuna (clé gratuite, excellente couverture FR) ───────────────

def search_adzuna(keywords: str, location: str, country: str,
                  app_id: str, app_key: str) -> list[dict]:
    if not app_id or not app_key:
        return []
    cc_map = {"France":"fr","Belgique":"be","Suisse":"ch",
               "Canada":"ca","USA":"us","UK":"gb","Allemagne":"de"}
    cc = cc_map.get(country, "fr")
    try:
        r = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
            params={"app_id": app_id, "app_key": app_key,
                    "results_per_page": 20, "what": keywords, "where": location},
            headers=HEADERS, timeout=12,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("results", []):
            desc = clean_html(item.get("description", ""))
            jobs.append({
                "source":      "Adzuna",
                "title":       item.get("title", ""),
                "company":     item.get("company", {}).get("display_name", "N/A"),
                "location":    item.get("location", {}).get("display_name", location),
                "description": desc,
                "url":         item.get("redirect_url", ""),
                "salary":      fmt_salary(item.get("salary_min"), item.get("salary_max")),
                "contract":    item.get("contract_time", ""),
                "posted":      item.get("created", "")[:10],
                "is_remote":   False,
                "missions":    _extract_missions(desc),
            })
        return jobs
    except Exception as e:
        st.warning(f"Adzuna : {e}")
        return []

# ── SerpAPI Google Jobs (optionnel, meilleure qualité) ────────────

def search_serpapi(keywords: str, location: str, serpapi_key: str,
                   radius: int = 50) -> list[dict]:
    if not serpapi_key:
        return []
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_jobs",
                "q": f"{keywords} {location}",
                "api_key": serpapi_key,
                "hl": "fr",
                "lrad": radius,
                "chips": "date_posted:month",
            },
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("jobs_results", []):
            ext    = item.get("detected_extensions", {})
            salary = ext.get("salary", "") or fmt_salary(
                item.get("salary_min"), item.get("salary_max")
            )
            # Extraire les missions depuis job_highlights
            missions = []
            for hl in item.get("job_highlights", []):
                if hl.get("title","").lower() in ("responsabilités","missions","tâches","responsibilities"):
                    missions = hl.get("items", [])
                    break
            if not missions:
                for hl in item.get("job_highlights", []):
                    missions += hl.get("items", [])
            desc = clean_html(item.get("description", ""))
            jobs.append({
                "source":      f"Google Jobs (via {item.get('via','web')})",
                "title":       item.get("title", ""),
                "company":     item.get("company_name", "N/A"),
                "location":    item.get("location", location),
                "description": desc,
                "url":         (item.get("apply_options") or [{}])[0].get("link", ""),
                "salary":      salary,
                "contract":    ext.get("schedule_type", ""),
                "posted":      ext.get("posted_at", ""),
                "is_remote":   ext.get("work_from_home", False),
                "missions":    missions[:6],
                "highlights":  item.get("job_highlights", []),
            })
        return jobs
    except Exception as e:
        st.warning(f"SerpAPI : {e}")
        return []

# ── Remotive (remote mondial, sans clé) ───────────────────────────

def search_remotive(keywords: str) -> list[dict]:
    try:
        r = requests.get("https://remotive.com/api/remote-jobs",
                         params={"search": keywords, "limit": 10},
                         headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("jobs", []):
            desc = clean_html(item.get("description", ""))
            jobs.append({
                "source":    "Remotive (Remote)",
                "title":     item.get("title", ""),
                "company":   item.get("company_name", "N/A"),
                "location":  "🌍 Remote — " + item.get("candidate_required_location","Mondial"),
                "description": desc,
                "url":       item.get("url", ""),
                "salary":    item.get("salary",""),
                "contract":  item.get("job_type",""),
                "posted":    item.get("publication_date","")[:10],
                "is_remote": True,
                "missions":  _extract_missions(desc),
            })
        return jobs
    except Exception:
        return []

# ── Extraction de missions depuis une description ─────────────────

def _extract_missions(desc: str) -> list[str]:
    """Tente d'extraire une liste de missions depuis la description brute."""
    missions = []
    lines = desc.split(".")
    for line in lines:
        line = line.strip()
        if 10 < len(line) < 200 and any(kw in line.lower() for kw in
            ["vous","votre","assurer","gérer","développer","participer",
             "contribuer","analyser","concevoir","mettre en place","piloter",
             "rédiger","coordonner","accompagner","suivre","réaliser"]):
            missions.append(line.strip(" -•–"))
        if len(missions) >= 5:
            break
    return missions

# ══════════════════════════════════════════════════════════════════
# MOTEUR DE RECHERCHE PARALLÈLE
# ══════════════════════════════════════════════════════════════════

def run_all_searches(
    primary_keyword: str,
    extra_keywords:  list[str],
    location:        str,
    country:         str,
    radius:          int,
    include_remote:  bool,
    jooble_key:      str,
    adzuna_id:       str,
    adzuna_key:      str,
    serpapi_key:     str,
) -> list[dict]:

    all_terms = [primary_keyword] + extra_keywords

    tasks = []
    # Pour chaque terme, lance Jooble + Adzuna + SerpAPI
    for term in all_terms:
        if jooble_key:
            tasks.append(("jooble",   term, location))
        if adzuna_id and adzuna_key:
            tasks.append(("adzuna",   term, location))
        if serpapi_key:
            tasks.append(("serpapi",  term, location))

    if include_remote:
        tasks.append(("remotive", primary_keyword, ""))

    results: list[dict] = []

    def run_task(task):
        src, term, loc = task
        if src == "jooble":
            return search_jooble(term, loc, jooble_key, radius)
        if src == "adzuna":
            return search_adzuna(term, loc, country, adzuna_id, adzuna_key)
        if src == "serpapi":
            return search_serpapi(term, loc, serpapi_key, radius)
        if src == "remotive":
            return search_remotive(term)
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.extend(future.result())
            except Exception:
                pass

    return results

def filter_and_dedupe(jobs: list[dict], location: str, country: str,
                      include_remote: bool) -> list[dict]:
    """Filtre par localisation et supprime les doublons."""
    country_words = {
        "France":   ["france","fr,","paris","lyon","marseille","toulouse","orléans",
                     "orleans","bordeaux","lille","nantes","strasbourg","rennes",
                     "montpellier","nice","grenoble","nancy"],
        "Belgique": ["belgique","belgium","bruxelles","liège","gand"],
        "Suisse":   ["suisse","switzerland","genève","zurich","berne","lausanne"],
        "Canada":   ["canada","québec","montréal","toronto","vancouver"],
        "USA":      ["usa","united states","new york","california","chicago"],
        "UK":       ["uk","london","england","manchester","birmingham"],
        "Allemagne":["germany","deutschland","berlin","munich","hamburg","frankfurt"],
    }

    def matches(job):
        loc = job.get("location","").lower()
        if job.get("is_remote") or "remote" in loc or "🌍" in loc:
            return include_remote or True  # toujours inclus si remote
        if not location and not country:
            return True
        if location and location.lower() in loc:
            return True
        for word in country_words.get(country, [country.lower()]):
            if word in loc:
                return True
        return False

    filtered = [j for j in jobs if matches(j)]

    # Dédoublonnage : même titre + même entreprise
    seen: set = set()
    unique: list[dict] = []
    for j in filtered:
        key = (j["title"].lower()[:35], j["company"].lower()[:25])
        if key not in seen:
            seen.add(key)
            unique.append(j)

    return unique

# ══════════════════════════════════════════════════════════════════
# ENRICHISSEMENT IA : RÉSUMÉ DE L'OFFRE
# ══════════════════════════════════════════════════════════════════

def summarize_job(job: dict, api_key: str, model: str) -> dict:
    """
    Demande à Claude de résumer l'offre en 5 points clés :
    missions, compétences, avantages, profil, culture d'entreprise.
    """
    client = anthropic.Anthropic(api_key=api_key)
    desc = job.get("description","")[:3000]
    if not desc:
        return job
    try:
        msg = client.messages.create(
            model=model, max_tokens=600,
            messages=[{"role": "user", "content":
                f"""Analyse cette offre d'emploi et retourne un JSON avec ces 5 clés exactes :
{{
  "missions": ["mission 1", "mission 2", "mission 3", "mission 4"],
  "competences": ["compétence 1", "compétence 2", "compétence 3"],
  "profil": "description courte du profil recherché en 1-2 phrases",
  "avantages": ["avantage 1", "avantage 2"],
  "ambiance": "culture/ambiance en 1 phrase courte"
}}

Offre : {job.get('title')} chez {job.get('company')}
Description : {desc}

Réponds UNIQUEMENT avec le JSON, rien d'autre."""
            }]
        )
        raw = msg.content[0].text.strip()
        # Extraire le JSON
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            parsed = json.loads(match.group())
            job["ai_summary"] = parsed
    except Exception:
        pass
    return job

# ══════════════════════════════════════════════════════════════════
# GÉNÉRATION CANDIDATURE IA
# ══════════════════════════════════════════════════════════════════

def stream_adapted_cv(cv, job, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    desc   = job.get("description","")[:3000]
    with client.messages.stream(
        model=model, max_tokens=4096,
        system="Tu es un expert en recrutement. Adapte le CV pour ce poste précis. Conserve TOUTES les infos réelles, ne rien inventer. Structure claire avec #, ##. Réponds en français.",
        messages=[{"role":"user","content":
            f"CV :\n{cv}\n\n---\nPoste : {job['title']} chez {job['company']}\nOffre :\n{desc}\n\nAdapte mon CV. Retourne uniquement le CV adapté."}],
    ) as s:
        for t in s.text_stream: yield t

def stream_cover_letter(cv, job, name, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    desc   = job.get("description","")[:2000]
    name   = name or "[Votre Prénom Nom]"
    with client.messages.stream(
        model=model, max_tokens=2048,
        system="Expert en lettres de motivation percutantes. Accroche originale, 2-3 réalisations concrètes du CV, appel à l'entretien. 3-4 paragraphes. Format lettre formelle. Français.",
        messages=[{"role":"user","content":
            f"Candidat : {name}\nPoste : {job['title']} chez {job['company']}\nCV :\n{cv}\nOffre :\n{desc}\n\nRédige la lettre de motivation."}],
    ) as s:
        for t in s.text_stream: yield t

# ══════════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="AutoCandidature IA", page_icon="🔍",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.big-title  { font-size:2.1rem; font-weight:800; color:#0f172a; margin-bottom:0; }
.subtitle   { font-size:0.9rem; color:#64748b; margin-bottom:1.2rem; }
.jcard      { background:#fff; border:1.5px solid #e2e8f0; border-radius:12px;
              padding:1rem 1.2rem; margin-bottom:0.8rem;
              box-shadow:0 1px 4px rgba(0,0,0,.05); }
.jcard:hover{ border-color:#6366f1; }
.jtitle     { font-size:1rem; font-weight:700; color:#1e293b; margin-bottom:2px; }
.jmeta      { font-size:0.8rem; color:#64748b; }
.badge      { display:inline-block; border-radius:5px; padding:1px 7px;
              font-size:0.71rem; font-weight:600; margin-right:3px; margin-bottom:3px; }
.b-blue     { background:#dbeafe; color:#1d4ed8; }
.b-green    { background:#dcfce7; color:#15803d; }
.b-orange   { background:#ffedd5; color:#c2410c; }
.b-purple   { background:#ede9fe; color:#7c3aed; }
.b-gray     { background:#f1f5f9; color:#475569; }
.mission-li { margin:2px 0; padding-left:1rem; font-size:0.85rem; color:#334155; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">🔍 AutoCandidature IA</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Recherche intelligente sur 140 000 sites · Expansion automatique du domaine · Résumé IA de chaque offre · Candidature personnalisée en 1 clic</p>', unsafe_allow_html=True)

# ── SIDEBAR ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Claude IA")
    default_key = ""
    try:    default_key = st.secrets.get("ANTHROPIC_API_KEY","")
    except: pass
    if default_key:
        api_key = default_key
        st.success("🔑 Clé Claude chargée")
    else:
        api_key = st.text_input("Clé API Anthropic", type="password", placeholder="sk-ant-...")

    model = st.selectbox("Modèle",
        ["claude-sonnet-4-6","claude-opus-4-6","claude-haiku-4-5-20251001"])

    st.divider()
    st.header("🔑 Sources d'emploi")

    with st.expander("Jooble ⭐ (recommandé — 140K sites)", expanded=True):
        st.markdown("**Gratuit · 500 req/jour**")
        st.markdown("[→ Obtenir une clé gratuite](https://jooble.org/api/registered)")
        jooble_key = st.text_input("Clé Jooble", type="password", placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

    with st.expander("Adzuna (Indeed FR, Cadremploi, Monster…)", expanded=False):
        st.markdown("[→ Clé gratuite](https://developer.adzuna.com/)")
        adzuna_id  = st.text_input("App ID",  placeholder="xxxxxxxx")
        adzuna_key = st.text_input("App Key", placeholder="xxxxxxxxxx", type="password")

    with st.expander("SerpAPI — Google Jobs (optionnel)", expanded=False):
        st.markdown("**100 req/mois gratuites** — meilleure qualité")
        st.markdown("[→ Clé gratuite](https://serpapi.com/)")
        serpapi_key = st.text_input("SerpAPI Key", type="password", placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    st.divider()
    st.header("👤 Mon profil")
    applicant_name = st.text_input("Nom complet", placeholder="Jean Dupont")
    cv_source = st.radio("Mon CV", ["📎 Uploader","✏️ Coller"])
    cv_content = st.session_state.get("cv_content","")
    if "Uploader" in cv_source:
        up = st.file_uploader("PDF, DOCX ou TXT", type=["pdf","docx","txt"])
        if up:
            cv_content = load_cv_file(up)
            st.session_state["cv_content"] = cv_content
            st.success(f"✅ {len(cv_content)} caractères")
    else:
        t = st.text_area("CV", value=cv_content, height=180, placeholder="Expériences, compétences…")
        if t: cv_content = t; st.session_state["cv_content"] = cv_content

    try: jooble_key
    except NameError: jooble_key=""
    try: adzuna_id; adzuna_key
    except NameError: adzuna_id=""; adzuna_key=""
    try: serpapi_key
    except NameError: serpapi_key=""

# ── RECHERCHE ──────────────────────────────────────────────────────
st.markdown("### 🎯 Votre recherche")
r1, r2, r3, r4, r5 = st.columns([3, 2, 1.5, 1, 1])
with r1: keywords = st.text_input("Métier / Poste", placeholder="Data Analyst · Développeur Python · Chef de projet…", label_visibility="collapsed")
with r2: location = st.text_input("Ville",          placeholder="Orléans · Paris · Lyon…",                         label_visibility="collapsed")
with r3: country  = st.selectbox("Pays", ["France","Belgique","Suisse","Canada","USA","UK","Allemagne"],             label_visibility="collapsed")
with r4: radius   = st.selectbox("Rayon", [10,25,50,100,200], index=2, format_func=lambda x: f"{x} km",             label_visibility="collapsed")
with r5: search_btn = st.button("🔍 Chercher", type="primary", use_container_width=True, disabled=not keywords)

c1, c2, c3 = st.columns(3)
with c1: include_remote = st.checkbox("Inclure le remote", value=False)
with c2: expand_domain  = st.checkbox("Élargir au domaine (IA)", value=True,
             help="Claude suggère des titres connexes et les recherche en parallèle")
with c3: auto_summarize = st.checkbox("Résumé IA de l'offre sélectionnée", value=True,
             help="Claude analyse l'offre et extrait missions, compétences, profil")

# ── LANCEMENT ──────────────────────────────────────────────────────
if search_btn and keywords:
    # 1. Expansion du domaine par Claude
    extra_kws = []
    if expand_domain and api_key:
        with st.spinner("🧠 Claude analyse le domaine et génère les recherches connexes…"):
            extra_kws = expand_keywords(keywords, api_key, model)
        if extra_kws:
            st.info(f"🔎 Recherches parallèles : **{keywords}** + {' · '.join(extra_kws)}")

    # 2. Recherches parallèles
    with st.spinner("🔍 Recherche en cours sur toutes les sources…"):
        raw = run_all_searches(
            primary_keyword=keywords,
            extra_keywords=extra_kws,
            location=location,
            country=country,
            radius=radius,
            include_remote=include_remote,
            jooble_key=jooble_key,
            adzuna_id=adzuna_id,
            adzuna_key=adzuna_key,
            serpapi_key=serpapi_key,
        )

    # 3. Filtre + dédup
    jobs = filter_and_dedupe(raw, location, country, include_remote)

    st.session_state.update({
        "jobs":             jobs,
        "search_done":      True,
        "selected_job":     None,
        "generated_cv":     "",
        "generated_letter": "",
        "extra_kws":        extra_kws,
    })

# ── AFFICHAGE RÉSULTATS ────────────────────────────────────────────
SOURCE_BADGE = {
    "jooble":   ("b-purple","Jooble"),
    "adzuna":   ("b-blue",  "Adzuna"),
    "google":   ("b-green", "Google"),
    "remotive": ("b-orange","Remote"),
    "serpapi":  ("b-green", "Google"),
}

def make_badge(source: str) -> str:
    k = source.lower()
    for key,(cls,label) in SOURCE_BADGE.items():
        if key in k: return f'<span class="badge {cls}">{label}</span>'
    return f'<span class="badge b-gray">{source[:12]}</span>'

if st.session_state.get("search_done"):
    jobs: list[dict] = st.session_state.get("jobs", [])

    st.divider()
    col_list, col_detail = st.columns([1, 1.4], gap="large")

    with col_list:
        if not jobs:
            st.warning("Aucune offre trouvée. Ajoutez une clé Jooble ou modifiez les mots-clés.")
        else:
            src_count: dict = {}
            for j in jobs:
                s = j["source"].split("(")[0].strip()
                src_count[s] = src_count.get(s,0)+1
            st.markdown(f"**{len(jobs)} offres trouvées** — " +
                        " · ".join(f"{k} ({v})" for k,v in src_count.items()))

            for i, job in enumerate(jobs[:60]):
                remote_badge = '<span class="badge b-green">🌍 Remote</span>' if job.get("is_remote") else ""
                salary_html  = f'<div class="jmeta">💰 {job["salary"]}</div>' if job.get("salary") else ""
                contract_html= f'<span class="badge b-gray">{job["contract"]}</span>' if job.get("contract") else ""
                posted_html  = f'<span class="jmeta"> · {job["posted"]}</span>' if job.get("posted") else ""

                st.markdown(f"""<div class="jcard">
{make_badge(job['source'])}{remote_badge}{contract_html}
<div class="jtitle">{job['title']}</div>
<div class="jmeta">🏢 {job['company']} &nbsp;·&nbsp; 📍 {job['location']}{posted_html}</div>
{salary_html}
</div>""", unsafe_allow_html=True)

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("📄 Voir & Postuler", key=f"sel_{i}", use_container_width=True):
                        st.session_state["selected_job"]     = job
                        st.session_state["generated_cv"]     = ""
                        st.session_state["generated_letter"] = ""
                with b2:
                    if job.get("url"):
                        st.link_button("🔗 Offre originale", job["url"], use_container_width=True)

    with col_detail:
        selected = st.session_state.get("selected_job")

        if not selected:
            st.markdown("#### 👈 Sélectionnez une offre")
            st.info("Cliquez sur « Voir & Postuler » pour afficher le récapitulatif et générer votre candidature.")

        else:
            # ── Récapitulatif de l'offre ──────────────────────────
            st.markdown(f"## {selected['title']}")

            m1, m2, m3 = st.columns(3)
            m1.markdown(f"🏢 **{selected['company']}**")
            m2.markdown(f"📍 {selected['location']}")
            if selected.get("salary"):
                m3.markdown(f"💰 {selected['salary']}")
            if selected.get("contract"):
                st.markdown(f"📝 *{selected['contract']}*")
            if selected.get("posted"):
                st.caption(f"Publiée le {selected['posted']}")
            if selected.get("url"):
                st.link_button("🔗 Voir l'offre originale", selected["url"])

            st.divider()

            # Résumé IA ou missions brutes
            ai = selected.get("ai_summary")

            if auto_summarize and not ai and api_key:
                with st.spinner("🧠 Claude analyse l'offre…"):
                    selected = summarize_job(selected, api_key, model)
                    st.session_state["selected_job"] = selected
                    ai = selected.get("ai_summary")

            if ai:
                st.markdown("#### 📋 Récapitulatif de l'offre")

                if ai.get("missions"):
                    st.markdown("**🎯 Missions principales**")
                    for m in ai["missions"]:
                        st.markdown(f'<div class="mission-li">• {m}</div>', unsafe_allow_html=True)

                if ai.get("competences"):
                    st.markdown("**🛠️ Compétences recherchées**")
                    tags = "".join(f'<span class="badge b-blue">{c}</span>' for c in ai["competences"])
                    st.markdown(tags, unsafe_allow_html=True)

                if ai.get("profil"):
                    st.markdown(f"**👤 Profil recherché**  \n{ai['profil']}")

                if ai.get("avantages"):
                    st.markdown("**✨ Avantages**")
                    for a in ai["avantages"]:
                        st.markdown(f'<div class="mission-li">✓ {a}</div>', unsafe_allow_html=True)

                if ai.get("ambiance"):
                    st.markdown(f"**🏠 Culture** : *{ai['ambiance']}*")

            else:
                # Fallback : missions brutes + description
                missions = selected.get("missions",[])
                if missions:
                    st.markdown("**🎯 Missions**")
                    for m in missions:
                        st.markdown(f'<div class="mission-li">• {m}</div>', unsafe_allow_html=True)

                with st.expander("📃 Description complète", expanded=not bool(missions)):
                    desc = selected.get("description","")
                    st.markdown(desc[:4000] + ("…" if len(desc)>4000 else "") or "*Non disponible*")

            st.divider()

            # ── Générer la candidature ────────────────────────────
            if not cv_content:
                st.warning("⚠️ Chargez votre CV dans la barre latérale pour générer une candidature.")
            elif not api_key:
                st.warning("⚠️ Entrez votre clé API Anthropic dans la barre latérale.")
            else:
                if st.button("🚀 Générer CV adapté + Lettre de motivation",
                             type="primary", use_container_width=True):
                    tab_cv, tab_lm = st.tabs(["📋 CV Adapté", "✉️ Lettre de motivation"])
                    with tab_cv:
                        box, full_cv = st.empty(), ""
                        try:
                            for chunk in stream_adapted_cv(cv_content, selected, api_key, model):
                                full_cv += chunk; box.markdown(full_cv)
                            st.session_state["generated_cv"] = full_cv
                        except Exception as e: st.error(f"Erreur : {e}")
                    with tab_lm:
                        box2, full_lm = st.empty(), ""
                        try:
                            for chunk in stream_cover_letter(cv_content, selected, applicant_name, api_key, model):
                                full_lm += chunk; box2.markdown(full_lm)
                            st.session_state["generated_letter"] = full_lm
                        except Exception as e: st.error(f"Erreur : {e}")

            # Téléchargements
            gen_cv = st.session_state.get("generated_cv","")
            gen_lm = st.session_state.get("generated_letter","")
            if gen_cv or gen_lm:
                st.markdown("**💾 Télécharger**")
                d1,d2,d3,d4 = st.columns(4)
                if gen_cv:
                    cv_docx = export_docx(gen_cv)
                    if cv_docx: d1.download_button("📥 CV .docx", cv_docx, "cv_adapte.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)
                    d2.download_button("📥 CV .txt", gen_cv.encode(), "cv_adapte.txt",
                        "text/plain", use_container_width=True)
                if gen_lm:
                    lm_docx = export_docx(gen_lm)
                    if lm_docx: d3.download_button("📥 Lettre .docx", lm_docx, "lettre.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)
                    d4.download_button("📥 Lettre .txt", gen_lm.encode(), "lettre.txt",
                        "text/plain", use_container_width=True)

st.divider()
st.caption("AutoCandidature IA · Jooble (140K sites) · Adzuna · SerpAPI/Google Jobs · Remotive · Propulsé par Claude (Anthropic)")
