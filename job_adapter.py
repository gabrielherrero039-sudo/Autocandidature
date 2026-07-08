"""
job_adapter.py — Adaptation du CV et génération de lettre de motivation
Utilise Ollama (local, gratuit) ou Groq (API cloud gratuite)
"""

import json
import re
from openai import OpenAI
from typing import Generator


# ─── Prompts système ────────────────────────────────────────────────────────

SYSTEM_PROMPT_CV = """Tu es un expert en recrutement et en rédaction de CV professionnels.
Ton rôle est d'adapter un CV existant pour maximiser les chances du candidat face à une offre d'emploi spécifique.

Règles importantes :
- Ne jamais inventer d'expériences ou de compétences absentes du CV original.
- Réorganiser, reformuler et mettre en valeur les éléments déjà présents.
- Adapter le vocabulaire aux termes de l'offre (mots-clés du secteur, technologies mentionnées).
- Mettre en avant les expériences les plus pertinentes en premier.
- Conserver toutes les informations de contact et les faits objectifs (dates, diplômes, entreprises).
- Rendre le CV concis, professionnel et percutant.
- Utiliser une mise en forme claire avec des sections bien délimitées (### pour les titres).
- Répondre UNIQUEMENT avec le CV adapté, sans commentaires ni explications."""

SYSTEM_PROMPT_LETTRE = """Tu es un expert en recrutement et en rédaction de lettres de motivation.
Ton rôle est de rédiger une lettre de motivation percutante, personnalisée et professionnelle.

Règles importantes :
- La lettre doit être directement liée à l'offre d'emploi fournie.
- Mettre en valeur les compétences du candidat qui correspondent aux besoins de l'entreprise.
- Adopter un ton professionnel mais chaleureux, montrant la motivation réelle du candidat.
- Structure : accroche → présentation → adéquation profil/poste → motivation → conclusion avec appel à l'action.
- Longueur : 3 à 4 paragraphes (environ 300-400 mots).
- Ne pas répéter bêtement le CV, mais raconter une histoire cohérente.
- Personnaliser selon l'entreprise et le secteur si des informations sont disponibles dans l'offre.
- Répondre UNIQUEMENT avec la lettre, sans commentaires ni explications."""


# ─── Clients IA ─────────────────────────────────────────────────────────────

def get_ollama_client(base_url: str = "http://localhost:11434/v1") -> OpenAI:
    """Retourne un client OpenAI pointant vers Ollama local."""
    return OpenAI(base_url=base_url, api_key="ollama")


def get_groq_client(api_key: str) -> OpenAI:
    """Retourne un client OpenAI pointant vers l'API Groq."""
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


def get_client(provider: str, api_key: str = "", ollama_url: str = "http://localhost:11434/v1") -> OpenAI:
    if provider == "ollama":
        return get_ollama_client(ollama_url)
    elif provider == "groq":
        return get_groq_client(api_key)
    else:
        raise ValueError(f"Fournisseur inconnu : {provider}")


# ─── Adaptation du CV (streaming) ────────────────────────────────────────────

def adapt_cv_streamed(
    cv_content: str,
    job_posting: str,
    job_sector: str,
    provider: str,
    model: str,
    api_key: str = "",
    ollama_url: str = "http://localhost:11434/v1",
) -> Generator[str, None, None]:
    """
    Adapte le CV à l'offre d'emploi. Génère le texte en streaming.
    """
    client = get_client(provider, api_key, ollama_url)

    user_message = (
        f"Voici le CV du candidat :\n\n---\n{cv_content}\n---\n\n"
        f"Voici l'offre d'emploi (secteur : {job_sector or 'non specifie'}) :\n\n---\n{job_posting}\n---\n\n"
        "Adapte ce CV pour maximiser les chances du candidat face a cette offre. "
        "Conserve toutes les informations reelles et restructure/reformule pour mettre en valeur "
        "les elements les plus pertinents."
    )

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CV},
            {"role": "user", "content": user_message},
        ],
        max_tokens=4096,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


# ─── Génération de la lettre (streaming) ─────────────────────────────────────

def generate_cover_letter_streamed(
    cv_content: str,
    job_posting: str,
    job_sector: str,
    provider: str,
    model: str,
    api_key: str = "",
    ollama_url: str = "http://localhost:11434/v1",
) -> Generator[str, None, None]:
    """
    Génère une lettre de motivation personnalisée. Texte en streaming.
    """
    client = get_client(provider, api_key, ollama_url)

    user_message = (
        f"Voici le profil du candidat (extrait de son CV) :\n\n---\n{cv_content}\n---\n\n"
        f"Voici l'offre d'emploi (secteur : {job_sector or 'non specifie'}) :\n\n---\n{job_posting}\n---\n\n"
        "Redige une lettre de motivation professionnelle, personnalisee et convaincante pour cette offre."
    )

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_LETTRE},
            {"role": "user", "content": user_message},
        ],
        max_tokens=2048,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


