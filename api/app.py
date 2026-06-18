# ============================================================
# SENTINELLE-IA — API Flask complète v4
# Routes : /analyser  /vocal  /vocal-audio  /detecter-wakeword
#          /dernieres-donnees  /dashboard  /test-vocal  /
# ============================================================

from flask import Flask, request, jsonify, render_template_string
import anthropic, requests, os, json, tempfile
from datetime import datetime

app = Flask(__name__)

# ── Clés API ──────────────────────────────────────────────────
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID")
OPENAI_KEY     = os.environ.get("OPENAI_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Client OpenAI optionnel (pour transcription Whisper)
openai_client = None
if OPENAI_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_KEY)
    except ImportError:
        print("OpenAI non installé — transcription audio désactivée")

# ── Mémoire partagée ──────────────────────────────────────────
derniere_donnee = {}

# ── Prompt analyse capteurs ───────────────────────────────────
PROMPT_ANALYSE = """Tu es SENTINELLE-IA, assistant de sécurité industrielle.
Tu reçois des données capteurs d'un travailleur en zone hostile.
Analyse les risques et réponds UNIQUEMENT en JSON valide, sans markdown :
{
  "niveau": "OK" ou "ATTENTION" ou "DANGER",
  "message": "phrase courte pour le dashboard (max 15 mots)",
  "alerte_telegram": true ou false,
  "details": "explication technique en 1 phrase"
}
Seuils critiques :
- gaz > 1500 → DANGER
- total_g > 2.5 → DANGER (chute détectée)
- temp_corps > 38.5 ET temp_amb > 35 → DANGER (coup de chaleur)
- temp_amb > 45 → DANGER (environnement hostile)
- bpm > 120 ou bpm < 40 (si contact_ok=true) → ATTENTION
- Capteur défaillant (valeur nulle ou aberrante) → ATTENTION
- Tout va bien → OK"""

# ── Envoi alerte Telegram ─────────────────────────────────────
def envoyer_telegram(texte):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("Telegram non configuré")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT,
            "text": texte,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        print(f"Erreur Telegram : {e}")

# ── ROUTE 1 — /analyser ───────────────────────────────────────
# Reçoit JSON de l'ESP-32, appelle Claude, renvoie analyse
@app.route("/analyser", methods=["POST"])
def analyser():
    global derniere_donnee
    data = request.get_json()
    derniere_donnee = {**data, "timestamp": datetime.now().strftime("%H:%M:%S")}

    try:
        reponse = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=300,
            system=PROMPT_ANALYSE,
            messages=[{
                "role": "user",
                "content": f"Données capteurs : {json.dumps(data, ensure_ascii=False)}"
            }]
        )
        texte   = reponse.content[0].text
        texte   = texte.replace("```json", "").replace("```", "").strip()
        analyse = json.loads(texte)

    except Exception as e:
        print(f"Erreur Claude : {e}")
        analyse = {
            "niveau": "OK",
            "message": "Analyse temporairement indisponible",
            "alerte_telegram": False,
            "details": str(e)
        }

    derniere_donnee["analyse"] = analyse

    # Alerte Telegram si danger
    if analyse.get("alerte_telegram"):
        emoji  = "🚨" if analyse["niveau"] == "DANGER" else "⚠️"
        lat    = data.get("lat", 0)
        lng    = data.get("lng", 0)
        gps_ok = data.get("gps_fix", False)
        maps   = f"https://maps.google.com/?q={lat},{lng}" if gps_ok else "GPS non fixé"
        msg = (
            f"{emoji} <b>SENTINELLE-IA — {analyse['niveau']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 {analyse['message']}\n\n"
            f"🌡 Temp. ambiante   : {data.get('temp_amb', 'N/A')}°C\n"
            f"🤒 Temp. corporelle : {data.get('temp_corps', 'N/A')}°C\n"
            f"💨 Gaz (brut)       : {data.get('gaz', 'N/A')}\n"
            f"💓 Fréq. cardiaque  : {data.get('bpm', 'N/A')} BPM\n"
            f"⚡ Accélération     : {data.get('total_g', 'N/A')}g\n"
            f"📍 Position         : {maps}\n"
            f"🕐 Heure            : {derniere_donnee['timestamp']}"
        )
        envoyer_telegram(msg)

    return jsonify(analyse)

