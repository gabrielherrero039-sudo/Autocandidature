"""
AutoCandidature IA — Recherche + Candidature automatique
Recherche d'offres sur Adzuna, Remotive, JSearch (RapidAPI)
puis génération de CV adapté + lettre de motivation via Claude.
"""

import io
import re
import time
import requests
import streamlit as st
import anthropic

# ══════════════════════════════════════════════════════════════════
# CHARGEMENT DU CV
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
        return "[Impossible de lire le PDF — essayez de coller le texte manuellement]"

def extract_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return "[Impossible de lire le DOCX — essayez de coller le texte manuellement]"

def load_cv_file(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        return extract_pdf(data)
    elif name.endswith(".docx"):
        return extract_docx(data)
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

def search_adzuna(keywords: str, location: str, country: str,
                  app_id: str, app_key: str, max_results: int = 20) -> list[dict]:
    """Adzuna API — agrège Indeed, Reed, CV-Library, Monster, etc."""
    if not app_id or not app_key:
        return []
    try:
        country_code = country.lower()[:2]
        url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": max_results,
            "what": keywords,
            "where": location,
            "content-type": "application/json",
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("results", []):
            jobs.append({
                "source": "Adzuna",
                "title": item.get("title", ""),
                "company": item.get("company", {}).get("display_name", "N/A"),
                "location": item.get("location", {}).get("display_name", location),
                "description": item.get("description", ""),
                "url": item.get("redirect_url", ""),
                "salary": _fmt_salary(item.get("salary_min"), item.get("salary_max")),
                "contract": item.get("contract_time", ""),
                "posted": item.get("created", "")[:10],
            })
        return jobs
    except Exception as e:
        st.warning(f"Adzuna : {e}")
        return []


def search_jsearch(keywords: str, location: str, rapidapi_key: str,
                   max_results: int = 20) -> list[dict]:
    """JSearch via RapidAPI — agrège LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs."""
    if not rapidapi_key:
        return []
    try:
        query = f"{keywords} in {location}" if location else keywords
        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        params = {"query": query, "num_pages": "2", "date_posted": "month"}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("data", [])[:max_results]:
            jobs.append({
                "source": f"JSearch ({item.get('job_publisher', 'Multi-board')})",
                "title": item.get("job_title", ""),
                "company": item.get("employer_name", "N/A"),
                "location": f"{item.get('job_city', '')} {item.get('job_country', '')}".strip(),
                "description": item.get("job_description", ""),
                "url": item.get("job_apply_link", ""),
                "salary": _fmt_salary(
                    item.get("job_min_salary"),
                    item.get("job_max_salary"),
                    item.get("job_salary_currency", ""),
                ),
                "contract": item.get("job_employment_type", ""),
                "posted": item.get("job_posted_at_datetime_utc", "")[:10],
            })
        return jobs
    except Exception as e:
        st.warning(f"JSearch : {e}")
        return []

def search_remotive_intl(keywords: str) -> list[dict]:
    """Remotive — offres remote mondiales, sans clé."""
    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": keywords, "limit": 15},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for item in r.json().get("jobs", [])[:15]:
            jobs.append({
                "source": "Remotive (Remote)",
                "title": item.get("title", ""),
                "company": item.get("company_name", "N/A"),
                "location": "🌍 Remote — " + item.get("candidate_required_location", "Mondial"),
                "description": re.sub(r"<[^>]+>", " ", item.get("description", "")),
                "url": item.get("url", ""),
                "salary": item.get("salary", "Non précisé"),
                "contract": item.get("job_type", "Full-time"),
                "posted": item.get("publication_date", "")[:10],
                "is_remote": True,
            })
        return jobs
    except Exception as e:
        return []

def _fmt_salary(mn, mx, currency="€") -> str:
    if mn and mx:
        return f"{int(mn):,} – {int(mx):,} {currency}/an"
    elif mn:
        return f"À partir de {int(mn):,} {currency}/an"
    elif mx:
        return f"Jusqu'à {int(mx):,} {currency}/an"
    return "Non précisé"

def location_matches(job_location: str, city: str, country: str) -> bool:
    """
    Vérifie si la localisation d'une offre correspond à la ville/pays demandé.
    Les offres remote passent toujours.
    """
    loc_lower = job_location.lower()
    # Remote → toujours inclus
    if "remote" in loc_lower or "🌍" in job_location:
        return True
    # Pas de ville précisée → on accepte tout
    if not city and not country:
        return True
    # Vérifie la ville
    if city and city.lower() in loc_lower:
        return True
    # Vérifie la région / le pays
    country_lower = country.lower()
    country_aliases = {
        "france": ["france", "fr", "français", "française"],
        "belgique": ["belgique", "belgium", "be", "belg"],
        "suisse": ["suisse", "switzerland", "ch", "swiss"],
        "canada": ["canada", "ca", "québec", "montreal"],
        "usa": ["usa", "united states", "us ", "new york", "california"],
        "uk": ["uk", "united kingdom", "london", "england"],
        "allemagne": ["germany", "deutschland", "de", "berlin", "munich"],
    }
    aliases = country_aliases.get(country_lower, [country_lower])
    for alias in aliases:
        if alias in loc_lower:
            return True
    return False


def aggregate_jobs(keywords, location, country, include_remote,
                   adzuna_id, adzuna_key, rapidapi_key) -> list[dict]:
    """Lance toutes les recherches, filtre par localisation et agrège."""
    all_jobs = []
    with st.spinner("🔍 Recherche en cours sur toutes les plateformes..."):
        prog = st.progress(0, text="Adzuna (Indeed, Monster, Reed, Cadremploi...)...")
        adz = search_adzuna(keywords, location, country, adzuna_id, adzuna_key)
        all_jobs.extend(adz)

        prog.progress(40, text="JSearch (LinkedIn, Indeed, Glassdoor, ZipRecruiter...)...")
        jsr = search_jsearch(keywords, f"{location}, {country}" if location else country, rapidapi_key)
        all_jobs.extend(jsr)

        if include_remote:
            prog.progress(75, text="Remotive (offres full remote)...")
            rem = search_remotive_intl(keywords)
            all_jobs.extend(rem)

        prog.progress(100, text=f"✅ {len(all_jobs)} offres brutes récupérées — filtrage...")
        time.sleep(0.3)
        prog.empty()

    # Filtre localisation
    filtered = []
    for j in all_jobs:
        if location_matches(j.get("location", ""), location, country):
            filtered.append(j)

    # Dédoublonnage par titre + entreprise
    seen = set()
    unique = []
    for j in filtered:
        key = (j["title"].lower()[:40], j["company"].lower()[:30])
        if key not in seen:
            seen.add(key)
            unique.append(j)
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
            f"Mon CV :\n\n{cv}\n\n---\n\nPoste visé : {job_title} chez {company}\n\nDescription du poste :\n{job_desc[:3000]}\n\n---\n\nAdapte mon CV pour ce poste précis. Garde mes vraies informations. Retourne uniquement le CV adapté."}],
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
- Avoir une accroche originale liée à l'entreprise ou au secteur
- Citer 2-3 réalisations concrètes du CV en lien avec l'offre
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