SYSTEM_PROMPT_CANVA_GUIDE = """Tu es un expert en recrutement et optimisation de CV.
Tu vas recevoir un CV et une offre d'emploi.

Ta mission : produire un guide clair et actionnable listant les modifications precises a apporter au CV pour le cibler sur cette offre.

Format de reponse (Markdown) :
- Organise les modifications par section du CV (Accroche, Competences, Experiences, Formation, etc.)
- Pour chaque modification, indique clairement :
  - [AVANT] le texte actuel (ou une description de ce qui est present)
  - [APRES] le nouveau texte suggere
  - Ou : "Ajouter : ..." / "Supprimer : ..." / "Reformuler : ..."
- Sois tres specifique et actionnable — la personne doit pouvoir faire les modifications directement dans Canva
- Mets en gras les mots-cles importants de l'offre a integrer
- Ne modifie pas les informations factuelles (nom, dates, entreprises, diplomes reels)
- Maximum 20 modifications, en ordre de priorite (les plus importantes en premier)

Commence directement par les modifications, sans introduction."""


def generate_canva_guide_streamed(
    cv_content: str,
    job_posting: str,
    job_sector: str,
    provider: str,
    model: str,
    api_key: str = "",
    ollama_url: str = "http://localhost:11434/v1",
) -> Generator[str, None, None]:
    """
    Génère un guide de modifications Canva pour adapter le CV à l'offre.
    """
    client = get_client(provider, api_key, ollama_url)

    user_message = (
        f"Voici mon CV actuel :\n\n---\n{cv_content}\n---\n\n"
        f"Voici l'offre d'emploi (secteur : {job_sector or 'non specifie'}) :\n\n---\n{job_posting}\n---\n\n"
        "Produis le guide des modifications a apporter a mon CV pour maximiser mes chances sur cette offre."
    )

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CANVA_GUIDE},
            {"role": "user", "content": user_message},
        ],
        max_tokens=2048,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


SYSTEM_PROMPT_STRUCTURED = """Tu es un expert en rédaction de CV professionnels.
Tu vas recevoir une liste de paragraphes numérotés extraits d'un CV, ainsi qu'une offre d'emploi.

Ta mission :
- Adapter UNIQUEMENT le contenu des descriptions de poste, competences, resume/accroche et realisations.
- NE PAS modifier : les en-tetes de section, les noms d'entreprises, les dates, les noms de diplomes, les noms d'ecoles, les coordonnees.
- Reformuler les descriptions pour mettre en avant les competences correspondant a l'offre.
- Utiliser les mots-cles de l'offre dans les descriptions quand c'est pertinent.
- Conserver exactement le meme niveau de detail (ne pas allonger ni raccourcir significativement).

Reponds UNIQUEMENT avec un objet JSON valide de la forme :
{"index": "nouveau texte adapte", "index2": "autre texte adapte"}
Ou "index" est le numero du paragraphe entre crochets dans la liste fournie.
N'inclure QUE les paragraphes que tu as modifies. Ne pas inclure les paragraphes inchanges.
Ne pas ajouter de texte avant ou apres le JSON."""


def adapt_cv_structured(
    paragraphs_text: str,
    job_posting: str,
    job_sector: str,
    provider: str,
    model: str,
    api_key: str = "",
    ollama_url: str = "http://localhost:11434/v1",
) -> dict[int, str]:
    """
    Adapte le CV paragraphe par paragraphe en preservant la structure.
    Retourne {index_paragraphe: texte_adapte}.
    """
    client = get_client(provider, api_key, ollama_url)

    user_message = (
        f"Voici les paragraphes adaptables de mon CV (numerotes) :\n\n{paragraphs_text}\n\n"
        f"Voici l'offre d'emploi (secteur : {job_sector or 'non specifie'}) :\n\n---\n{job_posting}\n---\n\n"
        "Adapte uniquement les paragraphes pertinents. Retourne un JSON {\"index\": \"texte adapte\"}."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_STRUCTURED},
            {"role": "user", "content": user_message},
        ],
        max_tokens=4096,
        stream=False,
    )

    raw = response.choices[0].message.content or "{}"

    # Extraire le JSON de la reponse (parfois entouré de ```json ... ```)
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return {}
    try:
        parsed = json.loads(json_match.group())
        return {int(k): v for k, v in parsed.items() if str(k).isdigit()}
    except (json.JSONDecodeError, ValueError):
        return {}


# ─── Vérification de connexion ────────────────────────────────────────────────

def check_ollama(base_url: str = "http://localhost:11434") -> tuple[bool, list[str]]:
    """
    Vérifie si Ollama est en cours d'exécution et retourne la liste des modèles disponibles.
    """
    import requests
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return True, models
        return False, []
    except Exception:
        return False, []


def check_groq(api_key: str) -> tuple[bool, str]:
    """
    Vérifie si la clé Groq est valide.
    """
    try:
        client = get_groq_client(api_key)
        client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=5,
        )
        return True, ""
    except Exception as e:
        err = str(e)
        if "401" in err or "auth" in err.lower():
            return False, "Cle API invalide. Verifiez sur console.groq.com"
        return False, f"Erreur : {err}"


# ─── Modèles recommandés ──────────────────────────────────────────────────────

GROQ_MODELS = [
    "llama-3.3-70b-versatile",   # Meilleur qualite
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",      # Le plus rapide
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

OLLAMA_RECOMMENDED = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "gemma2",
    "qwen2.5",
    "phi3",
]