# ── ROUTE 2 — /vocal ──────────────────────────────────────────
# Reçoit une question texte, répond en langage naturel parlé
@app.route("/vocal", methods=["POST"])
def vocal():
    data                 = request.get_json()
    question             = data.get("question", "")
    langue               = data.get("langue", "fr")
    capteurs_defaillants = data.get("capteurs_defaillants", [])
    capteurs             = derniere_donnee if derniere_donnee else data.get("capteurs", {})

    heure_actuelle = datetime.now().strftime("%H:%M")
    date_actuelle  = datetime.now().strftime("%d/%m/%Y")
    langue_forcee  = "Réponds OBLIGATOIREMENT en français." if langue == "fr" \
                     else "Reply ONLY in English."
    defaillants_str = ", ".join(capteurs_defaillants) if capteurs_defaillants else "aucun"

    prompt_systeme = f"""Tu es SENTINELLE, assistant vocal de sécurité industrielle.

RÈGLE ABSOLUE N°1 : Réponds D'ABORD DIRECTEMENT à la question posée.
RÈGLE ABSOLUE N°2 : Seulement APRÈS avoir répondu à la question, tu peux ajouter UNE information complémentaire si elle est vraiment utile.
RÈGLE ABSOLUE N°3 : Maximum 2 phrases au total.
RÈGLE ABSOLUE N°4 : {langue_forcee}
RÈGLE ABSOLUE N°5 : Pas de markdown, pas de listes, langage naturel parlé uniquement.

Exemples de comportement attendu :
- Question "Quelle heure est-il ?" → "Il est {heure_actuelle}."
- Question "Quelle est ma température corporelle ?" → "Ta température corporelle est de {capteurs.get('temp_corps', 'N/A')} degrés."
- Question "Est-ce qu'il y a du gaz ?" → "Le niveau de gaz est à {capteurs.get('gaz', 'N/A')}, {'en dessous' if isinstance(capteurs.get('gaz'), (int, float)) and capteurs.get('gaz', 0) < 1500 else 'au-dessus'} du seuil de danger."
- Question "Comment je vais ?" → Résumé court de l'état général.
- Question hors capteurs (météo, calcul, etc.) → Réponds normalement.

Informations disponibles :
- Heure actuelle         : {heure_actuelle}
- Date actuelle          : {date_actuelle}
- Capteurs défaillants   : {defaillants_str}
- Température ambiante   : {capteurs.get('temp_amb', 'N/A')}°C
- Température corporelle : {capteurs.get('temp_corps', 'N/A')}°C
- Humidité               : {capteurs.get('humidity', 'N/A')}%
- Niveau de gaz          : {capteurs.get('gaz', 'N/A')} (seuil danger : 1500)
- Fréquence cardiaque    : {capteurs.get('bpm', 'N/A')} BPM
- Accélération totale    : {capteurs.get('total_g', 'N/A')}g
- Distance objet         : {capteurs.get('distance', 'N/A')} cm
- GPS fixé               : {capteurs.get('gps_fix', False)}
- Statut général         : {capteurs.get('analyse', {}).get('niveau', 'N/A')}"""

    try:
        reponse = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=150,
            system=prompt_systeme,
            messages=[{"role": "user", "content": question}]
        )
        texte = reponse.content[0].text
    except Exception as e:
        texte = "Je rencontre une difficulté technique. Veuillez réessayer." \
                if langue == "fr" else "Technical error. Please try again."

    return jsonify({"reponse": texte})

