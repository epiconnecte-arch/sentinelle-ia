import { useState, useEffect, useRef } from "react";
import {
  View, Text, TouchableOpacity, ScrollView,
  StyleSheet, Vibration, Switch, StatusBar, TextInput
} from "react-native";
import * as Speech from "expo-speech";
import { Audio } from "expo-av";

// ── Configuration ─────────────────────────────────────────────
const API_URL = "https://insightful-passion-production-76aa.up.railway.app";
const INTERVALLE_CAPTEURS  = 3000;
const DUREE_ENREGISTREMENT = 5000;

// ── Thèmes ────────────────────────────────────────────────────
const THEMES = {
  nuit: {
    fond: "#0d1117", fondCarte: "#161b22", fondReponse: "#0d1117",
    bordure: "#30363d", texte: "#c9d1d9", texteFaible: "#8b949e",
    accent: "#58a6ff", statusBar: "light-content",
    iconeTheme: "☀️", labelTheme: "Jour",
  },
  jour: {
    fond: "#f0f2f5", fondCarte: "#ffffff", fondReponse: "#f8f9fa",
    bordure: "#d0d7de", texte: "#1c2128", texteFaible: "#57606a",
    accent: "#0969da", statusBar: "dark-content",
    iconeTheme: "🌙", labelTheme: "Nuit",
  },
};

// ── Textes bilingues ──────────────────────────────────────────
const T = {
  fr: {
    titre: "SENTINELLE-IA", sousTitre: "Surveillance industrielle intelligente",
    connexion: "⏳ Connexion...", espEsp: "⏳ En attente ESP-32...",
    surveillance: "✅ Surveillance active", danger: "🚨 DANGER DÉTECTÉ",
    attention: "⚠️ ATTENTION REQUISE", erreur: "⚠️ Erreur connexion",
    capteurDef: "⚠️ Capteur(s) défaillant(s)",
    wakeWord: "👂 Dites 'Sentinelle' ou appuyez 🎤",
    ecoute: "🔴 Enregistrement en cours...",
    analyse: "⏳ Analyse...", reflechit: "⏳ SENTINELLE réfléchit...",
    rien: "Rien capté — réessayez", erreurCo: "Erreur de connexion.",
    vous: "Vous", sentinelle: "SENTINELLE :",
    maj: "Mise à jour toutes les 3s",
    titreVocal: "🎙️ Parler à SENTINELLE",
    capteurs: "📡 Données capteurs",
    parler: "Appuyer pour parler",
    arreter: "Appuyer pour envoyer",
    modeTexte: "⌨️ Écrire une question",
    envoyer: "Envoyer",
    ouEcrire: "Écrivez votre question...",
  },
  en: {
    titre: "SENTINEL-AI", sousTitre: "Industrial safety monitoring",
    connexion: "⏳ Connecting...", espEsp: "⏳ Waiting for ESP-32...",
    surveillance: "✅ Active monitoring", danger: "🚨 DANGER DETECTED",
    attention: "⚠️ ATTENTION REQUIRED", erreur: "⚠️ Connection error",
    capteurDef: "⚠️ Sensor(s) failing",
    wakeWord: "👂 Say 'Sentinel' or press 🎤",
    ecoute: "🔴 Recording...",
    analyse: "⏳ Analyzing...", reflechit: "⏳ SENTINEL is thinking...",
    rien: "Nothing captured — try again", erreurCo: "Connection error.",
    vous: "You", sentinelle: "SENTINEL:",
    maj: "Updated every 3s",
    titreVocal: "🎙️ Talk to SENTINEL",
    capteurs: "📡 Sensor data",
    parler: "Press to speak",
    arreter: "Press to send",
    modeTexte: "⌨️ Type a question",
    envoyer: "Send",
    ouEcrire: "Type your question...",
  },
};