st.set_page_config(
    page_title="AutoCandidature IA",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.big-title { font-size: 2.4rem; font-weight: 800; color: #0f172a; margin-bottom: 0; }
.subtitle  { font-size: 1rem; color: #64748b; margin-bottom: 1.5rem; }
.job-card  { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
             padding: 1rem 1.2rem; margin-bottom: 0.8rem; }
.job-title { font-size: 1.05rem; font-weight: 700; color: #1e293b; }
.job-meta  { font-size: 0.85rem; color: #64748b; margin: 0.2rem 0; }
.badge     { display: inline-block; background: #dbeafe; color: #1d4ed8;
             border-radius: 4px; padding: 1px 7px; font-size: 0.75rem;
             font-weight: 600; margin-right: 4px; }
.badge-green { background: #dcfce7; color: #15803d; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">🔍 AutoCandidature IA</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Recherchez des offres sur tous les sites d\'emploi, puis générez automatiquement votre CV adapté et votre lettre de motivation.</p>', unsafe_allow_html=True)

# ── Barre latérale ─────────────────────────────────────────────────────────────
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
        api_key = st.text_input("Clé API Anthropic (Claude)", type="password", placeholder="sk-ant-...")

    model = st.selectbox("Modèle", ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"], index=0)

    st.divider()
    st.header("🔍 Clés API Recherche")
    st.caption("Les sources sans clé fonctionnent toujours.")

    with st.expander("Adzuna (recommandé — gratuit)", expanded=False):
        st.markdown("[Obtenir une clé gratuite](https://developer.adzuna.com/) — 250 req/jour")
        adzuna_id  = st.text_input("Adzuna App ID",  placeholder="xxxxxxxx")
        adzuna_key = st.text_input("Adzuna App Key", placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", type="password")

    with st.expander("JSearch / RapidAPI (optionnel)", expanded=False):
        st.markdown("[Obtenir une clé gratuite](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) — 100 req/mois\nAgrège LinkedIn, Indeed, Glassdoor, ZipRecruiter")
        rapidapi_key = st.text_input("RapidAPI Key", placeholder="xxxxxxxxxxxx", type="password")

    st.divider()
    st.header("👤 Mon profil")
    applicant_name = st.text_input("Mon nom complet", placeholder="Jean Dupont")

    cv_source = st.radio("Mon CV", ["Uploader un fichier", "Coller le texte"])
    cv_content = st.session_state.get("cv_content", "")

    if cv_source == "Uploader un fichier":
        uploaded = st.file_uploader("CV (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
        if uploaded:
            cv_content = load_cv_file(uploaded)
            st.session_state["cv_content"] = cv_content
            st.success(f"✅ CV chargé ({len(cv_content)} caractères)")
    else:
        cv_text = st.text_area("Coller mon CV ici", value=cv_content, height=200,
                               placeholder="Nom, titre, expériences...")
        if cv_text:
            cv_content = cv_text
            st.session_state["cv_content"] = cv_content

    if not hasattr(st.session_state, "adzuna_id"):
        pass
    try:
        adzuna_id
    except NameError:
        adzuna_id = ""
        adzuna_key = ""
        rapidapi_key = ""

# ── Barre de recherche principale ─────────────────────────────────────────────

st.markdown("### 🔎 Recherche d'offres")
c1, c2, c3, c4 = st.columns([3, 2, 1.5, 1])
with c1:
    keywords = st.text_input("Mots-clés", placeholder="Data Scientist, Marketing Manager, Développeur Python...", label_visibility="collapsed")
with c2:
    location = st.text_input("Ville / Région", placeholder="Paris, Lyon, Remote...", label_visibility="collapsed")
with c3:
    country = st.selectbox("Pays", ["France", "Belgique", "Suisse", "Canada", "USA", "UK", "Allemagne"], label_visibility="collapsed")
with c4:
    search_btn = st.button("🔍 Rechercher", type="primary", use_container_width=True, disabled=not keywords)

country_codes = {"France": "fr", "Belgique": "be", "Suisse": "ch", "Canada": "ca", "USA": "us", "UK": "gb", "Allemagne": "de"}

# Filtres
with st.expander("⚙️ Filtres avancés"):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filter_remote = st.checkbox("Remote uniquement")
    with fc2:
        filter_source = st.multiselect("Sources", ["Remotive (Remote)", "Adzuna", "JSearch"])
    with fc3:
        sort_by = st.selectbox("Trier par", ["Pertinence", "Date (récent)", "Entreprise (A-Z)"])

# ── Lancement de la recherche ──────────────────────────────────────────────────

if search_btn and keywords:
    jobs = aggregate_jobs(
        keywords=keywords,
        location=location,
        country=country,
        include_remote=filter_remote or not location,
        adzuna_id=adzuna_id,
        adzuna_key=adzuna_key,
        rapidapi_key=rapidapi_key,
    )
    st.session_state["jobs"] = jobs
    st.session_state["search_done"] = True
    st.session_state["selected_job"] = None

# ── Affichage des résultats ────────────────────────────────────────────────────

if st.session_state.get("search_done"):
    jobs = st.session_state.get("jobs", [])

    # Filtres
    if filter_remote:
        jobs = [j for j in jobs if "remote" in j["location"].lower() or "remote" in j["contract"].lower()]
    if filter_source:
        jobs = [j for j in jobs if any(s.lower() in j["source"].lower() for s in filter_source)]
    if sort_by == "Date (récent)":
        jobs = sorted(jobs, key=lambda j: j.get("posted", ""), reverse=True)
    elif sort_by == "Entreprise (A-Z)":
        jobs = sorted(jobs, key=lambda j: j.get("company", "").lower())

    st.divider()

    if not jobs:
        st.warning("Aucune offre trouvée. Essayez des mots-clés différents ou ajoutez des clés API pour plus de résultats.")
    else:
        # Statistiques
        sources = {}
        for j in jobs:
            src = j["source"].split(" (")[0]
            sources[src] = sources.get(src, 0) + 1

        st.markdown(f"**{len(jobs)} offres trouvées** — " + " | ".join(f"**{k}** : {v}" for k, v in sources.items()))

        col_list, col_detail = st.columns([1, 1.2], gap="large")

        with col_list:
            st.markdown("#### 📋 Offres disponibles")
            for i, job in enumerate(jobs[:50]):
                remote_badge = '<span class="badge badge-green">🌍 Remote</span>' if "remote" in job["location"].lower() or "remote" in job["contract"].lower() else ""
                source_badge = f'<span class="badge">{job["source"].split("(")[0].strip()}</span>'
                salary_text = f"<br><span class='job-meta'>💰 {job['salary']}</span>" if job.get("salary") and job["salary"] != "Non précisé" else ""
                posted_text = f"<span class='job-meta'> · {job['posted']}</span>" if job.get("posted") else ""

                st.markdown(f"""
<div class="job-card">
  {source_badge}{remote_badge}
  <div class="job-title">{job['title']}</div>
  <div class="job-meta">🏢 {job['company']} &nbsp;·&nbsp; 📍 {job['location']}{posted_text}</div>
  {salary_text}
</div>
""", unsafe_allow_html=True)

                btn_col1, btn_col2 = st.columns([1, 1])
                with btn_col1:
                    if st.button("📄 Voir & Postuler", key=f"select_{i}", use_container_width=True):
                        st.session_state["selected_job"] = job
                        st.session_state["generated_cv"] = ""
                        st.session_state["generated_letter"] = ""
                with btn_col2:
                    if job.get("url"):
                        st.link_button("🔗 Offre originale", job["url"], use_container_width=True)

        with col_detail:
            selected = st.session_state.get("selected_job")
            if not selected:
                st.info("👈 Sélectionnez une offre pour voir les détails et postuler.")
            else:
                st.markdown(f"#### {selected['title']}")
                st.markdown(f"🏢 **{selected['company']}** &nbsp;·&nbsp; 📍 {selected['location']}")
                if selected.get("salary") and selected["salary"] != "Non précisé":
                    st.markdown(f"💰 {selected['salary']}")
                if selected.get("contract"):
                    st.markdown(f"📝 {selected['contract']}")
                if selected.get("url"):
                    st.link_button("🔗 Voir l'offre complète", selected["url"])

                with st.expander("📃 Description du poste", expanded=True):
                    desc = selected.get("description", "Aucune description disponible.")
                    st.markdown(desc[:3000] + ("..." if len(desc) > 3000 else ""))

                st.divider()

                if not cv_content:
                    st.warning("⚠️ Chargez votre CV dans la barre latérale avant de postuler.")
                elif not api_key:
                    st.warning("⚠️ Entrez votre clé API Anthropic dans la barre latérale.")
                else:
                    if st.button("🚀 Générer CV adapté + Lettre de motivation", type="primary", use_container_width=True):
                        tab_cv, tab_letter = st.tabs(["📋 CV Adapté", "✉️ Lettre de motivation"])

                        with tab_cv:
                            box = st.empty()
                            full_cv = ""
                            try:
                                for chunk in stream_adapted_cv(
                                    cv=cv_content,
                                    job_desc=selected.get("description", ""),
                                    job_title=selected["title"],
                                    company=selected["company"],
                                    api_key=api_key,
                                    model=model,
                                ):
                                    full_cv += chunk
                                    box.markdown(full_cv)
                                st.session_state["generated_cv"] = full_cv
                                st.success("✅ CV adapté généré !")
                            except Exception as e:
                                st.error(f"Erreur : {e}")

                        with tab_letter:
                            box2 = st.empty()
                            full_letter = ""
                            try:
                                for chunk in stream_cover_letter(
                                    cv=cv_content,
                                    job_desc=selected.get("description", ""),
                                    job_title=selected["title"],
                                    company=selected["company"],
                                    name=applicant_name,
                                    api_key=api_key,
                                    model=model,
                                ):
                                    full_letter += chunk
                                    box2.markdown(full_letter)
                                st.session_state["generated_letter"] = full_letter
                                st.success("✅ Lettre générée !")
                            except Exception as e:
                                st.error(f"Erreur : {e}")

                # Téléchargements si déjà générés
                gen_cv     = st.session_state.get("generated_cv", "")
                gen_letter = st.session_state.get("generated_letter", "")

                if gen_cv or gen_letter:
                    st.markdown("**💾 Télécharger**")
                    dc1, dc2, dc3, dc4 = st.columns(4)
                    if gen_cv:
                        cv_docx = export_docx(gen_cv)
                        with dc1:
                            if cv_docx:
                                st.download_button("📥 CV .docx", cv_docx, "cv_adapte.docx",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True)
                        with dc2:
                            st.download_button("📥 CV .txt", gen_cv.encode(), "cv_adapte.txt",
                                "text/plain", use_container_width=True)
                    if gen_letter:
                        letter_docx = export_docx(gen_letter)
                        with dc3:
                            if letter_docx:
                                st.download_button("📥 Lettre .docx", letter_docx, "lettre.docx",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True)
                        with dc4:
                            st.download_button("📥 Lettre .txt", gen_letter.encode(), "lettre.txt",
                                "text/plain", use_container_width=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption("AutoCandidature IA — Sources : Remotive (sans clé, remote) · Adzuna (Indeed, Monster, Reed...) · JSearch/RapidAPI (LinkedIn, Glassdoor, ZipRecruiter) · Propulsé par Claude (Anthropic)")