# ── ROUTE 3 — /vocal-audio ────────────────────────────────────
# Reçoit fichier audio, transcrit avec Whisper, répond avec Claude
@app.route("/vocal-audio", methods=["POST"])
def vocal_audio():
    fichier       = request.files.get("audio")
    langue        = request.form.get("langue", "fr")
    capteurs_str  = request.form.get("capteurs", "{}")
    defaillants_str = request.form.get("capteurs_defaillants", "[]")

    try:
        capteurs_data    = json.loads(capteurs_str)
        capteurs_defaillants = json.loads(defaillants_str)
    except:
        capteurs_data    = {}
        capteurs_defaillants = []

    question = ""

    # Transcription audio avec Whisper si disponible
    if fichier and openai_client:
        try:
            with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
                fichier.save(tmp.name)
                tmp_path = tmp.name
            with open(tmp_path, "rb") as f:
                resultat = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="fr" if langue == "fr" else "en"
                )
            os.unlink(tmp_path)
            question = resultat.text.strip()
            print(f"Transcription Whisper : {question}")
        except Exception as e:
            print(f"Erreur Whisper : {e}")
            question = ""

    # Fallback si pas de transcription
    if not question:
        question = "Donne-moi un résumé de mon état de santé actuel." \
                   if langue == "fr" else \
                   "Give me a summary of my current health status."

    # Appel Claude pour la réponse
    heure_actuelle = datetime.now().strftime("%H:%M")
    date_actuelle  = datetime.now().strftime("%d/%m/%Y")
    langue_forcee  = "Réponds OBLIGATOIREMENT en français." if langue == "fr" \
                     else "Reply ONLY in English."
    defaillants_info = ", ".join(capteurs_defaillants) if capteurs_defaillants else "aucun"

    prompt_systeme = f"""Tu es SENTINELLE, assistant vocal de sécurité industrielle.

RÈGLE ABSOLUE N°1 : Réponds D'ABORD DIRECTEMENT à la question posée.
RÈGLE ABSOLUE N°2 : Seulement APRÈS avoir répondu, tu peux ajouter UNE information complémentaire utile.
RÈGLE ABSOLUE N°3 : Maximum 2 phrases au total.
RÈGLE ABSOLUE N°4 : {langue_forcee}
RÈGLE ABSOLUE N°5 : Pas de markdown, langage naturel parlé uniquement.

Informations disponibles :
- Heure : {heure_actuelle} | Date : {date_actuelle}
- Capteurs défaillants : {defaillants_info}
- Température ambiante   : {capteurs_data.get('temp_amb', 'N/A')}°C
- Température corporelle : {capteurs_data.get('temp_corps', 'N/A')}°C
- Humidité               : {capteurs_data.get('humidity', 'N/A')}%
- Gaz                    : {capteurs_data.get('gaz', 'N/A')} (seuil : 1500)
- BPM                    : {capteurs_data.get('bpm', 'N/A')}
- Accélération           : {capteurs_data.get('total_g', 'N/A')}g
- Distance               : {capteurs_data.get('distance', 'N/A')} cm
- Statut général         : {capteurs_data.get('analyse', {}).get('niveau', 'N/A')}"""

    try:
        rep = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=150,
            system=prompt_systeme,
            messages=[{"role": "user", "content": question}]
        )
        reponse = rep.content[0].text
    except Exception as e:
        reponse = "Erreur d'analyse." if langue == "fr" else "Analysis error."

    return jsonify({"question": question, "reponse": reponse})

# ── ROUTE 4 — /detecter-wakeword ─────────────────────────────
# Détecte si le mot "Sentinelle" a été prononcé dans l'audio
@app.route("/detecter-wakeword", methods=["POST"])
def detecter_wakeword():
    fichier = request.files.get("audio")
    langue  = request.form.get("langue", "fr")

    if not fichier:
        return jsonify({"detected": False})

    # Si Whisper disponible → transcription réelle
    if openai_client:
        try:
            with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
                fichier.save(tmp.name)
                tmp_path = tmp.name
            with open(tmp_path, "rb") as f:
                resultat = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="fr" if langue == "fr" else "en"
                )
            os.unlink(tmp_path)
            texte = resultat.text.lower().strip()
            print(f"Wake word check : '{texte}'")

            wake_words = ["sentinelle", "sentinel", "centinelle", "santinelle",
                          "sentinal", "sentinell"]
            detected = any(w in texte for w in wake_words)
            return jsonify({"detected": detected, "texte": texte})

        except Exception as e:
            print(f"Erreur wake word : {e}")
            return jsonify({"detected": False})

    # Sans Whisper → wake word désactivé
    return jsonify({"detected": False, "raison": "Whisper non configuré"})

