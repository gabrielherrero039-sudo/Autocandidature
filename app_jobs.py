"""
AutoCandidature IA — Recherche multi-sources + Candidature automatique
Sources : LinkedIn · Indeed · Glassdoor · Welcome to the Jungle · Adzuna · Remotive
"""

import io
import re
import time
import requests
import streamlit as st
import anthropic

# ══════════════════════════════════════════════════════════════════
# CHARGEMENT / EXPORT CV
# ══════════════════════════════════════════════════════════════════

def extract_pdf(data: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        pass
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""

def extract_docx_text(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""

def load_cv_file(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        return extract_pdf(data)
    if name.endswith(".docx"):
        return extract_docx_text(data)
    return data.decode("utf-8", errors="ignore")

def export_docx(content: str) -> bytes | None:
    try:
        import docx as dx
        doc = dx.Document()
        for line in content.split("\n"):
            s = line.strip()
            if s.startswith("# "):
                doc.add_heading(s[2:], level=1)
            elif s.startswith("## "):
                doc.add_heading(s[3:], level=2)
            elif s == "":
                doc.add_paragraph("")
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

# ══════════════════════════════════════════════════════════════════
# RECHERCHE D'OFFRES
# ══════════════════════════════════════════════════════════════════

def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _fmt_salary(mn, mx, currency="€") -> str:
    try:
        if mn and mx:
            return f"{int(float(mn)):,} – {int(float(mx)):,} {currency}/an"
        if mn:
            return f"À partir de {int(float(mn)):,} {currency}/an"
        if mx:
            return f"Jusqu'à {int(float(mx)):,} {currency}/an"
    except Exception:
        pass
    return ""

# ── LinkedIn + Indeed + Glassdoor via python-jobspy ──────────────

def search_jobspy(keywords: str, location: str, sites: list[str],
                  country: str = "France", max_results: int = 15) -> list[dict]:
    """
    Scrape LinkedIn, Indeed et/ou Glassdoor via python-jobspy.
    Nécessite : pip install python-jobspy
    """
    try:
        from jobspy import scrape_jobs
        import pandas as pd

        # Mapping pays
        country_map = {
            "France": "France", "Belgique": "Belgium", "Suisse": "Switzerland",
            "Canada": "Canada", "USA": "USA", "UK": "UK", "Allemagne": "Germany",
        }
        country_indeed = country_map.get(country, "France")

        df = scrape_jobs(
            site_name=sites,
            search_term=keywords,
            location=f"{location}, {country}" if location else country,
            results_wanted=max_results,
            hours_old=720,           # offres des 30 derniers jours
            country_indeed=country_indeed,
            linkedin_fetch_description=True,
        )

        if df is None or df.empty:
            return []

        jobs = []
        for _, row in df.iterrows():
            source_name = str(row.get("site", "")).capitalize()
            salary = _fmt_salary(
                row.get("min_amount"), row.get("max_amount"),
                row.get("currency", "€") or "€"
            )
            jobs.append({
                "source": source_name,
                "title": str(row.get("title", "")),
                "company": str(row.get("company", "N/A")),
                "location": str(row.get("location", location)),
                "description": _clean_html(str(row.get("description", ""))),
                "url": str(row.get("job_url", "")),
                "salary": salary,
                "contract": str(row.get("job_type", "") or ""),
                "posted": str(row.get("date_posted", "") or "")[:10],
                "is_remote": bool(row.get("is_remote", False)),
            })
        return jobs

    except ImportError:
        st.warning("⚠️ python-jobspy non installé — LinkedIn/Indeed/Glassdoor indisponibles. Vérifiez requirements.txt.")
        return []
    except Exception as e:
        st.warning(f"JobSpy ({', '.join(sites)}) : {e}")
        return []

# ── Welcome to the Jungle ─────────────────────────────────────────

def search_wttj(keywords: str, location: str, country: str,
                max_results: int = 20) -> list[dict]:
    """Scrape Welcome to the Jungle via leur API publique."""
    try:
        # Construire la requête de localisation
        location_query = location if location else country

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Origin": "https://www.welcometothejungle.com",
            "Referer": "https://www.welcometothejungle.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        params = {
            "query": keywords,
            "page": 1,
            "per_page": max_results,
            "language": "fr",
        }
        if location_query:
            params["aroundQuery"] = location_query

        r = requests.get(
            "https://api.welcometothejungle.com/api/v1/jobs",
            headers=headers,
            params=params,
            timeout=12,
        )

        if r.status_code != 200:
            # Fallback : chercher via leur moteur de recherche public
            return _wttj_fallback(keywords, location_query, max_results)

        data = r.json()
        jobs_raw = data.get("jobs", []) or data.get("results", []) or []

        jobs = []
        for item in jobs_raw[:max_results]:
            org = item.get("organization", {}) or {}
            office = item.get("office", {}) or {}
            loc = office.get("city") or location or "France"
            if office.get("country_code"):
                loc += f", {office.get('country_code', '').upper()}"

            jobs.append({
                "source": "Welcome to the Jungle",
                "title": item.get("name", ""),
                "company": org.get("name", "N/A"),
                "location": loc,
                "description": _clean_html(item.get("description", "") or ""),
                "url": f"https://www.welcometothejungle.com/fr/companies/{org.get('slug', '')}/jobs/{item.get('slug', '')}",
                "salary": "",
                "contract": item.get("contract_type", ""),
                "posted": item.get("published_at", "")[:10] if item.get("published_at") else "",
                "is_remote": "remote" in str(item.get("remote", "")).lower(),
            })
        return jobs

    except Exception as e:
        st.warning(f"Welcome to the Jungle : {e}")
        return []

def _wttj_fallback(keywords: str, location: str, max_results: int) -> list[dict]:
    """Fallback WTTJ : scrape la page de résultats HTML."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        query = f"{keywords} {location}".strip()
        r = requests.get(
            f"https://www.welcometothejungle.com/fr/jobs?query={requests.utils.quote(query)}",
            headers=headers, timeout=12
        )
        # Extraire les offres JSON dans le script Next.js
        matches = re.findall(r'"name":"([^"]+)","slug":"([^"]+)".*?"organization":\{"name":"([^"]+)"', r.text)
        jobs = []
        for title, slug, company in matches[:max_results]:
            jobs.append({
                "source": "Welcome to the Jungle",
                "title": title,
                "company": company,
                "location": location or "France",
                "description": "",
                "url": f"https://www.welcometothejungle.com/fr/jobs/{slug}",
                "salary": "",
                "contract": "",
                "posted": "",
                "is_remote": False,
            })
        return jobs
    except Exception:
        return []

# ── Adzuna (agrège Indeed FR, Monster, Cadremploi, Reed…) ────────

def search_adzuna(keywords: str, location: str, country: str,
                  app_id: str, app_key: str, max_results: int = 20) -> list[dict]:
    if not app_id or not app_key:
        return []
    country_codes = {
        "France": "fr", "Belgique": "be", "Suisse": "ch",
        "Canada": "ca", "USA": "us", "UK": "gb", "Allemagne": "de",
    }
    cc = country_codes.get(country, "fr")
    try:
        r = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
            params={
                "app_id": app_id, "app_key": app_key,
                "results_per_page": max_results,
                "what": keywords, "where": location,
                "content-type": "application/json",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("results", []):
            jobs.append({
                "source": "Adzuna",
                "title": item.get("title", ""),
                "company": item.get("company", {}).get("display_name", "N/A"),
                "location": item.get("location", {}).get("display_name", location),
                "description": _clean_html(item.get("description", "")),
                "url": item.get("redirect_url", ""),
                "salary": _fmt_salary(item.get("salary_min"), item.get("salary_max")),
                "contract": item.get("contract_time", ""),
                "posted": item.get("created", "")[:10],
                "is_remote": False,
            })
        return jobs
    except Exception as e:
        st.warning(f"Adzuna : {e}")
        return []

# ── Remotive (Remote only, sans clé) ─────────────────────────────

def search_remotive(keywords: str, max_results: int = 15) -> list[dict]:
    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": keywords, "limit": max_results},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("jobs", [])[:max_results]:
            jobs.append({
                "source": "Remotive (Remote)",
                "title": item.get("title", ""),
                "company": item.get("company_name", "N/A"),
                "location": "🌍 Remote — " + item.get("candidate_required_location", "Mondial"),
                "description": _clean_html(item.get("description", "")),
                "url": item.get("url", ""),
                "salary": item.get("salary", ""),
                "contract": item.get("job_type", ""),
                "posted": item.get("publication_date", "")[:10],
                "is_remote": True,
            })
        return jobs
    except Exception:
        return []

# ── Filtre de localisation ────────────────────────────────────────

COUNTRY_ALIASES = {
    "France": ["france", "fr ", "paris", "lyon", "marseille", "toulouse", "nantes",
               "bordeaux", "lille", "strasbourg", "rennes", "orléans", "orleans",
               "montpellier", "nice"],
    "Belgique": ["belgique", "belgium", "bruxelles", "brussels", "be "],
    "Suisse":   ["suisse", "switzerland", "genève", "zurich", "berne"],
    "Canada":   ["canada", "québec", "montreal", "toronto", "vancouver"],
    "USA":      ["usa", "united states", "new york", "california", "texas", "us "],
    "UK":       ["uk", "united kingdom", "london", "england", "scotland"],
    "Allemagne":["germany", "deutschland", "berlin", "munich", "hamburg"],
}

def location_matches(job_loc: str, city: str, country: str) -> bool:
    loc = job_loc.lower()
    if "remote" in loc or "🌍" in job_loc:
        return True
    if not city and not country:
        return True
    if city and city.lower() in loc:
        return True
    for alias in COUNTRY_ALIASES.get(country, [country.lower()]):
        if alias in loc:
            return True
    return False

# ── Agrégateur principal ──────────────────────────────────────────

def aggregate_jobs(keywords, location, country, include_remote,
                   use_linkedin, use_indeed, use_glassdoor, use_wttj,
                   adzuna_id, adzuna_key) -> list[dict]:

    all_jobs: list[dict] = []
    steps = []

    jobspy_sites = []
    if use_linkedin:   jobspy_sites.append("linkedin")
    if use_indeed:     jobspy_sites.append("indeed")
    if use_glassdoor:  jobspy_sites.append("glassdoor")

    if jobspy_sites:
        steps.append(("jobspy", jobspy_sites))
    if use_wttj:
        steps.append(("wttj", []))
    if adzuna_id and adzuna_key:
        steps.append(("adzuna", []))
    if include_remote:
        steps.append(("remotive", []))

    total = max(len(steps), 1)
    prog = st.progress(0, text="Démarrage de la recherche...")

    for i, (src, sites) in enumerate(steps):
        pct = int((i / total) * 90)
        if src == "jobspy":
            label = f"🔍 {', '.join(s.capitalize() for s in sites)}..."
            prog.progress(pct, text=label)
            jobs = search_jobspy(keywords, location, sites, country)
            all_jobs.extend(jobs)
        elif src == "wttj":
            prog.progress(pct, text="🌿 Welcome to the Jungle...")
            jobs = search_wttj(keywords, location, country)
            all_jobs.extend(jobs)
        elif src == "adzuna":
            prog.progress(pct, text="📋 Adzuna (Indeed FR, Monster, Cadremploi...)...")
            jobs = search_adzuna(keywords, location, country, adzuna_id, adzuna_key)
            all_jobs.extend(jobs)
        elif src == "remotive":
            prog.progress(pct, text="🌍 Remotive (offres remote)...")
            jobs = search_remotive(keywords)
            all_jobs.extend(jobs)

    prog.progress(95, text="Filtrage par localisation...")

    # Filtre géographique
    filtered = [j for j in all_jobs if location_matches(j.get("location", ""), location, country)]

    # Dédoublonnage
    seen: set = set()
    unique: list[dict] = []
    for j in filtered:
        key = (j["title"].lower()[:40], j["company"].lower()[:30])
        if key not in seen:
            seen.add(key)
            unique.append(j)

    prog.progress(100, text=f"✅ {len(unique)} offres trouvées à {location or country} !")
    time.sleep(0.4)
    prog.empty()
    return unique

# ══════════════════════════════════════════════════════════════════
# GÉNÉRATION IA (Claude)
# ══════════════════════════════════════════════════════════════════

def stream_adapted_cv(cv, job_desc, job_title, company, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=model, max_tokens=4096,
        system="""Tu es un expert en recrutement et rédaction de CV professionnels.
Adapte le CV fourni pour maximiser les chances d'obtenir un entretien :
- Conserve TOUTES les informations réelles (ne rien inventer)
- Réorganise et reformule pour coller aux exigences du poste
- Intègre les mots-clés de l'offre naturellement
- Structure : # Nom | ## Profil | ## Expériences | ## Compétences | ## Formation
- Réponds en français, ton professionnel""",
        messages=[{"role": "user", "content":
            f"Mon CV :\n\n{cv}\n\n---\n\nPoste : {job_title} chez {company}\n\nDescription :\n{job_desc[:3000]}\n\n---\n\nAdapte mon CV pour ce poste. Retourne uniquement le CV adapté."}],
    ) as stream:
        for text in stream.text_stream:
            yield text

def stream_cover_letter(cv, job_desc, job_title, company, name, api_key, model):
    client = anthropic.Anthropic(api_key=api_key)
    name_str = name if name else "[Votre Prénom Nom]"
    with client.messages.stream(
        model=model, max_tokens=2048,
        system="""Tu es un expert en rédaction de lettres de motivation percutantes.
La lettre doit :
- Avoir une accroche originale liée à l'entreprise/secteur
- Citer 2-3 réalisations concrètes en lien avec l'offre
- Être 3-4 paragraphes, ton professionnel et chaleureux
- Se terminer par un appel à l'entretien
- Inclure objet, date, formule de politesse
- Être en français""",
        messages=[{"role": "user", "content":
            f"Candidat : {name_str}\nPoste : {job_title} chez {company}\n\nCV :\n{cv}\n\nOffre :\n{job_desc[:2000]}\n\nRédige la lettre de motivation."}],
    ) as stream:
        for text in stream.text_stream:
            yield text

# ══════════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="AutoCandidature IA", page_icon="🔍", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.big-title { font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-bottom: 0; }
.subtitle  { font-size: 0.95rem; color: #64748b; margin-bottom: 1.5rem; }
.job-card  { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
             padding: 0.9rem 1.1rem; margin-bottom: 0.7rem; }
.job-title { font-size: 1rem; font-weight: 700; color: #1e293b; }
.job-meta  { font-size: 0.82rem; color: #64748b; }
.badge     { display:inline-block; background:#dbeafe; color:#1d4ed8; border-radius:4px;
             padding:1px 7px; font-size:0.72rem; font-weight:600; margin-right:4px; }
.badge-g   { background:#dcfce7; color:#15803d; }
.badge-r   { background:#fee2e2; color:#b91c1c; }
.badge-y   { background:#fef9c3; color:#854d0e; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">🔍 AutoCandidature IA</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Recherchez des offres sur LinkedIn · Indeed · Welcome to the Jungle · Glassdoor · Adzuna, puis adaptez votre candidature en 1 clic avec l\'IA.</p>', unsafe_allow_html=True)

# ── SIDEBAR ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration IA")
    default_key = ""
    try:
        default_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if default_key:
        api_key = default_key
        st.success("🔑 Clé Claude chargée")
    else:
        api_key = st.text_input("Clé API Anthropic", type="password", placeholder="sk-ant-...")

    model = st.selectbox("Modèle Claude",
        ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"])

    st.divider()
    st.header("🌐 Sources de recherche")
    st.caption("Cochez les sites à interroger")
    use_linkedin   = st.checkbox("LinkedIn",              value=True)
    use_indeed     = st.checkbox("Indeed",                value=True)
    use_wttj       = st.checkbox("Welcome to the Jungle", value=True)
    use_glassdoor  = st.checkbox("Glassdoor",             value=False)
    include_remote = st.checkbox("+ Offres Remote (Remotive)", value=False)

    st.divider()
    with st.expander("🔑 Adzuna (optionnel — plus d'offres FR)", expanded=False):
        st.markdown("[Clé gratuite → developer.adzuna.com](https://developer.adzuna.com/)")
        adzuna_id  = st.text_input("App ID",  placeholder="xxxxxxxx")
        adzuna_key = st.text_input("App Key", placeholder="xxxxxxxx", type="password")

    st.divider()
    st.header("👤 Mon profil")
    applicant_name = st.text_input("Nom complet", placeholder="Jean Dupont")

    cv_source = st.radio("Mon CV", ["Uploader", "Coller le texte"])
    cv_content = st.session_state.get("cv_content", "")
    if cv_source == "Uploader":
        up = st.file_uploader("CV (PDF, DOCX, TXT)", type=["pdf","docx","txt"])
        if up:
            cv_content = load_cv_file(up)
            st.session_state["cv_content"] = cv_content
            st.success(f"✅ {len(cv_content)} caractères chargés")
    else:
        t = st.text_area("Texte du CV", value=cv_content, height=180,
                         placeholder="Nom, titre, expériences...")
        if t:
            cv_content = t
            st.session_state["cv_content"] = cv_content

    # Récupérer les vars Adzuna si non définies
    try: adzuna_id
    except NameError: adzuna_id = ""; adzuna_key = ""

# ── BARRE DE RECHERCHE ─────────────────────────────────────────────
st.markdown("### 🔎 Recherche d'offres")
c1, c2, c3, c4 = st.columns([3, 2, 1.5, 1])
with c1:
    keywords = st.text_input("Mots-clés", placeholder="Data Scientist · Développeur · Marketing Manager...", label_visibility="collapsed")
with c2:
    location = st.text_input("Ville", placeholder="Paris · Lyon · Orléans · Remote...", label_visibility="collapsed")
with c3:
    country = st.selectbox("Pays", ["France","Belgique","Suisse","Canada","USA","UK","Allemagne"], label_visibility="collapsed")
with c4:
    active_sources = sum([use_linkedin, use_indeed, use_wttj, use_glassdoor, include_remote, bool(adzuna_id)])
    search_btn = st.button(f"🔍 Rechercher ({active_sources} sources)", type="primary",
                           use_container_width=True, disabled=not keywords)

with st.expander("⚙️ Filtres"):
    f1, f2 = st.columns(2)
    with f1:
        sort_by = st.selectbox("Trier par", ["Pertinence", "Date (récent)", "Entreprise A-Z"])
    with f2:
        filter_remote_only = st.checkbox("Remote uniquement")

# ── LANCEMENT ──────────────────────────────────────────────────────
if search_btn and keywords:
    st.session_state["jobs"]         = aggregate_jobs(
        keywords, location, country, include_remote,
        use_linkedin, use_indeed, use_glassdoor, use_wttj,
        adzuna_id, adzuna_key
    )
    st.session_state["search_done"]  = True
    st.session_state["selected_job"] = None
    st.session_state["generated_cv"] = ""
    st.session_state["generated_letter"] = ""

# ── RÉSULTATS ──────────────────────────────────────────────────────
SOURCE_COLORS = {
    "linkedin":             ("badge",   "in"),
    "indeed":               ("badge-y", "indeed"),
    "glassdoor":            ("badge-g", "glassdoor"),
    "welcome to the jungle":("badge-g", "WTTJ"),
    "adzuna":               ("badge",   "adzuna"),
    "remotive":             ("badge-r", "remote"),
}

def source_badge(source: str) -> str:
    k = source.lower()
    for key, (cls, label) in SOURCE_COLORS.items():
        if key in k:
            return f'<span class="{cls}">{label}</span>'
    return f'<span class="badge">{source[:10]}</span>'

if st.session_state.get("search_done"):
    jobs: list[dict] = st.session_state.get("jobs", [])

    if filter_remote_only:
        jobs = [j for j in jobs if j.get("is_remote") or "remote" in j["location"].lower()]
    if sort_by == "Date (récent)":
        jobs = sorted(jobs, key=lambda j: j.get("posted",""), reverse=True)
    elif sort_by == "Entreprise A-Z":
        jobs = sorted(jobs, key=lambda j: j.get("company","").lower())

    st.divider()

    if not jobs:
        st.warning("Aucune offre trouvée pour cette localisation. Essayez d'autres mots-clés ou une ville différente.")
    else:
        # Stats sources
        srcs: dict = {}
        for j in jobs:
            s = j["source"].split(" (")[0].split("/")[0].strip()
            srcs[s] = srcs.get(s, 0) + 1
        st.markdown(f"**{len(jobs)} offres** — " + " · ".join(f"{k} ({v})" for k, v in srcs.items()))

        col_list, col_detail = st.columns([1, 1.3], gap="large")

        with col_list:
            st.markdown("#### Offres")
            for i, job in enumerate(jobs[:60]):
                remote_badge = '<span class="badge-r">🌍 remote</span>' if job.get("is_remote") else ""
                salary_html  = f'<div class="job-meta">💰 {job["salary"]}</div>' if job.get("salary") else ""
                posted_html  = f'<span class="job-meta"> · {job["posted"]}</span>' if job.get("posted") else ""

                st.markdown(f"""<div class="job-card">
{source_badge(job['source'])}{remote_badge}
<div class="job-title">{job['title']}</div>
<div class="job-meta">🏢 {job['company']} &nbsp;·&nbsp; 📍 {job['location']}{posted_html}</div>
{salary_html}</div>""", unsafe_allow_html=True)

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("📄 Voir & Postuler", key=f"sel_{i}", use_container_width=True):
                        st.session_state["selected_job"]      = job
                        st.session_state["generated_cv"]      = ""
                        st.session_state["generated_letter"]  = ""
                with b2:
                    if job.get("url"):
                        st.link_button("🔗 Offre", job["url"], use_container_width=True)

        with col_detail:
            selected = st.session_state.get("selected_job")
            if not selected:
                st.info("👈 Cliquez sur une offre pour voir les détails et générer votre candidature.")
            else:
                st.markdown(f"#### {selected['title']}")
                st.markdown(f"🏢 **{selected['company']}** &nbsp;·&nbsp; 📍 {selected['location']}")
                meta_cols = st.columns(3)
                if selected.get("salary"):
                    meta_cols[0].metric("Salaire", selected["salary"])
                if selected.get("contract"):
                    meta_cols[1].metric("Contrat", selected["contract"])
                if selected.get("posted"):
                    meta_cols[2].metric("Publié le", selected["posted"])
                if selected.get("url"):
                    st.link_button("🔗 Voir l'offre originale", selected["url"])

                with st.expander("📃 Description complète", expanded=True):
                    desc = selected.get("description","")
                    st.markdown(desc[:4000] + ("…" if len(desc) > 4000 else "") if desc else "*Description non disponible*")

                st.divider()
                if not cv_content:
                    st.warning("⚠️ Chargez votre CV dans la barre latérale pour postuler.")
                elif not api_key:
                    st.warning("⚠️ Entrez votre clé API Anthropic dans la barre latérale.")
                else:
                    if st.button("🚀 Générer CV adapté + Lettre de motivation", type="primary", use_container_width=True):
                        tab_cv, tab_letter = st.tabs(["📋 CV Adapté", "✉️ Lettre de motivation"])
                        with tab_cv:
                            box, full_cv = st.empty(), ""
                            try:
                                for chunk in stream_adapted_cv(cv_content, selected.get("description",""),
                                                               selected["title"], selected["company"], api_key, model):
                                    full_cv += chunk
                                    box.markdown(full_cv)
                                st.session_state["generated_cv"] = full_cv
                            except Exception as e:
                                st.error(f"Erreur IA : {e}")
                        with tab_letter:
                            box2, full_letter = st.empty(), ""
                            try:
                                for chunk in stream_cover_letter(cv_content, selected.get("description",""),
                                                                 selected["title"], selected["company"],
                                                                 applicant_name, api_key, model):
                                    full_letter += chunk
                                    box2.markdown(full_letter)
                                st.session_state["generated_letter"] = full_letter
                            except Exception as e:
                                st.error(f"Erreur IA : {e}")

                gen_cv     = st.session_state.get("generated_cv","")
                gen_letter = st.session_state.get("generated_letter","")
                if gen_cv or gen_letter:
                    st.markdown("**💾 Télécharger**")
                    d1, d2, d3, d4 = st.columns(4)
                    if gen_cv:
                        cv_docx = export_docx(gen_cv)
                        if cv_docx:
                            d1.download_button("📥 CV .docx", cv_docx, "cv_adapte.docx",
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True)
                        d2.download_button("📥 CV .txt", gen_cv.encode(), "cv_adapte.txt",
                            "text/plain", use_container_width=True)
                    if gen_letter:
                        l_docx = export_docx(gen_letter)
                        if l_docx:
                            d3.download_button("📥 Lettre .docx", l_docx, "lettre.docx",
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True)
                        d4.download_button("📥 Lettre .txt", gen_letter.encode(), "lettre.txt",
                            "text/plain", use_container_width=True)

st.divider()
st.caption("AutoCandidature IA · LinkedIn · Indeed · Welcome to the Jungle · Glassdoor · Adzuna · Remotive · Propulsé par Claude (Anthropic)")