export default function App() {
  const [theme, setTheme]               = useState("nuit");
  const [langue, setLangue]             = useState("fr");
  const [statut, setStatut]             = useState("⏳ Connexion...");
  const [couleurStatut, setCouleurStatut] = useState("#8b949e");
  const [capteurs, setCapteurs]         = useState(null);
  const [capteursDefaillants, setCapteursDefaillants] = useState([]);
  const [transcription, setTranscription] = useState("");
  const [reponse, setReponse]           = useState("");
  const [modeEcoute, setModeEcoute]     = useState("veille");
  const [dernierNiveau, setDernierNiveau] = useState("OK");
  const [modeTexte, setModeTexte]       = useState(false);
  const [questionTexte, setQuestionTexte] = useState("");
  const [wakeWordEcoute, setWakeWordEcoute] = useState(false);

  const intervalCapteursRef = useRef(null);
  const intervalWakeWordRef = useRef(null);
  const derniereAlerteRef   = useRef(0);
  const langueRef           = useRef("fr");
  const recordingRef        = useRef(null);
  const enregistrementRef   = useRef(false);
  const timerEnreg          = useRef(null);
  const wakeCheckRef        = useRef(false);

  const th = THEMES[theme];
  const t  = T[langue];

  useEffect(() => { langueRef.current = langue; }, [langue]);

  useEffect(() => {
    configurerAudio();
    demarrerSurveillance();
    demarrerEcouteWakeWord();
    return () => {
      if (intervalCapteursRef.current) clearInterval(intervalCapteursRef.current);
      if (intervalWakeWordRef.current) clearInterval(intervalWakeWordRef.current);
      if (timerEnreg.current) clearTimeout(timerEnreg.current);
    };
  }, []);

  // ── Audio ─────────────────────────────────────────────────────
  async function configurerAudio() {
    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
    } catch (e) {}
  }

  // ── Détection capteurs défaillants ────────────────────────────
  function detecterDefaillants(data) {
    const def = [];
    if (!data.temp_amb || data.temp_amb === 0) def.push("DHT22");
    if (!data.temp_corps || data.temp_corps < 10) def.push("DS18B20");
    if (data.gaz === null || data.gaz === undefined) def.push("MQ-2");
    if (!data.total_g && data.total_g !== 0) def.push("MPU6050");
    if (!data.distance) def.push("HC-SR04");
    return def;
  }

  // ── Surveillance capteurs toutes les 3s ───────────────────────
  function demarrerSurveillance() {
    verifierCapteurs();
    intervalCapteursRef.current = setInterval(verifierCapteurs, INTERVALLE_CAPTEURS);
  }

  async function verifierCapteurs() {
    const lng = langueRef.current;
    const txt = T[lng];
    try {
      const res = await fetch(`${API_URL}/dernieres-donnees`, {
        signal: AbortSignal.timeout(4000)
      });
      if (!res.ok) { setStatut(txt.erreur); setCouleurStatut("#e3b341"); return; }
      const data = await res.json();
      if (!data || Object.keys(data).length === 0) {
        setStatut(txt.espEsp); setCouleurStatut("#8b949e"); return;
      }

      setCapteurs(data);
      const def = detecterDefaillants(data);
      setCapteursDefaillants(def);

      const niveau = data.analyse?.niveau || "OK";
      if (niveau === "DANGER") {
        setStatut(txt.danger); setCouleurStatut("#f85149");
        Vibration.vibrate([500, 200, 500, 200, 500]);
      } else if (niveau === "ATTENTION") {
        setStatut(txt.attention); setCouleurStatut("#e3b341");
        Vibration.vibrate(300);
      } else if (def.length > 0) {
        setStatut(`${txt.capteurDef} : ${def.join(", ")}`);
        setCouleurStatut("#e3b341");
      } else {
        setStatut(txt.surveillance); setCouleurStatut("#3fb950");
      }

      const maintenant = Date.now();
      if (
        (niveau === "DANGER" || niveau === "ATTENTION") &&
        niveau !== dernierNiveau &&
        maintenant - derniereAlerteRef.current > 30000
      ) {
        derniereAlerteRef.current = maintenant;
        setDernierNiveau(niveau);
        await alerteVocaleAuto(data, lng);
      } else if (niveau === "OK") {
        setDernierNiveau("OK");
      }
    } catch (e) {
      setStatut(T[langueRef.current].erreur);
      setCouleurStatut("#e3b341");
    }
  }

  // ── Alerte vocale automatique ─────────────────────────────────
  async function alerteVocaleAuto(data, lng) {
    const question = lng === "fr"
      ? `ALERTE ${data.analyse?.niveau} : ${data.analyse?.message}. Donne une instruction d'urgence courte en français.`
      : `ALERT ${data.analyse?.niveau}: ${data.analyse?.message}. Give a short emergency instruction in English.`;
    await envoyerQuestion(question, lng);
  }

  // ── Wake word — écoute passive toutes les 3s ──────────────────
  function demarrerEcouteWakeWord() {
    setWakeWordEcoute(true);
    intervalWakeWordRef.current = setInterval(async () => {
      if (enregistrementRef.current || wakeCheckRef.current) return;
      await verifierWakeWord();
    }, 3000);
  }

  async function verifierWakeWord() {
    wakeCheckRef.current = true;
    try {
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      await new Promise(r => setTimeout(r, 2500));
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();

      const formData = new FormData();
      formData.append("audio", { uri, type: "audio/m4a", name: "wake.m4a" });
      formData.append("langue", langueRef.current);

      const res = await fetch(`${API_URL}/detecter-wakeword`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(5000),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.detected && !enregistrementRef.current) {
          await activerEnregistrement();
        }
      }
    } catch (e) {}
    wakeCheckRef.current = false;
  }

  // ── Activation enregistrement ─────────────────────────────────
  async function activerEnregistrement() {
    if (enregistrementRef.current) return;
    enregistrementRef.current = true;
    const lng = langueRef.current;
    setModeEcoute("enregistrement");
    setTranscription(T[lng].ecoute);
    setReponse("");

    Speech.speak(lng === "fr" ? "Oui ?" : "Yes?", {
      language: lng === "fr" ? "fr-FR" : "en-US",
      rate: 1.3,
    });

    try {
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      recordingRef.current = recording;
      timerEnreg.current = setTimeout(traiterEnregistrement, DUREE_ENREGISTREMENT);
    } catch (e) {
      enregistrementRef.current = false;
      setModeEcoute("veille");
    }
  }

  // ── Bouton micro ──────────────────────────────────────────────
  function gererBoutonMicro() {
    if (modeEcoute === "traitement") return;
    if (modeEcoute === "enregistrement") {
      if (timerEnreg.current) clearTimeout(timerEnreg.current);
      traiterEnregistrement();
    } else {
      activerEnregistrement();
    }
  }

  // ── Traitement enregistrement ─────────────────────────────────
  async function traiterEnregistrement() {
    if (!recordingRef.current) return;
    const lng = langueRef.current;

    try {
      setModeEcoute("traitement");
      setTranscription(T[lng].analyse);

      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      recordingRef.current = null;
      enregistrementRef.current = false;

      // Envoie à /vocal-audio
      const formData = new FormData();
      formData.append("audio", { uri, type: "audio/m4a", name: "question.m4a" });
      formData.append("langue", lng);
      formData.append("capteurs", JSON.stringify(capteurs || {}));
      formData.append("capteurs_defaillants", JSON.stringify(capteursDefaillants));

      const res = await fetch(`${API_URL}/vocal-audio`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(15000),
      });

      if (res.ok) {
        const data = await res.json();
        // Sans Whisper — affiche indication audio reçu
        setTranscription(`${T[lng].vous} : 🎤 (audio reçu)`);
        const texteReponse = data.reponse || T[lng].erreurCo;
        setReponse(texteReponse);
        lireReponse(texteReponse, lng);
      } else {
        setTranscription(T[lng].rien);
      }
    } catch (e) {
      setTranscription(T[lng].erreurCo);
      enregistrementRef.current = false;
    }
    setModeEcoute("veille");
  }

  // ── Question texte ────────────────────────────────────────────
  async function envoyerQuestionTexte() {
    if (!questionTexte.trim()) return;
    const lng = langue;
    const q   = questionTexte.trim();
    setTranscription(`${T[lng].vous} : "${q}"`);
    setQuestionTexte("");
    setModeEcoute("traitement");
    await envoyerQuestion(q, lng);
    setModeEcoute("veille");
  }

  // ── Envoi question à Claude ───────────────────────────────────
  async function envoyerQuestion(question, lng) {
    const txt = T[lng];
    try {
      setReponse(txt.reflechit);
      const res = await fetch(`${API_URL}/vocal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          capteurs: capteurs || {},
          langue: lng,
          capteurs_defaillants: capteursDefaillants,
        }),
        signal: AbortSignal.timeout(10000),
      });
      const data  = await res.json();
      const texte = data.reponse || txt.erreurCo;
      setReponse(texte);
      lireReponse(texte, lng);
    } catch (e) {
      setReponse(T[lng].erreurCo);
    }
    setModeEcoute("veille");
  }

  // ── Synthèse vocale ───────────────────────────────────────────
  function lireReponse(texte, lng) {
    Speech.stop();
    const opts = lng === "fr"
      ? ["fr-FR", "fr-fr", "fr"]
      : ["en-US", "en-us", "en"];
    const parler = (i) => {
      if (i >= opts.length) return;
      Speech.speak(texte, {
        language: opts[i], pitch: 1.0, rate: 0.9,
        onError: () => parler(i + 1),
      });
    };
    parler(0);
  }

  // ── Helpers bouton ────────────────────────────────────────────
  const couleurBouton = () => {
    if (modeEcoute === "enregistrement") return "#f85149";
    if (modeEcoute === "traitement") return "#e3b341";
    return "#238636";
  };
  const iconeBouton = () => {
    if (modeEcoute === "enregistrement") return "⏹️";
    if (modeEcoute === "traitement") return "⏳";
    return "🎤";
  };
  const texteBouton = () => {
    if (modeEcoute === "enregistrement") return t.arreter;
    if (modeEcoute === "traitement") return t.analyse;
    return t.parler;
  };

  // ── Rendu ─────────────────────────────────────────────────────
  return (
    <View style={{ flex: 1, backgroundColor: th.fond }}>
      <StatusBar barStyle={th.statusBar} backgroundColor={th.fond} />
      <ScrollView style={{ flex: 1 }}
        contentContainerStyle={[styles.content, { backgroundColor: th.fond }]}>

        {/* En-tête */}
        <View style={styles.entete}>
          <View>
            <Text style={[styles.titre, { color: th.accent }]}>🛡️ {t.titre}</Text>
            <Text style={[styles.sousTitre, { color: th.texteFaible }]}>{t.sousTitre}</Text>
          </View>
          <View style={styles.controles}>
            <View style={styles.switchGroupe}>
              <Text style={[styles.switchLabel, langue === "fr" && { color: th.accent }]}>FR</Text>
              <Switch
                value={langue === "en"}
                onValueChange={(v) => setLangue(v ? "en" : "fr")}
                trackColor={{ false: "#238636", true: "#1f6feb" }}
                thumbColor="#fff"
                style={styles.switchPetit}
              />
              <Text style={[styles.switchLabel, langue === "en" && { color: th.accent }]}>EN</Text>
            </View>
            <TouchableOpacity
              style={[styles.boutonTheme, { backgroundColor: th.fondCarte, borderColor: th.bordure }]}
              onPress={() => setTheme(theme === "nuit" ? "jour" : "nuit")}
            >
              <Text>{th.iconeTheme}</Text>
              <Text style={[styles.labelTheme, { color: th.texteFaible }]}>{th.labelTheme}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Statut */}
        <View style={[styles.carteStatut, { backgroundColor: th.fondCarte, borderColor: couleurStatut }]}>
          <Text style={[styles.texteStatut, { color: couleurStatut }]}>{statut}</Text>
          {capteurs?.analyse?.message && (
            <Text style={[styles.messageAnalyse, { color: th.texte }]}>
              {capteurs.analyse.message}
            </Text>
          )}
        </View>

        {/* Capteurs */}
        <Text style={[styles.titreSectionPlat, { color: th.texteFaible }]}>{t.capteurs}</Text>
        <View style={styles.grille}>
          <CarteCapteur th={th} label="🌡 Temp. amb."
            valeur={capteurs ? `${capteurs.temp_amb}°C` : "--"}
            danger={capteurs?.temp_amb > 45}
            defaillant={capteursDefaillants.includes("DHT22")} />
          <CarteCapteur th={th} label="🤒 Temp. corps"
            valeur={capteurs ? `${capteurs.temp_corps}°C` : "--"}
            danger={capteurs?.temp_corps > 38.5}
            defaillant={capteursDefaillants.includes("DS18B20")} />
          <CarteCapteur th={th} label="💧 Humidité"
            valeur={capteurs ? `${capteurs.humidity}%` : "--"}
            danger={false} defaillant={false} />
          <CarteCapteur th={th} label="💨 Gaz"
            valeur={capteurs ? `${capteurs.gaz}` : "--"}
            danger={capteurs?.gaz > 1500}
            defaillant={capteursDefaillants.includes("MQ-2")} />
          <CarteCapteur th={th} label="💓 BPM"
            valeur={capteurs ? `${capteurs.bpm}` : "--"}
            danger={capteurs?.bpm > 120 || capteurs?.bpm < 40}
            defaillant={capteursDefaillants.includes("MAX30102")} />
          <CarteCapteur th={th} label="⚡ Accél."
            valeur={capteurs ? `${capteurs.total_g}g` : "--"}
            danger={capteurs?.total_g > 2.5}
            defaillant={capteursDefaillants.includes("MPU6050")} />
          <CarteCapteur th={th} label="📡 Distance"
            valeur={capteurs ? `${capteurs.distance} cm` : "--"}
            danger={false}
            defaillant={capteursDefaillants.includes("HC-SR04")} />
          <CarteCapteur th={th} label="📍 GPS"
            valeur={capteurs ? (capteurs.gps_fix ? "✓ Fixé" : "Non fixé") : "--"}
            danger={false} defaillant={false} />
        </View>

        {/* Zone vocale */}
        <View style={[styles.carteVocale, { backgroundColor: th.fondCarte, borderColor: th.bordure }]}>
          <Text style={[styles.titreSection, { color: th.texte }]}>{t.titreVocal}</Text>

          {/* Indicateur état */}
          <View style={[styles.indicateurEtat, { borderColor: couleurBouton() }]}>
            <Text style={[styles.texteEtat, { color: couleurBouton() }]}>
              {modeEcoute === "veille" ? t.wakeWord :
               modeEcoute === "enregistrement" ? t.ecoute :
               t.analyse}
            </Text>
          </View>

          {/* Bouton micro */}
          <TouchableOpacity
            style={[styles.boutonMicro, { backgroundColor: couleurBouton() }]}
            onPress={gererBoutonMicro}
            disabled={modeEcoute === "traitement"}
            activeOpacity={0.75}
          >
            <Text style={styles.iconeMicro}>{iconeBouton()}</Text>
            <Text style={styles.texteBouton}>{texteBouton()}</Text>
          </TouchableOpacity>

          {/* Bouton mode texte */}
          <TouchableOpacity
            style={[styles.boutonModeTexte, { borderColor: th.bordure }]}
            onPress={() => setModeTexte(!modeTexte)}
          >
            <Text style={[styles.texteModeTexte, { color: th.texteFaible }]}>
              {modeTexte ? "🎤 Mode vocal" : t.modeTexte}
            </Text>
          </TouchableOpacity>

          {/* Champ texte */}
          {modeTexte && (
            <View style={styles.zoneTexte}>
              <TextInput
                style={[styles.champTexte, {
                  backgroundColor: th.fondReponse,
                  borderColor: th.bordure,
                  color: th.texte,
                }]}
                placeholder={t.ouEcrire}
                placeholderTextColor={th.texteFaible}
                value={questionTexte}
                onChangeText={setQuestionTexte}
                onSubmitEditing={envoyerQuestionTexte}
                returnKeyType="send"
              />
              <TouchableOpacity style={styles.boutonEnvoyer} onPress={envoyerQuestionTexte}>
                <Text style={styles.texteEnvoyer}>{t.envoyer}</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Transcription */}
          {transcription !== "" && (
            <View style={[styles.carteTranscription, {
              backgroundColor: th.fondReponse, borderColor: th.bordure
            }]}>
              <Text style={[styles.texteTranscription, { color: th.texteFaible }]}>
                {transcription}
              </Text>
            </View>
          )}

          {/* Réponse */}
          {reponse !== "" && (
            <View style={[styles.carteReponse, {
              backgroundColor: th.fondReponse, borderColor: th.accent
            }]}>
              <Text style={[styles.labelReponse, { color: th.accent }]}>{t.sentinelle}</Text>
              <Text style={[styles.texteReponse, { color: th.texte }]}>{reponse}</Text>
            </View>
          )}
        </View>

        <Text style={[styles.footer, { color: th.texteFaible }]}>
          {t.maj} • {capteurs?.timestamp || "--:--:--"}
        </Text>
      </ScrollView>
    </View>
  );
}

// ── Carte capteur ─────────────────────────────────────────────
function CarteCapteur({ th, label, valeur, danger, defaillant }) {
  const bg     = danger ? "#2d1b1b" : defaillant ? "#2d2208" : th.fondCarte;
  const border = danger ? "#f85149" : defaillant ? "#e3b341" : th.bordure;
  const color  = danger ? "#f85149" : defaillant ? "#e3b341" : th.accent;
  return (
    <View style={[styles.carte, { backgroundColor: bg, borderColor: border }]}>
      <Text style={[styles.carteValeur, { color }]}>
        {defaillant ? "⚠️" : valeur}
      </Text>
      <Text style={[styles.carteLabel, { color: th.texteFaible }]}>{label}</Text>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────
const styles = StyleSheet.create({
  content:            { padding: 16, paddingTop: 50, paddingBottom: 40 },
  entete:             { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 },
  titre:              { fontSize: 20, fontWeight: "bold" },
  sousTitre:          { fontSize: 11, marginTop: 2 },
  controles:          { alignItems: "flex-end", gap: 8 },
  switchGroupe:       { flexDirection: "row", alignItems: "center", gap: 4 },
  switchLabel:        { fontSize: 12, fontWeight: "bold", color: "#8b949e" },
  switchPetit:        { transform: [{ scaleX: 0.85 }, { scaleY: 0.85 }] },
  boutonTheme:        { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5, gap: 4 },
  labelTheme:         { fontSize: 12 },
  carteStatut:        { borderWidth: 2, borderRadius: 12, padding: 16, marginBottom: 12, alignItems: "center" },
  texteStatut:        { fontSize: 18, fontWeight: "bold" },
  messageAnalyse:     { fontSize: 13, marginTop: 6, textAlign: "center" },
  titreSectionPlat:   { fontSize: 12, fontWeight: "bold", marginBottom: 8, marginTop: 4, textTransform: "uppercase", letterSpacing: 1 },
  grille:             { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", marginBottom: 16 },
  carte:              { borderWidth: 1, borderRadius: 10, padding: 12, width: "48%", marginBottom: 8, alignItems: "center" },
  carteValeur:        { fontSize: 20, fontWeight: "bold" },
  carteLabel:         { fontSize: 11, marginTop: 4, textAlign: "center" },
  carteVocale:        { borderWidth: 1, borderRadius: 12, padding: 20, alignItems: "center", marginBottom: 16 },
  titreSection:       { fontSize: 15, fontWeight: "bold", marginBottom: 12 },
  indicateurEtat:     { borderWidth: 1, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8, marginBottom: 14, width: "100%" },
  texteEtat:          { fontSize: 13, fontWeight: "bold", textAlign: "center" },
  boutonMicro:        { borderRadius: 60, width: 110, height: 110, justifyContent: "center", alignItems: "center", marginBottom: 12, elevation: 4 },
  iconeMicro:         { fontSize: 34 },
  texteBouton:        { fontSize: 10, color: "white", marginTop: 4, textAlign: "center", paddingHorizontal: 8 },
  boutonModeTexte:    { borderWidth: 1, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 6, marginBottom: 12 },
  texteModeTexte:     { fontSize: 12 },
  zoneTexte:          { width: "100%", flexDirection: "row", gap: 8, marginBottom: 12 },
  champTexte:         { flex: 1, borderWidth: 1, borderRadius: 8, padding: 10, fontSize: 14 },
  boutonEnvoyer:      { backgroundColor: "#238636", borderRadius: 8, padding: 10, justifyContent: "center" },
  texteEnvoyer:       { color: "white", fontWeight: "bold", fontSize: 13 },
  carteTranscription: { borderWidth: 1, borderRadius: 8, padding: 10, width: "100%", marginBottom: 10 },
  texteTranscription: { fontSize: 13, fontStyle: "italic" },
  carteReponse:       { borderWidth: 1, borderRadius: 10, padding: 14, width: "100%" },
  labelReponse:       { fontSize: 12, fontWeight: "bold", marginBottom: 6 },
  texteReponse:       { fontSize: 14, lineHeight: 22 },
  footer:             { fontSize: 11, textAlign: "center", marginTop: 8 },
});
