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

let recognition  = null;
let enEcoute     = false;
let questionFinale = "";

// ── Démarre la reconnaissance ────────────────────────────────
function demarrerMicro() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    document.getElementById('transcription').textContent = "Utilisez Chrome";
    return;
  }
  questionFinale = "";
  recognition = new SR();
  recognition.lang            = 'fr-FR';
  recognition.interimResults  = true;
  recognition.continuous      = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    document.getElementById('transcription').textContent = "🔴 Maintenez et parlez...";
    document.getElementById('reponse-ia').textContent    = "";
  };

  recognition.onresult = (event) => {
    let interimaire = "";
    let finale      = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finale += t;
      } else {
        interimaire += t;
      }
    }
    // Affiche en temps réel ce qui est capté
    const affiche = finale || interimaire;
    if (affiche) {
      document.getElementById('transcription').textContent = '"' + affiche + '"';
      questionFinale = affiche;
    }
  };

  recognition.onerror = (e) => {
    if (e.error === 'no-speech') return; // ignore silence
    document.getElementById('transcription').textContent = "Erreur : " + e.error;
  };

  recognition.onend = () => {
    // Relance si toujours en écoute (Chrome Android coupe parfois)
    if (enEcoute) {
      try { recognition.start(); } catch(e) { }
    }
  };

  recognition.start();
  enEcoute = true;
}

// ── Arrête et envoie à Claude ────────────────────────────────
async function arreterMicro() {
  enEcoute = false;
  if (recognition) recognition.stop();
  document.getElementById('btn-parler').classList.remove('ecoute');
  document.getElementById('btn-parler').textContent = "🎤";

  const question = questionFinale.trim();
  if (question.length === 0) {
    document.getElementById('transcription').textContent = "Rien capté — réessayez";
    return;
  }
  document.getElementById('reponse-ia').textContent = "SENTINELLE réfléchit...";
  await interrogerSentinelle(question);
}

// ── Bouton appui long (talkie-walkie) ────────────────────────
const btn = document.getElementById('btn-parler');

// Tactile (téléphone)
btn.addEventListener('touchstart', (e) => {
  e.preventDefault();
  btn.classList.add('ecoute');
  btn.textContent = "🔴";
  demarrerMicro();
});

btn.addEventListener('touchend', (e) => {
  e.preventDefault();
  arreterMicro();
});

// Souris (PC)
btn.addEventListener('mousedown', () => {
  btn.classList.add('ecoute');
  btn.textContent = "🔴";
  demarrerMicro();
});

btn.addEventListener('mouseup', () => {
  arreterMicro();
});

// Garde l'ancien onclick comme fallback
function basculerEcoute() {}

// ── Appel API /vocal ─────────────────────────────────────────
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

// ── Synthèse vocale française ────────────────────────────────
function lireAVoixHaute(texte) {
  const synth = window.speechSynthesis;
  synth.cancel();
  function parler(voix) {
    const u  = new SpeechSynthesisUtterance(texte);
    u.lang   = 'fr-FR';
    u.rate   = 0.92;
    u.pitch  = 1.0;
    u.volume = 1.0;
    const voixFR = voix.find(v => v.lang === 'fr-FR' && v.localService)
                || voix.find(v => v.lang === 'fr-FR')
                || voix.find(v => v.lang.startsWith('fr'))
                || null;
    if (voixFR) u.voice = voixFR;
    synth.speak(u);
  }
  const v = synth.getVoices();
  if (v.length > 0) {
    parler(v);
  } else {
    synth.onvoiceschanged = () => parler(synth.getVoices());
    setTimeout(() => parler(synth.getVoices()), 500);
  }
}
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
    document.getElementById('transcription').textContent = "Non supporté — utilisez Chrome";
    return;
  }
  recognition = new SR();
  recognition.lang            = 'fr-FR';
  recognition.interimResults  = true;
  recognition.maxAlternatives = 1;
  recognition.continuous      = true;

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
        document.getElementById('reponse-ia').textContent = "SENTINELLE réfléchit...";
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
  function parler(voix) {
    const u  = new SpeechSynthesisUtterance(texte);
    u.lang   = 'fr-FR';
    u.rate   = 0.92;
    u.pitch  = 1.0;
    u.volume = 1.0;
    const voixFR = voix.find(v => v.lang === 'fr-FR' && v.localService)
                || voix.find(v => v.lang === 'fr-FR')
                || voix.find(v => v.lang.startsWith('fr'))
                || null;
    if (voixFR) u.voice = voixFR;
    synth.speak(u);
  }
  const voixDisponibles = synth.getVoices();
  if (voixDisponibles.length > 0) {
    parler(voixDisponibles);
  } else {
    synth.onvoiceschanged = () => parler(synth.getVoices());
    setTimeout(() => parler(synth.getVoices()), 500);
  }
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
