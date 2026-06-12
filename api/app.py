# ============================================================
# SENTINELLE-IA — API Flask complète v3
# Routes : /analyser  /dashboard  /vocal  /test-vocal
# ============================================================

from flask import Flask, request, jsonify, render_template_string
import anthropic, requests, os, json
from datetime import datetime

app = Flask(__name__)

ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID")
client         = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

derniere_donnee = {}

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
- Tout va bien → OK"""

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

@app.route("/vocal", methods=["POST"])
def vocal():
    data     = request.get_json()
    question = data.get("question", "")
    capteurs = derniere_donnee if derniere_donnee else data.get("capteurs", {})

    prompt_contexte = f"""Tu es SENTINELLE, l'assistant vocal de sécurité d'un travailleur.
Tu réponds en français naturel parlé, 2 phrases maximum.
Pas de markdown, pas de symboles spéciaux, pas de listes.
Sois direct et rassurant sauf en cas de danger réel.

Données capteurs en temps réel :
- Température ambiante   : {capteurs.get('temp_amb', 'N/A')}°C
- Température corporelle : {capteurs.get('temp_corps', 'N/A')}°C
- Humidité               : {capteurs.get('humidity', 'N/A')}%
- Niveau de gaz          : {capteurs.get('gaz', 'N/A')} (seuil danger : 1500)
- Fréquence cardiaque    : {capteurs.get('bpm', 'N/A')} BPM
- Accélération totale    : {capteurs.get('total_g', 'N/A')}g
- Distance objet proche  : {capteurs.get('distance', 'N/A')} cm
- GPS fixé               : {capteurs.get('gps_fix', False)}"""

    try:
        reponse = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=150,
            system=prompt_contexte,
            messages=[{"role": "user", "content": question}]
        )
        texte = reponse.content[0].text
    except Exception as e:
        texte = "Je rencontre une difficulté technique. Veuillez réessayer."

    return jsonify({"reponse": texte})

@app.route("/test-vocal")
def test_vocal():
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#000;color:#fff;font-family:monospace;padding:20px;}
button{background:#238636;color:#fff;border:none;padding:15px 30px;
font-size:1.2em;border-radius:8px;margin:10px 0;}
#log{background:#111;padding:10px;border-radius:5px;margin-top:10px;
min-height:100px;white-space:pre-wrap;font-size:0.9em;}
</style></head>
<body>
<h2>Test Reconnaissance Vocale</h2>
<button onclick="tester()">Appuyer et parler</button>
<div id="log">En attente...</div>
<script>
function log(msg) {
  document.getElementById('log').textContent += msg + '\\n';
}
function tester() {
  log('Démarrage...');
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { log('ERREUR: SpeechRecognition non disponible !'); return; }
  log('OK: SpeechRecognition disponible');
  const r = new SR();
  r.lang = 'fr-FR';
  r.interimResults = true;
  r.onstart  = () => log('OK: Micro activé — parlez !');
  r.onresult = (e) => {
    const t = e.results[e.results.length-1][0].transcript;
    log('Transcription : ' + t);
  };
  r.onerror  = (e) => log('ERREUR: ' + e.error);
  r.onend    = () => log('Fin écoute');
  r.start();
}
</script>
</body></html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="3">
  <title>SENTINELLE-IA</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Courier New', monospace;
      background: #0d1117; color: #c9d1d9;
      padding: 20px; min-height: 100vh;
    }
    h1 { color: #58a6ff; margin-bottom: 20px; font-size: 1.4em; }
    h2 { color: #8b949e; font-size: 1em; margin-bottom: 12px; }
    .statut {
      padding: 15px 20px; border-radius: 8px;
      margin-bottom: 20px; font-size: 1.1em; font-weight: bold;
    }
    .statut.danger  { background:#2d1b1b; border:2px solid #f85149; color:#f85149; }
    .statut.warning { background:#2d2208; border:2px solid #e3b341; color:#e3b341; }
    .statut.ok      { background:#1b2d1b; border:2px solid #3fb950; color:#3fb950; }
    .grille {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px; margin-bottom: 20px;
    }
    .carte {
      background: #161b22; border: 1px solid #30363d;
      border-radius: 8px; padding: 15px; text-align: center;
    }
    .carte .val { font-size: 1.6em; font-weight: bold; color: #58a6ff; }
    .carte .nom { font-size: 0.8em; color: #8b949e; margin-top: 5px; }
    #vocal-section {
      background: #161b22; border: 1px solid #30363d;
      border-radius: 8px; padding: 20px;
      text-align: center; margin-bottom: 20px;
    }
    #btn-parler {
      background: #238636; color: white; border: none;
      border-radius: 50%; width: 80px; height: 80px;
      font-size: 2em; cursor: pointer; margin: 15px 0;
      transition: background 0.2s;
    }
    #btn-parler.ecoute {
      background: #f85149;
      animation: pulse 1s infinite;
    }
    @keyframes pulse {
      0%   { box-shadow: 0 0 0 0 rgba(248,81,73,0.5); }
      100% { box-shadow: 0 0 0 15px rgba(248,81,73,0); }
    }
    #transcription { color: #8b949e; font-style: italic; margin: 8px 0; min-height: 24px; }
    #reponse-ia    { color: #58a6ff; font-size: 1.05em; margin: 8px 0; min-height: 24px; }
    .timestamp { color: #444; font-size: 0.8em; margin-top: 10px; }
    a { color: #58a6ff; }
  </style>
</head>
<body>
  <h1>🛡️ SENTINELLE-IA — Surveillance temps réel</h1>

  {% if data %}
  <div class="statut {{ niveau_class }}">
    {% if data.analyse %}
      {{ '🚨' if data.analyse.niveau == 'DANGER' else ('⚠️' if data.analyse.niveau == 'ATTENTION' else '✅') }}
      {{ data.analyse.niveau }} — {{ data.analyse.message }}
    {% else %}
      ✅ En attente d'analyse...
    {% endif %}
  </div>
  <div class="grille">
    <div class="carte">
      <div class="val">{{ data.temp_amb }}°C</div>
      <div class="nom">🌡 Temp. ambiante</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.temp_corps }}°C</div>
      <div class="nom">🤒 Temp. corporelle</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.humidity }}%</div>
      <div class="nom">💧 Humidité</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.gaz }}</div>
      <div class="nom">💨 Gaz (brut)</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.bpm }}</div>
      <div class="nom">💓 BPM</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.total_g }}g</div>
      <div class="nom">⚡ Accélération</div>
    </div>
    <div class="carte">
      <div class="val">{{ data.distance }} cm</div>
      <div class="nom">📡 Distance objet</div>
    </div>
    <div class="carte">
      <div class="val">{{ '✓' if data.contact_ok else '✗' }}</div>
      <div class="nom">👆 Contact capteur</div>
    </div>
    <div class="carte">
      {% if data.gps_fix %}
        <div class="val">📍</div>
        <div class="nom">
          <a href="https://maps.google.com/?q={{ data.lat }},{{ data.lng }}"
             target="_blank">Voir sur Maps</a>
        </div>
      {% else %}
        <div class="val">—</div>
        <div class="nom">GPS non fixé</div>
      {% endif %}
    </div>
  </div>
  {% else %}
  <div class="statut ok">En attente des données de l'ESP-32...</div>
  {% endif %}

  <div id="vocal-section">
    <h2>🎙️ Parler à SENTINELLE</h2>
    <p style="color:#8b949e; font-size:0.9em">
      Appuyez sur le bouton et posez votre question à voix haute
    </p>
    <br>
    <button id="btn-parler" onclick="basculerEcoute()">🎤</button>
    <p id="transcription">En attente...</p>
    <p id="reponse-ia"></p>
  </div>

  {% if data %}
  <p class="timestamp">Dernière mise à jour : {{ data.timestamp }}</p>
  {% endif %}

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

function demarrerReconnaissance() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    document.getElementById('transcription').textContent =
      "Non supporté — utilisez Chrome";
    return;
  }

  recognition = new SR();
  recognition.lang            = 'fr-FR';
  recognition.interimResults  = true;
  recognition.maxAlternatives = 1;
  recognition.continuous      = false;

  recognition.onstart = () => {
    document.getElementById('transcription').textContent = "Je vous écoute...";
    document.getElementById('btn-parler').classList.add('ecoute');
  };

  recognition.onresult = async (event) => {
    const dernier  = event.results[event.results.length - 1];
    const question = dernier[0].transcript;

    // Affiche la transcription en temps réel pendant que l'utilisateur parle
    document.getElementById('transcription').textContent = '"' + question + '"';

    // N'envoie à Claude que quand la phrase est finale
    if (dernier.isFinal) {
      document.getElementById('reponse-ia').textContent = "SENTINELLE réfléchit...";
      document.getElementById('btn-parler').classList.remove('ecoute');
      enEcoute = false;
      await interrogerSentinelle(question);
    }
  };

  recognition.onerror = (e) => {
    document.getElementById('transcription').textContent = "Erreur : " + e.error;
    document.getElementById('btn-parler').classList.remove('ecoute');
    enEcoute = false;
  };

  recognition.onend = () => {
    document.getElementById('btn-parler').classList.remove('ecoute');
    enEcoute = false;
  };

  recognition.start();
  enEcoute = true;
}

function basculerEcoute() {
  if (enEcoute && recognition) {
    recognition.stop();
    enEcoute = false;
  } else {
    demarrerReconnaissance();
  }
}

async function interrogerSentinelle(question) {
  try {
    const res = await fetch('/vocal', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({ question: question, capteurs: CAPTEURS })
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
  setTimeout(() => {
    const u  = new SpeechSynthesisUtterance(texte);
    u.lang   = 'fr-FR';
    u.rate   = 0.95;
    u.pitch  = 1.0;
    u.volume = 1.0;
    const voix   = synth.getVoices();
    const voixFR = voix.find(v => v.lang === 'fr-FR')
                || voix.find(v => v.lang.startsWith('fr'));
    if (voixFR) u.voice = voixFR;
    synth.speak(u);
  }, 300);
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

@app.route("/")
def index():
    return """<h2 style='font-family:monospace;color:#58a6ff;padding:20px'>
    🛡️ SENTINELLE-IA API<br><br>
    <a href='/dashboard' style='color:#3fb950'>→ Ouvrir le Dashboard</a>
    </h2>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