# ── ROUTE 5 — /dernieres-donnees ──────────────────────────────
# Renvoie le dernier JSON reçu de l'ESP-32
@app.route("/dernieres-donnees", methods=["GET"])
def dernieres_donnees():
    return jsonify(derniere_donnee if derniere_donnee else {})

# ── ROUTE 6 — /test-vocal ─────────────────────────────────────
# Page de diagnostic vocal dans le navigateur
@app.route("/test-vocal")
def test_vocal():
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#000;color:#fff;font-family:monospace;padding:20px;}
button{background:#238636;color:#fff;border:none;padding:15px 30px;
font-size:1.2em;border-radius:8px;margin:10px 0;cursor:pointer;}
#log{background:#111;padding:10px;border-radius:5px;margin-top:10px;
min-height:100px;white-space:pre-wrap;font-size:0.9em;}
</style></head>
<body>
<h2>🎤 Test Reconnaissance Vocale</h2>
<button onclick="tester()">Appuyer et parler</button>
<div id="log">En attente...</div>
<script>
function log(msg){document.getElementById('log').textContent+=msg+'\\n';}
function tester(){
  log('Démarrage...');
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){log('ERREUR: non disponible');return;}
  const r=new SR();
  r.lang='fr-FR';
  r.interimResults=true;
  r.continuous=true;
  r.onstart=()=>log('✅ Micro activé — parlez !');
  r.onresult=(e)=>{
    const t=e.results[e.results.length-1][0].transcript;
    log('📝 : '+t);
  };
  r.onerror=(e)=>log('❌ Erreur: '+e.error);
  r.onend=()=>log('⏹️ Fin écoute');
  r.start();
}
</script>
</body></html>"""

# ── ROUTE 7 — /dashboard ──────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="3">
  <title>SENTINELLE-IA</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Courier New',monospace;background:#0d1117;color:#c9d1d9;padding:20px;min-height:100vh;}
    h1{color:#58a6ff;margin-bottom:20px;font-size:1.4em;}
    .statut{padding:15px 20px;border-radius:8px;margin-bottom:20px;font-size:1.1em;font-weight:bold;}
    .statut.danger{background:#2d1b1b;border:2px solid #f85149;color:#f85149;}
    .statut.warning{background:#2d2208;border:2px solid #e3b341;color:#e3b341;}
    .statut.ok{background:#1b2d1b;border:2px solid #3fb950;color:#3fb950;}
    .grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;}
    .carte{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px;text-align:center;}
    .carte .val{font-size:1.6em;font-weight:bold;color:#58a6ff;}
    .carte .nom{font-size:0.8em;color:#8b949e;margin-top:5px;}
    .carte.danger{border-color:#f85149;background:#2d1b1b;}
    .carte.danger .val{color:#f85149;}
    #vocal-section{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;text-align:center;margin-bottom:20px;}
    #btn-parler{background:#238636;color:white;border:none;border-radius:50%;width:80px;height:80px;font-size:2em;cursor:pointer;margin:15px 0;transition:background 0.2s;}
    #btn-parler.ecoute{background:#f85149;animation:pulse 1s infinite;}
    @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(248,81,73,0.5);}100%{box-shadow:0 0 0 15px rgba(248,81,73,0);}}
    #transcription{color:#8b949e;font-style:italic;margin:8px 0;min-height:24px;}
    #reponse-ia{color:#58a6ff;font-size:1.05em;margin:8px 0;min-height:24px;}
    .timestamp{color:#444;font-size:0.8em;margin-top:10px;}
    a{color:#58a6ff;}
  </style>
</head>
<body>
  <h1>🛡️ SENTINELLE-IA — Surveillance temps réel</h1>
  {% if data %}
  <div class="statut {{ niveau_class }}">
    {% if data.analyse %}
      {{ '🚨' if data.analyse.niveau == 'DANGER' else ('⚠️' if data.analyse.niveau == 'ATTENTION' else '✅') }}
      {{ data.analyse.niveau }} — {{ data.analyse.message }}
    {% else %}✅ En attente d'analyse...{% endif %}
  </div>
  <div class="grille">
    <div class="carte {{ 'danger' if data.temp_amb > 45 else '' }}">
      <div class="val">{{ data.temp_amb }}°C</div><div class="nom">🌡 Temp. ambiante</div>
    </div>
    <div class="carte {{ 'danger' if data.temp_corps > 38.5 else '' }}">
      <div class="val">{{ data.temp_corps }}°C</div><div class="nom">🤒 Temp. corporelle</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.humidity }}%</div><div class="nom">💧 Humidité</div>
    </div>
    <div class="carte {{ 'danger' if data.gaz > 1500 else '' }}">
      <div class="val">{{ data.gaz }}</div><div class="nom">💨 Gaz (brut)</div>
    </div>
    <div class="carte {{ 'danger' if data.bpm > 120 or data.bpm < 40 else '' }}">
      <div class="val">{{ data.bpm }}</div><div class="nom">💓 BPM</div>
    </div>
    <div class="carte {{ 'danger' if data.total_g > 2.5 else '' }}">
      <div class="val">{{ data.total_g }}g</div><div class="nom">⚡ Accélération</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.distance }} cm</div><div class="nom">📡 Distance</div>
    </div>
    <div class="carte">
      {% if data.gps_fix %}
        <div class="val">📍</div>
        <div class="nom"><a href="https://maps.google.com/?q={{ data.lat }},{{ data.lng }}" target="_blank">Voir sur Maps</a></div>
      {% else %}<div class="val">—</div><div class="nom">GPS non fixé</div>{% endif %}
    </div>
  </div>
  {% else %}
  <div class="statut ok">En attente des données de l'ESP-32...</div>
  {% endif %}

  <div id="vocal-section">
    <h2 style="color:#c9d1d9;margin-bottom:8px;">🎙️ Parler à SENTINELLE</h2>
    <p style="color:#8b949e;font-size:0.9em">Appuyez sur le bouton et posez votre question</p>
    <button id="btn-parler" onclick="basculerEcoute()">🎤</button>
    <p id="transcription">En attente...</p>
    <p id="reponse-ia"></p>
  </div>

  {% if data %}<p class="timestamp">Mise à jour toutes les 3s • {{ data.timestamp }}</p>{% endif %}

<script>
const CAPTEURS = {
  temp_amb:   {{ data.temp_amb   if data else 0 }},
  temp_corps: {{ data.temp_corps if data else 0 }},
  humidity:   {{ data.humidity   if data else 0 }},
  gaz:        {{ data.gaz        if data else 0 }},
  bpm:        {{ data.bpm        if data else 0 }},
  total_g:    {{ data.total_g    if data else 0 }},
  distance:   {{ data.distance   if data else 0 }},
  gps_fix:    {{ 'true' if data and data.gps_fix else 'false' }}
};

let recognition = null;
let enEcoute    = false;
let silenceTimer = null;

function demarrerReconnaissance() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    document.getElementById('transcription').textContent = "Utilisez Chrome";
    return;
  }
  recognition = new SR();
  recognition.lang            = 'fr-FR';
  recognition.interimResults  = true;
  recognition.continuous      = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    document.getElementById('transcription').textContent = "Je vous écoute...";
    document.getElementById('btn-parler').classList.add('ecoute');
    document.getElementById('reponse-ia').textContent = "";
  };

  recognition.onresult = async (event) => {
    if (silenceTimer) clearTimeout(silenceTimer);
    const dernier  = event.results[event.results.length - 1];
    const question = dernier[0].transcript;
    document.getElementById('transcription').textContent = '"' + question + '"';
    silenceTimer = setTimeout(async () => {
      if (question.trim().length > 0) {
        document.getElementById('reponse-ia').textContent = "⏳ SENTINELLE réfléchit...";
        document.getElementById('btn-parler').classList.remove('ecoute');
        enEcoute = false;
        recognition.stop();
        await interrogerSentinelle(question);
      }
    }, 1500);
  };

  recognition.onerror = (e) => {
    if (e.error === 'no-speech') {
      recognition.stop();
      if (enEcoute) recognition.start();
      return;
    }
    document.getElementById('transcription').textContent = "Erreur : " + e.error;
    document.getElementById('btn-parler').classList.remove('ecoute');
    enEcoute = false;
  };

  recognition.onend = () => {
    if (enEcoute) {
      try { recognition.start(); } catch(e) {}
    } else {
      document.getElementById('btn-parler').classList.remove('ecoute');
    }
  };

  recognition.start();
  enEcoute = true;
}

function basculerEcoute() {
  if (enEcoute) {
    enEcoute = false;
    if (silenceTimer) clearTimeout(silenceTimer);
    if (recognition) recognition.stop();
    document.getElementById('transcription').textContent = "En attente...";
    document.getElementById('btn-parler').classList.remove('ecoute');
  } else {
    demarrerReconnaissance();
  }
}

async function interrogerSentinelle(question) {
  try {
    const res = await fetch('/vocal', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question, capteurs: CAPTEURS, langue: 'fr' })
    });
    const json    = await res.json();
    const reponse = json.reponse;
    document.getElementById('reponse-ia').textContent = reponse;
    lireAVoixHaute(reponse);
  } catch (err) {
    document.getElementById('reponse-ia').textContent = "Erreur de connexion.";
  }
}

function lireAVoixHaute(texte) {
  const synth = window.speechSynthesis;
  synth.cancel();
  function parler(voix) {
    const u = new SpeechSynthesisUtterance(texte);
    u.lang = 'fr-FR'; u.rate = 0.92; u.pitch = 1.0; u.volume = 1.0;
    const voixFR = voix.find(v => v.lang === 'fr-FR' && v.localService)
                || voix.find(v => v.lang === 'fr-FR')
                || voix.find(v => v.lang.startsWith('fr')) || null;
    if (voixFR) u.voice = voixFR;
    synth.speak(u);
  }
  const v = synth.getVoices();
  if (v.length > 0) parler(v);
  else { synth.onvoiceschanged = () => parler(synth.getVoices()); setTimeout(() => parler(synth.getVoices()), 500); }
}
</script>
</body>
</html>"""

@app.route("/dashboard")
def dashboard():
    niveau_class = "ok"
    if derniere_donnee.get("analyse"):
        n = derniere_donnee["analyse"].get("niveau", "OK")
        niveau_class = {"DANGER":"danger","ATTENTION":"warning","OK":"ok"}.get(n,"ok")
    return render_template_string(
        DASHBOARD_HTML,
        data=derniere_donnee if derniere_donnee else None,
        niveau_class=niveau_class
    )

# ── ROUTE 8 — / ───────────────────────────────────────────────
@app.route("/")
def index():
    return """<h2 style='font-family:monospace;color:#58a6ff;padding:20px'>
    🛡️ SENTINELLE-IA API v4<br><br>
    <a href='/dashboard' style='color:#3fb950'>→ Dashboard temps réel</a><br>
    <a href='/test-vocal' style='color:#e3b341'>→ Test vocal</a><br>
    <a href='/dernieres-donnees' style='color:#8b949e'>→ Dernières données JSON</a>
    </h2>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
