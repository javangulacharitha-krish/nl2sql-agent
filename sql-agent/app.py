"""
app.py — Streamlit UI — all 15 improvements active.
"""
import os, sys, time, json, re, math
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

st.set_page_config(
    page_title="SQL Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Lazy imports (after path is set) ─────────────────────────────────────────
from data.seed_db      import seed
from db_executor       import execute_sql, test_connection, clear_cache, DB_PATH
from schema_loader     import get_schema, get_schema_dict
from agent             import run_agent, MAX_RETRIES, explain_result, _make_client
from logger            import CorrectionLogger
from prompts           import SYSTEM_PROMPT

# ── DB bootstrap ─────────────────────────────────────────────────────────────
if not os.path.exists(DB_PATH):
    with st.spinner("Setting up database…"):
        seed()

# ── Session state ─────────────────────────────────────────────────────────────
if "logger"        not in st.session_state:
    st.session_state.logger   = CorrectionLogger()
if "history"       not in st.session_state:
    st.session_state.history  = []
if "stream_buffer" not in st.session_state:
    st.session_state.stream_buffer = ""
if "last_result"   not in st.session_state:
    st.session_state.last_result = None

logger: CorrectionLogger = st.session_state.logger

# ══════════════════════════════════════════════════════════════════════════════
# CSS + 3D ANIMATIONS
# ══════════════════════════════════════════════════════════════════════════════
def inject_css():
    st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ════════════════════════════════════════════════════
   PALETTE  — Professional Charcoal + Emerald
   bg0  #0E0E11  deepest bg
   bg1  #141418  sidebar
   bg2  #1C1C22  cards
   bg3  #22222A  elevated cards
   em   #00C896  emerald — primary accent
   am   #F0A500  amber   — warnings / secondary
   ro   #FF4D6A  rose    — errors
   ice  #A8B5C8  muted text
   bdr  rgba(255,255,255,.07) borders
════════════════════════════════════════════════════ */
:root{
  --bg0:#0E0E11; --bg1:#141418; --bg2:#1C1C22; --bg3:#22222A;
  --em:#00C896;  --am:#F0A500;  --ro:#FF4D6A;
  --txt:#EAEDF2; --ice:#A8B5C8; --dim:#5A6478;
  --bdr:rgba(255,255,255,.07);
  --bdr-em:rgba(0,200,150,.22);
  --glow-em:0 0 22px rgba(0,200,150,.28);
  --glow-am:0 0 22px rgba(240,165,0,.28);
  --glow-ro:0 0 22px rgba(255,77,106,.28);
}

html,body,[data-testid="stAppViewContainer"]{
  background:var(--bg0)!important;
  font-family:'Inter',sans-serif;
  color:var(--txt);
}
[data-testid="stSidebar"]{
  background:var(--bg1)!important;
  border-right:1px solid var(--bdr)!important;
}
[data-testid="stHeader"]{background:transparent!important;}
#MainMenu,footer,[data-testid="stToolbar"]{display:none!important;}
.block-container{padding-top:1.8rem!important;max-width:1440px!important;}

/* ── HERO ── */
.hero{
  position:relative;
  background:linear-gradient(140deg,#111114 0%,#161D1B 50%,#111510 100%);
  border-radius:20px;padding:44px 52px;margin-bottom:28px;overflow:hidden;
  border:1px solid rgba(0,200,150,.22);
  box-shadow:0 32px 80px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.06);
}
.hero::before{
  content:'';position:absolute;inset:0;
  background:
    radial-gradient(ellipse at 10% 60%,rgba(0,200,150,.12) 0%,transparent 50%),
    radial-gradient(ellipse at 80% 10%,rgba(240,165,0,.08)  0%,transparent 50%),
    radial-gradient(ellipse at 60% 90%,rgba(0,200,150,.06)  0%,transparent 55%);
  animation:hpulse 8s ease-in-out infinite;
}
@keyframes hpulse{0%,100%{opacity:.5}50%{opacity:1}}
.hero::after{
  content:'';position:absolute;inset:0;
  background-image:
    linear-gradient(rgba(0,200,150,.03) 1px,transparent 1px),
    linear-gradient(90deg,rgba(0,200,150,.03) 1px,transparent 1px);
  background-size:48px 48px;
  transform:perspective(700px) rotateX(14deg);transform-origin:bottom;
  animation:gmove 24s linear infinite;
}
@keyframes gmove{0%{background-position:0 0}100%{background-position:0 48px}}

.hero-title{
  position:relative;z-index:2;font-size:2.75rem;font-weight:800;letter-spacing:-.025em;
  color:#EAEDF2;
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;
}
.hero-title .ht-icon{
  font-size:3rem;line-height:1;
  filter:drop-shadow(0 0 14px rgba(0,200,150,.7));
  -webkit-text-fill-color:initial;
  display:inline-block;
}
.hero-title .ht-plain{
  color:#EAEDF2;
  -webkit-text-fill-color:#EAEDF2;
}
.hero-title .ht-accent{
  background:linear-gradient(120deg,#00C896,#00E5A8);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  animation:tshimmer 4s ease-in-out infinite;
}
@keyframes tshimmer{0%,100%{filter:brightness(1)}50%{filter:brightness(1.2)}}
.hero-sub{position:relative;z-index:2;color:#C8CDD8;font-size:1rem;margin-top:12px;font-weight:400;letter-spacing:.01em;}
.hero-badges{position:relative;z-index:2;display:flex;gap:9px;flex-wrap:wrap;margin-top:20px;}
.badge{
  padding:5px 13px;border-radius:6px;font-size:.73rem;font-weight:600;
  letter-spacing:.04em;border:1px solid;animation:bfloat 3.5s ease-in-out infinite;
}
.b1{background:rgba(0,200,150,.1); border-color:rgba(0,200,150,.3); color:#00C896;}
.b2{background:rgba(240,165,0,.1);  border-color:rgba(240,165,0,.3);  color:#F0A500; animation-delay:.5s;}
.b3{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.12);color:var(--ice);animation-delay:1s;}
.b4{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.12);color:var(--ice);animation-delay:1.5s;}
.b5{background:rgba(255,77,106,.09); border-color:rgba(255,77,106,.25); color:#FF4D6A; animation-delay:2s;}
@keyframes bfloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}

/* ── METRIC CARDS ── */
.mc{
  background:var(--bg2);border-radius:14px;padding:22px 22px 18px;
  border:1px solid var(--bdr);position:relative;overflow:hidden;
  transition:transform .25s ease,box-shadow .25s ease;
}
.mc:hover{transform:translateY(-5px) rotateX(3deg);box-shadow:0 20px 44px rgba(0,0,0,.6),var(--glow-em);}
.mc::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--em),transparent);
  animation:scan 4s linear infinite;
}
@keyframes scan{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.mc-val{
  font-size:2.1rem;font-weight:700;letter-spacing:-.02em;
  color:var(--em);
}
.mc-val.warn{color:var(--am);}
.mc-val.bad {color:var(--ro);}
.mc-lbl{color:var(--ice);font-size:.78rem;margin-top:5px;font-weight:500;}
.mc-delta{font-size:.73rem;margin-top:9px;}
.pos{color:var(--em)}.neg{color:var(--ro)}

/* ── PANEL ── */
.panel{
  background:var(--bg2);border-radius:14px;padding:22px 24px;
  border:1px solid var(--bdr);margin-bottom:16px;
  position:relative;overflow:hidden;
}
.panel::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--em),transparent);
  animation:bflow 6s ease-in-out infinite;
}
@keyframes bflow{
  0%{opacity:0;transform:scaleX(0);transform-origin:left}
  50%{opacity:1;transform:scaleX(1);transform-origin:left}
  51%{opacity:1;transform:scaleX(1);transform-origin:right}
  100%{opacity:0;transform:scaleX(0);transform-origin:right}
}

/* ── PIPELINE ── */
.pipe{
  display:flex;align-items:center;
  background:var(--bg3);border-radius:12px;
  padding:14px 20px;border:1px solid var(--bdr);
  overflow-x:auto;gap:2px;margin-bottom:18px;
}
.pstep{display:flex;flex-direction:column;align-items:center;gap:5px;padding:8px 12px;min-width:68px;}
.picon{
  width:36px;height:36px;border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  font-size:1.05rem;background:var(--bg1);border:1px solid var(--bdr);
  transition:all .3s;
}
.pstep.done .picon{background:rgba(0,200,150,.12);border-color:var(--em);box-shadow:var(--glow-em);}
.plbl{font-size:.64rem;color:var(--dim);text-align:center;line-height:1.3;font-weight:500;}
.parr{color:var(--dim);font-size:1rem;padding:0 1px;}

/* ── ATTEMPT CHAIN ── */
.chain{display:flex;flex-direction:column;gap:0;position:relative;padding-left:26px;}
.chain::before{
  content:'';position:absolute;left:8px;top:18px;bottom:18px;width:1px;
  background:linear-gradient(to bottom,var(--em),var(--am),var(--ro));opacity:.3;
}
.anode{
  background:var(--bg2);border-radius:10px;padding:16px 18px;
  border:1px solid var(--bdr);margin-bottom:10px;
  position:relative;transition:all .25s;animation:nslide .3s ease forwards;
}
.anode:hover{transform:translateX(3px);border-color:var(--em);box-shadow:var(--glow-em);}
@keyframes nslide{from{opacity:0;transform:translateX(-14px)}to{opacity:1;transform:translateX(0)}}
.anode::before{
  content:'';position:absolute;left:-20px;top:50%;transform:translateY(-50%);
  width:10px;height:10px;border-radius:50%;
  background:var(--am);box-shadow:0 0 8px var(--am);
}
.anode.suc::before{background:var(--em);box-shadow:0 0 8px var(--em);}
.anode.err::before{background:var(--ro);box-shadow:0 0 8px var(--ro);}
.anode.cor::before{background:var(--am);box-shadow:0 0 8px var(--am);}
.ahead{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;}

/* badges */
.bs{ background:rgba(0,200,150,.1);  color:#00C896; border:1px solid rgba(0,200,150,.28); padding:2px 10px;border-radius:5px;font-size:.7rem;font-weight:700;}
.bf{ background:rgba(255,77,106,.1); color:#FF4D6A; border:1px solid rgba(255,77,106,.28);padding:2px 10px;border-radius:5px;font-size:.7rem;font-weight:700;}
.bc2{background:rgba(240,165,0,.1);  color:#F0A500; border:1px solid rgba(240,165,0,.28); padding:2px 10px;border-radius:5px;font-size:.7rem;font-weight:700;}
.tbdg{background:var(--bg3);color:var(--ice);border:1px solid var(--bdr);padding:2px 9px;border-radius:5px;font-size:.69rem;}
.rbdg{background:rgba(0,200,150,.08);color:var(--em);border:1px solid rgba(0,200,150,.2);padding:2px 9px;border-radius:5px;font-size:.69rem;}
.cachebdg{background:rgba(240,165,0,.08);color:var(--am);border:1px solid rgba(240,165,0,.2);padding:2px 9px;border-radius:5px;font-size:.69rem;}
.cotbdg{background:rgba(255,255,255,.06);color:var(--ice);border:1px solid var(--bdr);padding:2px 9px;border-radius:5px;font-size:.69rem;}

/* ── SQL BLOCK ── */
.sqlb{
  background:#0A0A0D;border:1px solid rgba(255,255,255,.08);
  border-radius:8px;padding:12px 14px;
  font-family:'JetBrains Mono',monospace;font-size:.79rem;
  color:#D4D8E2;white-space:pre-wrap;word-break:break-all;
  line-height:1.7;position:relative;
}
.sqlb::before{
  content:'SQL';position:absolute;top:6px;right:10px;
  font-size:.6rem;color:var(--dim);
  font-family:'Inter',sans-serif;font-weight:700;letter-spacing:.08em;
}
.kw{color:#00C896;font-weight:600;}
.fn{color:#F0A500;}
.str{color:#A8D8A8;}
.num{color:#FFB347;}

/* ── ERROR BOX ── */
.errbox{
  background:rgba(255,77,106,.07);border:1px solid rgba(255,77,106,.22);
  border-radius:8px;padding:10px 13px;
  color:#FF8FA3;font-size:.77rem;
  font-family:'JetBrains Mono',monospace;margin-top:8px;line-height:1.6;
}

/* ── STREAM BOX ── */
.streambox{
  background:#0A0A0D;border:1px solid rgba(0,200,150,.2);
  border-radius:8px;padding:14px;
  font-family:'JetBrains Mono',monospace;font-size:.8rem;
  color:#D4D8E2;white-space:pre-wrap;min-height:48px;line-height:1.7;
}
.cursor{
  display:inline-block;width:7px;height:.95em;
  background:var(--em);
  animation:blink .65s step-end infinite;
  vertical-align:text-bottom;margin-left:2px;border-radius:1px;
}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

/* ── EXPLANATION BOX ── */
.explainbox{
  background:linear-gradient(135deg,rgba(0,200,150,.07),rgba(240,165,0,.04));
  border:1px solid rgba(0,200,150,.2);border-radius:12px;
  padding:16px 18px;margin-top:14px;
  color:var(--txt);font-size:.9rem;line-height:1.72;
  animation:fadeup .45s ease;
}
.explainbox-title{
  font-size:.68rem;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--em);margin-bottom:8px;
}
@keyframes fadeup{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ── RESULT SECTION ── */
.res-sec{
  background:var(--bg2);border-radius:14px;padding:22px;
  border:1px solid var(--bdr);margin-top:16px;animation:fadeup .4s ease;
}
.res-hdr{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;}

/* ── BANNERS ── */
.sucbanner{
  background:linear-gradient(135deg,rgba(0,200,150,.1),rgba(0,200,150,.04));
  border:1px solid rgba(0,200,150,.25);border-radius:12px;
  padding:14px 20px;display:flex;align-items:center;gap:14px;
  animation:gblow 3s ease-in-out infinite;
}
@keyframes gblow{0%,100%{box-shadow:0 0 0 rgba(0,200,150,0)}50%{box-shadow:0 0 24px rgba(0,200,150,.12)}}
.failbanner{
  background:linear-gradient(135deg,rgba(255,77,106,.09),rgba(240,165,0,.05));
  border:1px solid rgba(255,77,106,.25);border-radius:12px;
  padding:14px 20px;display:flex;align-items:center;gap:14px;
}

/* ── SQL EDITOR LABEL ── */
.editor-label{
  font-size:.68rem;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--em);margin-bottom:6px;
}

/* ── SIDEBAR ── */
.sbsec{
  background:#1C1C22;border-radius:10px;padding:14px 15px;
  margin-bottom:12px;border:1px solid rgba(255,255,255,.1);
}
.sbtitle{
  font-size:.68rem;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;color:#00C896;margin-bottom:10px;
  display:flex;align-items:center;gap:6px;
}
.schema-tname{color:#00C896;font-weight:700;margin:8px 0 3px;font-size:.8rem;}
.schema-col{color:#C8CDD8;padding-left:11px;font-size:.74rem;line-height:1.8;}
.schema-type{color:#F0A500;font-size:.7rem;}
.hcard{
  background:#22222A;border-radius:8px;padding:11px 13px;
  border:1px solid rgba(255,255,255,.08);margin-bottom:7px;transition:all .2s;
}
.hcard:hover{border-color:#00C896;transform:translateX(2px);}
.hq{color:#EAEDF2;font-size:.83rem;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.hmeta{display:flex;gap:7px;align-items:center;}
.ds{width:6px;height:6px;background:#00C896;border-radius:50%;display:inline-block;flex-shrink:0;}
.df{width:6px;height:6px;background:#FF4D6A;border-radius:50%;display:inline-block;flex-shrink:0;}

/* ══════════════════════════════════════════════
   FORM WIDGETS — full visibility overrides
══════════════════════════════════════════════ */

/* All Streamlit labels — make them clearly visible */
.stTextArea label,
.stTextInput label,
.stSelectbox label,
.stSlider label,
.stToggle label,
.stCheckbox label,
.stRadio label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
label[data-testid],
.st-emotion-cache-1inwz65,
.st-emotion-cache-ue6h4q,
.st-emotion-cache-16idsys p {
  color:#EAEDF2!important;
  font-size:.84rem!important;
  font-weight:500!important;
  opacity:1!important;
}

/* Streamlit paragraph text inside sidebar */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {
  color:#EAEDF2!important;
  opacity:1!important;
}

/* Text inputs and textareas */
.stTextArea textarea,
.stTextInput input {
  background:#1C1C22!important;
  border:1px solid rgba(255,255,255,.18)!important;
  border-radius:8px!important;
  color:#EAEDF2!important;
  font-family:'Inter',sans-serif!important;
  font-size:.92rem!important;
  caret-color:#00C896!important;
  transition:border-color .2s,box-shadow .2s!important;
}
.stTextArea textarea::placeholder,
.stTextInput input::placeholder {
  color:#5A6478!important;
  opacity:1!important;
}
.stTextArea textarea:focus,
.stTextInput input:focus {
  border-color:#00C896!important;
  box-shadow:0 0 0 2px rgba(0,200,150,.15)!important;
  outline:none!important;
}

/* Selectbox — container, value text, arrow */
.stSelectbox > div > div,
.stSelectbox > div > div > div,
[data-testid="stSelectbox"] > div > div {
  background:#1C1C22!important;
  border:1px solid rgba(255,255,255,.18)!important;
  border-radius:8px!important;
  color:#EAEDF2!important;
}
/* the displayed selected value */
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div,
[data-baseweb="select"] .css-1jqq78o-placeholder,
[data-baseweb="select"] [class*="singleValue"],
[data-baseweb="select"] [class*="placeholder"] {
  color:#EAEDF2!important;
}
/* dropdown chevron icon */
.stSelectbox svg { fill:#A8B5C8!important; }

/* Selectbox dropdown list */
[data-baseweb="popover"],
[data-baseweb="menu"],
[role="listbox"],
[data-baseweb="menu"] ul,
[data-baseweb="menu"] li {
  background:#1C1C22!important;
  color:#EAEDF2!important;
  border:1px solid rgba(255,255,255,.12)!important;
}
[data-baseweb="menu"] li:hover,
[role="option"]:hover {
  background:#22222A!important;
  color:#00C896!important;
}
[aria-selected="true"][role="option"] {
  background:rgba(0,200,150,.12)!important;
  color:#00C896!important;
}

/* Toggle / checkbox */
.stToggle > label,
.stCheckbox > label {
  color:#EAEDF2!important;
}
/* toggle track off state */
[data-testid="stToggle"] > label > div[data-checked="false"] {
  background:#3A3A44!important;
}
/* toggle track on state */
[data-testid="stToggle"] > label > div[data-checked="true"] {
  background:#00C896!important;
}
/* toggle text label */
[data-testid="stToggle"] p,
[data-testid="stToggle"] span {
  color:#EAEDF2!important;
}

/* Slider */
[data-testid="stSlider"] label,
[data-testid="stSlider"] p {
  color:#EAEDF2!important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
  background:#00C896!important;
  border-color:#00C896!important;
}

/* Expander */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
  color:#EAEDF2!important;
  font-weight:600!important;
}
[data-testid="stExpander"] {
  background:var(--bg2)!important;
  border:1px solid rgba(255,255,255,.08)!important;
  border-radius:10px!important;
}

/* Info / warning boxes */
[data-testid="stInfo"],
[data-testid="stWarning"] {
  background:#22222A!important;
  border-left:3px solid #00C896!important;
  color:#EAEDF2!important;
}
[data-testid="stInfo"] p,
[data-testid="stWarning"] p { color:#EAEDF2!important; }

/* Success / error */
[data-testid="stSuccess"]  { border-left:3px solid #00C896!important; }
[data-testid="stError"]    { border-left:3px solid #FF4D6A!important; }

/* Buttons */
.stButton > button {
  background:linear-gradient(135deg,#00C896,#00A07A)!important;
  color:#0A0A0D!important;
  border:none!important;
  border-radius:8px!important;
  font-weight:700!important;
  font-size:.88rem!important;
  padding:9px 22px!important;
  letter-spacing:.02em!important;
  transition:all .25s!important;
  box-shadow:0 4px 16px rgba(0,200,150,.22)!important;
}
.stButton > button:hover {
  transform:translateY(-2px)!important;
  box-shadow:0 8px 28px rgba(0,200,150,.35)!important;
  filter:brightness(1.08)!important;
}
.stButton > button:active { transform:translateY(0)!important; }
/* secondary / ghost buttons (Clear, Reset) */
.stButton > button[kind="secondary"],
.stButton > button[data-testid*="secondary"] {
  background:transparent!important;
  border:1px solid rgba(255,255,255,.18)!important;
  color:#EAEDF2!important;
  box-shadow:none!important;
}
.stButton > button[kind="secondary"]:hover {
  border-color:#00C896!important;
  color:#00C896!important;
  background:rgba(0,200,150,.06)!important;
}

/* Tabs */
div[data-testid="stTabs"] button {
  color:#A8B5C8!important;
  font-weight:500!important;
  font-size:.9rem!important;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
  color:#00C896!important;
  border-bottom:2px solid #00C896!important;
}
div[data-testid="stTabs"] [data-baseweb="tab-border"] {
  background:rgba(255,255,255,.07)!important;
}

/* Dataframe */
[data-testid="stDataFrame"] * { font-family:'Inter',sans-serif!important; }
[data-testid="stDataFrame"] th {
  background:#22222A!important;
  color:#A8B5C8!important;
  font-size:.78rem!important;
  font-weight:600!important;
  letter-spacing:.04em!important;
}
[data-testid="stDataFrame"] td {
  background:#1C1C22!important;
  color:#EAEDF2!important;
  font-size:.84rem!important;
}

/* Download button */
[data-testid="stDownloadButton"] > button {
  background:transparent!important;
  border:1px solid rgba(0,200,150,.35)!important;
  color:#00C896!important;
  font-weight:600!important;
  box-shadow:none!important;
}
[data-testid="stDownloadButton"] > button:hover {
  background:rgba(0,200,150,.08)!important;
}

/* Spinner text */
[data-testid="stSpinner"] p { color:#A8B5C8!important; }

/* Markdown / headers inside app */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 {
  color:#EAEDF2!important;
}
[data-testid="stMarkdownContainer"] p {
  color:#A8B5C8!important;
}
[data-testid="stMarkdownContainer"] code {
  background:#22222A!important;
  color:#00C896!important;
  border-radius:4px!important;
  padding:1px 5px!important;
}

/* Scrollbars */
::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:var(--bg1); }
::-webkit-scrollbar-thumb { background:rgba(0,200,150,.3); border-radius:2px; }
::-webkit-scrollbar-thumb:hover { background:rgba(0,200,150,.55); }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
_KW = re.compile(
    r'\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|'
    r'GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|AS|ON|AND|OR|NOT|IN|IS|'
    r'NULL|DISTINCT|COUNT|SUM|AVG|MAX|MIN|WITH|UNION|ALL|CASE|WHEN|THEN|'
    r'ELSE|END|BY|BETWEEN|LIKE|EXISTS|DESC|ASC|OVER|PARTITION)\b',
    re.IGNORECASE
)

def _hl(sql: str) -> str:
    return _KW.sub(lambda m: f'<span class="kw">{m.group(0).upper()}</span>', sql)

def sql_block(sql: str):
    st.markdown(f'<div class="sqlb">{_hl(sql)}</div>', unsafe_allow_html=True)

def render_chain(attempts: list):
    st.markdown('<div class="chain">', unsafe_allow_html=True)
    for i, att in enumerate(attempts):
        is_last = i == len(attempts) - 1
        ok      = att["success"]
        if ok:
            nc, badge, icon = "anode suc", '<span class="bs">✓ SUCCESS</span>', "🟢"
        elif is_last and not ok:
            nc, badge, icon = "anode err", '<span class="bf">✗ FAILED</span>',  "🔴"
        else:
            nc, badge, icon = "anode cor", '<span class="bc2">⚡ CORRECTING</span>', "🟡"

        cache_tag = '<span class="cachebdg">⚡ cache hit</span>' if att.get("from_cache") else ""
        row_tag   = f'<span class="rbdg">{att.get("row_count",0)} rows</span>' if ok else ""
        err_type  = att.get("error_type","")
        etype_tag = f'<span style="font-size:.7rem;color:#94a3b8;">[{err_type}]</span>' if err_type and not ok else ""

        st.markdown(f"""
        <div class="{nc}" style="animation-delay:{i*.1}s">
          <div class="ahead">
            <span>{icon}</span>
            <span style="font-weight:600;font-size:.9rem;">Attempt {att['attempt']}</span>
            {badge}
            <span class="tbdg">⏱ {att.get('execution_time_ms',0):.1f}ms</span>
            {row_tag}{cache_tag}{etype_tag}
          </div>
        """, unsafe_allow_html=True)

        sql_block(att["sql"] or "— no SQL generated —")

        if att.get("error"):
            st.markdown(f'<div class="errbox">⚠ {att["error"]}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def metric_cards(stats: dict):
    if not stats:
        return
    items = [
        ("Queries Run",    str(stats["total_queries"]), "", True),
        ("Success Rate",   f"{stats['success_rate']}%", "target >87%",
         stats["success_rate"] >= 87),
        ("First-Try Rate", f"{stats['first_try_rate']}%", "target >60%",
         stats["first_try_rate"] >= 60),
        ("Avg Attempts",   str(stats["avg_attempts"]), "target <1.5",
         stats["avg_attempts"] < 1.5),
    ]
    cols = st.columns(4)
    for col, (lbl, val, delta, good) in zip(cols, items):
        dcls  = "pos" if good else "neg"
        vcls  = "" if good else " bad"
        dt    = f'<div class="mc-delta {dcls}">{delta}</div>' if delta else ""
        col.markdown(f"""
        <div class="mc">
          <div class="mc-val{vcls}">{val}</div>
          <div class="mc-lbl">{lbl}</div>
          {dt}
        </div>""", unsafe_allow_html=True)


def sidebar_schema():
    sd = get_schema_dict()
    st.markdown('<div class="sbsec"><div class="sbtitle">📐 Schema</div>', unsafe_allow_html=True)
    for tbl, cols in sd.items():
        st.markdown(f'<div class="schema-tname">▸ {tbl}</div>', unsafe_allow_html=True)
        for c in cols:
            pk = " 🔑" if c["pk"] else ""
            st.markdown(
                f'<div class="schema-col">{c["name"]} '
                f'<span class="schema-type">{c["type"]}</span>{pk}</div>',
                unsafe_allow_html=True
            )
    st.markdown('</div>', unsafe_allow_html=True)


def radar(stats: dict):
    cats = ["Success Rate","First-Try","Speed","Robustness","Coverage"]
    spd  = max(0, min(100, 100 - stats.get("avg_time_ms",1000)/20))
    rob  = max(0, min(100, 100 - (stats.get("avg_attempts",1)-1)*50))
    vals = [stats.get("success_rate",0), stats.get("first_try_rate",0),
            spd, rob, min(100, stats.get("total_queries",0)*10)]
    fig  = go.Figure(go.Scatterpolar(
        r=vals+[vals[0]], theta=cats+[cats[0]], fill='toself',
        fillcolor='rgba(0,200,150,.12)',
        line=dict(color='#00C896',width=2),
        marker=dict(size=6,color='#00C896'),
    ))
    fig.update_layout(
        polar=dict(bgcolor='rgba(0,0,0,0)',
            radialaxis=dict(visible=True,range=[0,100],
                gridcolor='rgba(255,255,255,.05)',tickfont=dict(color='#5A6478',size=9)),
            angularaxis=dict(gridcolor='rgba(255,255,255,.05)',tickfont=dict(color='#A8B5C8',size=10))),
        paper_bgcolor='rgba(0,0,0,0)',font=dict(color='#EAEDF2'),
        margin=dict(l=35,r=35,t=20,b=20),height=270,
    )
    return fig


def attempts_bar(history: list):
    if not history: return None
    fig = go.Figure(go.Bar(
        x=[f"Q{i+1}" for i in range(len(history))],
        y=[len(r.get("attempts",[])) for r in history],
        marker_color=["#00C896" if r.get("success") else "#FF4D6A" for r in history],
        text=[len(r.get("attempts",[])) for r in history],
        textposition='outside', textfont=dict(color='#5A6478',size=10),
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#EAEDF2'),
        xaxis=dict(gridcolor='rgba(255,255,255,.04)',tickfont=dict(color='#5A6478')),
        yaxis=dict(gridcolor='rgba(255,255,255,.04)',tickfont=dict(color='#5A6478'),
                   title="Attempts",range=[0,max(len(r.get("attempts",[])) for r in history)+1.8]),
        margin=dict(l=38,r=16,t=16,b=38),height=220,bargap=.28,
    )
    return fig


def scatter_3d(history: list):
    if len(history) < 3: return None
    x = list(range(1, len(history)+1))
    y = [len(r.get("attempts",[])) for r in history]
    z = [r.get("total_time_ms",0) for r in history]
    c = ["#00C896" if r.get("success") else "#FF4D6A" for r in history]
    q = [r.get("question","")[:40] for r in history]
    fig = go.Figure(go.Scatter3d(
        x=x,y=y,z=z,mode='markers+lines',
        marker=dict(size=8,color=c,opacity=.88,line=dict(color='rgba(255,255,255,.15)',width=.5)),
        line=dict(color='rgba(0,200,150,.2)',width=2),
        text=q,
        hovertemplate='<b>%{text}</b><br>Query #%{x}<br>Attempts: %{y}<br>%{z:.0f}ms<extra></extra>',
    ))
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='Query #',backgroundcolor='rgba(0,0,0,0)',gridcolor='rgba(255,255,255,.05)',color='#A8B5C8'),
            yaxis=dict(title='Attempts',backgroundcolor='rgba(0,0,0,0)',gridcolor='rgba(255,255,255,.05)',color='#A8B5C8'),
            zaxis=dict(title='ms',backgroundcolor='rgba(0,0,0,0)',gridcolor='rgba(255,255,255,.05)',color='#A8B5C8'),
            bgcolor='rgba(0,0,0,0)',
        ),
        paper_bgcolor='rgba(0,0,0,0)',font=dict(color='#EAEDF2'),
        margin=dict(l=0,r=0,t=10,b=0),height=390,
    )
    return fig


def auto_chart(df: pd.DataFrame, question: str):
    num = df.select_dtypes(include="number").columns.tolist()
    txt = df.select_dtypes(exclude="number").columns.tolist()
    if not num or len(df) > 60: return
    yc = num[0]
    xc = txt[0] if txt else df.columns[0]
    if xc == yc: xc = df.columns[0]
    if len(df) <= 20:
        fig = px.bar(df, x=xc, y=yc, color_discrete_sequence=["#00C896"], title=f"{yc} by {xc}")
    else:
        fig = px.line(df, x=xc, y=yc, color_discrete_sequence=["#00C896"],
                      title=f"{yc} over {xc}", markers=True)
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#EAEDF2'),
        xaxis=dict(gridcolor='rgba(255,255,255,.05)',tickfont=dict(color='#5A6478')),
        yaxis=dict(gridcolor='rgba(255,255,255,.05)',tickfont=dict(color='#5A6478')),
        title_font=dict(color='#A8B5C8',size=12),
        margin=dict(l=38,r=14,t=38,b=38),
    )
    st.plotly_chart(fig, use_container_width=True)


SAMPLES = [
    "Show me the top 5 customers by total spending",
    "What are the 3 best-selling product categories by revenue?",
    "How many orders were placed per month?",
    "Which products have an average rating above 4?",
    "Find users who have placed more than 3 orders",
    "What is the total revenue from Electronics products?",
    "List the 10 most expensive products with their category",
    "Show cancelled orders with customer names and totals",
    "What is the average order value by city?",
    "Which product has the most reviews and what is its average rating?",
    "Find users who bought Electronics but never bought Books",
    "Show monthly revenue for all delivered orders",
    "What percentage of orders were cancelled per category?",
    "Show the top 3 cities by number of customers",
]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    inject_css()

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:16px 0 22px">
          <div style="font-size:3.2rem;line-height:1;filter:drop-shadow(0 0 12px rgba(0,200,150,.5))">🤖</div>
          <div style="font-weight:800;font-size:1.15rem;color:#EAEDF2;margin-top:10px;letter-spacing:-.01em">SQL Agent</div>
          <div style="font-size:.68rem;color:#00C896;letter-spacing:.12em;text-transform:uppercase;margin-top:4px;font-weight:600">Self-Correcting · LLM-Powered</div>
          <div style="width:40px;height:2px;background:linear-gradient(90deg,transparent,#00C896,transparent);margin:12px auto 0;border-radius:1px"></div>
        </div>""", unsafe_allow_html=True)

        # Model config
        st.markdown('<div class="sbsec"><div class="sbtitle">⚙️ Model Config</div>', unsafe_allow_html=True)
        model_choice = st.selectbox("Model", [
            "gpt-3.5-turbo","gpt-4o-mini","gpt-4o",
            "ollama:mistral","ollama:llama3","ollama:codellama",
        ], label_visibility="collapsed")
        api_key = st.text_input(
            "OpenAI API Key", value=os.getenv("OPENAI_API_KEY",""),
            type="password", placeholder="sk-… (OpenAI models only)",
        )
        if api_key: os.environ["OPENAI_API_KEY"] = api_key
        enable_cot     = st.toggle("Chain-of-Thought for complex queries", value=True)
        enable_explain = st.toggle("Explain results in plain English", value=True)
        enable_stream  = st.toggle("Stream SQL generation", value=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if model_choice.startswith("ollama:"):
            st.info("🦙 Ollama — make sure `ollama serve` is running on :11434", icon="ℹ️")

        # DB status
        st.markdown('<div class="sbsec"><div class="sbtitle">🗄️ Database</div>', unsafe_allow_html=True)
        ok = test_connection()
        st.markdown(
            f'<span style="color:{"#00C896" if ok else "#FF4D6A"}">{"● Connected" if ok else "● Disconnected"} — ecommerce.db</span>',
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        if c1.button("🔄 Re-seed"):
            seed(); st.success("Re-seeded!")
        if c2.button("🗑 Clear Cache"):
            clear_cache(); st.success("Cache cleared!")
        st.markdown('</div>', unsafe_allow_html=True)

        # LangSmith
        st.markdown('<div class="sbsec"><div class="sbtitle">🔭 LangSmith Tracing</div>', unsafe_allow_html=True)
        ls_key = st.text_input("LangChain API Key", value=os.getenv("LANGCHAIN_API_KEY",""),
                                type="password", placeholder="ls-…")
        if ls_key:
            os.environ["LANGCHAIN_API_KEY"] = ls_key
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            st.markdown('<span style="color:#00C896;font-size:.78rem">● Tracing enabled</span>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        sidebar_schema()

        # History search (#8)
        if st.session_state.history:
            st.markdown('<div class="sbsec"><div class="sbtitle">📜 History</div>', unsafe_allow_html=True)
            search_kw = st.text_input("Search history", placeholder="filter…", label_visibility="collapsed")
            hist_show = (logger.search_history(search_kw) if search_kw
                         else st.session_state.history[-8:])
            for item in reversed(hist_show[-8:]):
                dot  = "ds" if item.get("success") else "df"
                short= item.get("question","")[:44] + ("…" if len(item.get("question","")) > 44 else "")
                st.markdown(f"""
                <div class="hcard">
                  <div class="hq">{short}</div>
                  <div class="hmeta">
                    <span class="{dot}"></span>
                    <span style="font-size:.7rem;color:#5A6478">{len(item.get('attempts',[]))} att · {item.get('total_time_ms',0):.0f}ms</span>
                  </div>
                </div>""", unsafe_allow_html=True)
            if st.button("🗑 Clear History"):
                st.session_state.history.clear()
                st.session_state.logger.clear()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── HERO ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero">
      <div class="hero-title">
        <span class="ht-icon">🤖</span>
        <span class="ht-plain">LLM-Powered&nbsp;</span><span class="ht-accent">SQL Agent</span>
      </div>
      <div class="hero-sub">Natural language → SQL → Execute → Auto-correct — zero manual intervention</div>
      <div class="hero-badges">
        <span class="badge b1">GPT / Mistral-7B</span>
        <span class="badge b2">Self-Correcting Loop</span>
        <span class="badge b3">sqlglot Validation</span>
        <span class="badge b4">Read-Only Safety</span>
        <span class="badge b5">Spider Benchmark</span>
      </div>
    </div>""", unsafe_allow_html=True)

    stats = logger.get_stats()
    metric_cards(stats)

    # ── TABS ──────────────────────────────────────────────────────────────────
    t_query, t_analytics, t_schema, t_benchmark = st.tabs(
        ["🔍 Query", "📊 Analytics", "🗄️ Schema Explorer", "🏆 Benchmark"]
    )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — QUERY
    # ════════════════════════════════════════════════════════════════════════
    with t_query:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        c_inp, c_samp = st.columns([3, 1])
        with c_inp:
            user_q = st.text_area(
                "Question", height=88, key="user_q",
                placeholder="Ask anything about the database…",
                label_visibility="collapsed",
            )
        with c_samp:
            st.markdown("<br>", unsafe_allow_html=True)
            pick = st.selectbox("Samples", ["— pick —"]+SAMPLES,
                                label_visibility="collapsed", key="sample_pick")
            if pick != "— pick —":
                user_q = pick
                st.session_state["user_q"] = pick

        c_run, c_clr, _ = st.columns([1, 1, 5])
        run_btn = c_run.button("▶ Run", use_container_width=True)
        if c_clr.button("✕ Clear", use_container_width=True):
            st.session_state["user_q"] = ""
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # Pipeline steps
        st.markdown("""
        <div class="pipe">
          <div class="pstep"><div class="picon">📐</div><div class="plbl">Schema<br>Inject</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">🧠</div><div class="plbl">CoT<br>Reason</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">✍️</div><div class="plbl">Gen<br>SQL</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">🔍</div><div class="plbl">Syntax<br>Check</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">⚡</div><div class="plbl">Execute<br>SQL</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">🔄</div><div class="plbl">Auto<br>Correct</div></div>
          <div class="parr">→</div>
          <div class="pstep"><div class="picon">💡</div><div class="plbl">Explain<br>Result</div></div>
        </div>""", unsafe_allow_html=True)

        if run_btn and user_q and user_q.strip():
            question = user_q.strip()

            # API key guard
            if not model_choice.startswith("ollama:") and not os.getenv("OPENAI_API_KEY","").startswith("sk-"):
                st.error("⚠️ Enter a valid OpenAI API key in the sidebar.", icon="🔑")
                st.stop()

            status_ph  = st.empty()
            stream_ph  = st.empty()
            stream_buf = []

            # Streaming callback (#7)
            def on_token(tok: str):
                stream_buf.append(tok)
                preview = "".join(stream_buf)
                stream_ph.markdown(
                    f'<div class="streambox">{_hl(preview)}'
                    f'<span class="cursor"></span></div>',
                    unsafe_allow_html=True
                )

            status_ph.markdown(
                '<div style="background:rgba(59,130,246,.07);border:1px solid rgba(59,130,246,.18);'
                'border-radius:9px;padding:12px 16px;color:#93c5fd;font-size:.86rem;">'
                '⚙️ Schema injected → generating SQL…</div>',
                unsafe_allow_html=True
            )

            with st.spinner(f"Agent working… ({model_choice})"):
                res = run_agent(
                    question=question,
                    model=model_choice,
                    logger=logger,
                    stream_callback=on_token if enable_stream else None,
                    explain=enable_explain,
                )

            status_ph.empty()
            stream_ph.empty()

            res["question"] = question
            st.session_state.history.append(res)
            st.session_state.last_result = res

            # Status banner
            n_att = len(res["attempts"])
            if res["success"]:
                cot_tag = ' · <span style="color:#F0A500">🧠 CoT used</span>' if res.get("used_cot") else ""
                cache_tag= ' · <span style="color:#F0A500">⚡ cache hit</span>' if res.get("from_cache") else ""
                st.markdown(f"""
                <div class="sucbanner">
                  <span style="font-size:1.7rem">✅</span>
                  <div>
                    <div style="font-weight:700;color:#00C896">Query Successful</div>
                    <div style="color:#A8B5C8;font-size:.82rem">
                      {n_att} attempt(s) · {res['total_time_ms']:.0f}ms
                      · {res['dataframe'].shape[0] if res['dataframe'] is not None else 0} rows
                      {cot_tag}{cache_tag}
                    </div>
                  </div>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="failbanner">
                  <span style="font-size:1.7rem">❌</span>
                  <div>
                    <div style="font-weight:700;color:#FF4D6A">Failed after {n_att} attempt(s)</div>
                    <div style="color:#A8B5C8;font-size:.82rem">Try rephrasing or switching model.</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Correction chain
            with st.expander("🔗 Correction Chain", expanded=True):
                render_chain(res["attempts"])

            # ── SQL Editor (#9) ───────────────────────────────────────────────
            if res.get("final_sql"):
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="editor-label">✏️ Edit & Re-Run SQL</div>', unsafe_allow_html=True)
                edited_sql = st.text_area(
                    "edit_sql", value=res["final_sql"],
                    height=110, key="edit_sql",
                    label_visibility="collapsed",
                )
                c_rerun, c_reset, _ = st.columns([1,1,5])
                if c_rerun.button("▶ Execute Edited SQL"):
                    from db_executor import execute_sql as _exec
                    r2 = _exec(edited_sql)
                    if r2.success:
                        st.success(f"✅ {r2.row_count} rows · {r2.execution_time_ms:.1f}ms")
                        st.dataframe(r2.dataframe, use_container_width=True, hide_index=True)
                        auto_chart(r2.dataframe, question)
                        csv = r2.dataframe.to_csv(index=False)
                        st.download_button("⬇ Download CSV", csv, "result.csv", "text/csv")
                    else:
                        st.error(f"❌ {r2.error}")
                if c_reset.button("↩ Reset SQL"):
                    st.session_state["edit_sql"] = res["final_sql"]
                    st.rerun()

            # Results table
            if res["success"] and res["dataframe"] is not None:
                df = res["dataframe"]
                st.markdown('<div class="res-sec">', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="res-hdr">
                  <span style="font-weight:700;font-size:1rem">📊 Results</span>
                  <span class="rbdg">{len(df)} rows</span>
                  <span class="tbdg">⏱ {res['total_time_ms']:.0f}ms</span>
                </div>""", unsafe_allow_html=True)

                st.dataframe(df, use_container_width=True, hide_index=True)
                auto_chart(df, question)

                # Plain-English explanation (#10)
                if res.get("explanation"):
                    st.markdown(f"""
                    <div class="explainbox">
                      <div class="explainbox-title">💡 What this means</div>
                      {res['explanation']}
                    </div>""", unsafe_allow_html=True)

                csv = df.to_csv(index=False)
                st.download_button("⬇ Download CSV", csv, "result.csv", "text/csv")
                st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — ANALYTICS
    # ════════════════════════════════════════════════════════════════════════
    with t_analytics:
        if not st.session_state.history:
            st.markdown("""
            <div style="text-align:center;padding:70px 20px;color:#475569">
              <div style="font-size:3rem;margin-bottom:14px">📊</div>
              <div style="font-size:1.05rem">Run some queries to see analytics</div>
            </div>""", unsafe_allow_html=True)
        else:
            h = st.session_state.history
            s = logger.get_stats()
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🎯 Performance Radar")
                st.plotly_chart(radar(s), use_container_width=True)
            with c2:
                st.markdown("#### 📈 Attempts per Query")
                b = attempts_bar(h)
                if b: st.plotly_chart(b, use_container_width=True)

            st.markdown("#### 🌐 3D Query Space")
            sc = scatter_3d(h)
            if sc:
                st.plotly_chart(sc, use_container_width=True)
            else:
                st.info("Run at least 3 queries to unlock the 3D view.")

            # Error type breakdown
            all_attempts = [a for r in h for a in r.get("attempts",[])]
            failed = [a for a in all_attempts if not a["success"]]
            if failed:
                st.markdown("#### 🔍 Error Type Breakdown")
                from collections import Counter
                ct = Counter(a.get("error_type","general") for a in failed)
                fig = px.pie(
                    values=list(ct.values()), names=list(ct.keys()),
                    color_discrete_sequence=["#FF4D6A","#F0A500","#00C896","#A8B5C8","#5A6478"],
                    hole=.45,
                )
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',font=dict(color='#EAEDF2'),
                                  margin=dict(l=0,r=0,t=10,b=0),height=240)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### 📋 Session Log")
            rows = [{
                "Question": r.get("question","")[:55],
                "✓": "✅" if r.get("success") else "❌",
                "Attempts": len(r.get("attempts",[])),
                "Time(ms)": round(r.get("total_time_ms",0)),
                "Rows": r["dataframe"].shape[0] if r.get("dataframe") is not None else 0,
                "CoT": "🧠" if r.get("used_cot") else "",
                "Cache": "⚡" if r.get("from_cache") else "",
            } for r in h]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — SCHEMA EXPLORER
    # ════════════════════════════════════════════════════════════════════════
    with t_schema:
        st.markdown("## 🗄️ Schema Explorer")
        c1, c2 = st.columns([5, 4])
        with c1:
            st.code(get_schema(), language="sql")
        with c2:
            sd = get_schema_dict()
            tbl = st.selectbox("Browse table", list(sd.keys()))
            if tbl:
                r = execute_sql(f"SELECT * FROM {tbl} LIMIT 25")
                if r.success:
                    st.dataframe(r.dataframe, use_container_width=True, hide_index=True)

            # Entity diagram
            tables = list(sd.keys())
            n = len(tables)
            cx = [math.cos(2*math.pi*i/n)*2.2 for i in range(n)]
            cy = [math.sin(2*math.pi*i/n)*2.2 for i in range(n)]
            fig = go.Figure()
            for i, t in enumerate(tables):
                fig.add_trace(go.Scatter(
                    x=[cx[i]], y=[cy[i]], mode='markers+text',
                    marker=dict(size=44,color='rgba(0,200,150,.12)',
                                line=dict(color='#00C896',width=1.5)),
                    text=[t], textposition='middle center',
                    textfont=dict(size=10,color='#EAEDF2'), hoverinfo='skip',
                ))
            fig.update_layout(
                showlegend=False,paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(visible=False),yaxis=dict(visible=False),
                height=260,margin=dict(l=0,r=0,t=10,b=0),
                title=dict(text="Tables",font=dict(color='#5A6478',size=11)),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Quick-query the table
            st.markdown("#### ⚡ Quick Custom Query")
            qsql = st.text_area("SQL", value=f"SELECT * FROM {tbl} LIMIT 10",
                                height=70, key="schema_qsql", label_visibility="collapsed")
            if st.button("Run", key="schema_run"):
                qr = execute_sql(qsql)
                if qr.success:
                    st.dataframe(qr.dataframe, use_container_width=True, hide_index=True)
                else:
                    st.error(qr.error)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 4 — BENCHMARK
    # ════════════════════════════════════════════════════════════════════════
    with t_benchmark:
        st.markdown("## 🏆 Spider-Style Benchmark")
        st.markdown("""
        <div style="background:rgba(59,130,246,.07);border:1px solid rgba(59,130,246,.14);
             border-radius:10px;padding:12px 16px;color:#93c5fd;font-size:.85rem;margin-bottom:18px">
          Runs curated NL-to-SQL queries and measures first-try rate, final success rate,
          avg correction attempts, and per-difficulty breakdown — mirrors Spider benchmark methodology.
        </div>""", unsafe_allow_html=True)

        from eval.spider_eval import BENCHMARK_QUERIES
        c1,c2,c3 = st.columns(3)
        max_n      = c1.slider("Queries", 5, 20, 10, key="bn")
        bench_model= c2.selectbox("Model", ["gpt-3.5-turbo","gpt-4o-mini","ollama:mistral","ollama:codellama"], key="bm")
        c3.markdown("<br>", unsafe_allow_html=True)
        run_bench  = c3.button("▶ Run Benchmark", use_container_width=True)

        preview_df = pd.DataFrame(BENCHMARK_QUERIES[:max_n])[["id","difficulty","question"]]
        preview_df.columns = ["#","Difficulty","Question"]
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        if run_bench:
            if not bench_model.startswith("ollama:") and not os.getenv("OPENAI_API_KEY","").startswith("sk-"):
                st.error("⚠️ Enter a valid OpenAI API key in the sidebar.", icon="🔑")
                st.stop()

            bph  = st.empty()
            prog = st.progress(0)
            rows = []
            for idx, q in enumerate(BENCHMARK_QUERIES[:max_n]):
                bph.markdown(
                    f'<div style="color:#93c5fd;font-size:.88rem">⚙️ [{idx+1}/{max_n}] {q["question"][:65]}…</div>',
                    unsafe_allow_html=True
                )
                try:
                    r = run_agent(q["question"], model=bench_model, logger=logger, explain=False)
                    rows.append({
                        "#": q["id"], "Difficulty": q["difficulty"],
                        "Question": q["question"][:55],
                        "✓": "✅" if r["success"] else "❌",
                        "Attempts": len(r["attempts"]),
                        "Time(ms)": round(r["total_time_ms"]),
                        "CoT": "🧠" if r.get("used_cot") else "",
                    })
                except Exception as e:
                    rows.append({"#":q["id"],"Difficulty":q["difficulty"],
                                 "Question":q["question"][:55],"✓":"❌","Attempts":0,"Time(ms)":0,"CoT":""})
                prog.progress((idx+1)/max_n)

            bph.empty()
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            total   = len(rows)
            succ    = sum(1 for r in rows if r["✓"]=="✅")
            first_t = sum(1 for r in rows if r["✓"]=="✅" and r["Attempts"]==1)
            avg_att = sum(r["Attempts"] for r in rows)/total if total else 0

            m1,m2,m3,m4 = st.columns(4)
            for col,(lbl,val,tgt,good) in zip([m1,m2,m3,m4],[
                ("Total",   str(total),                  "",        True),
                ("Success", f"{succ/total*100:.0f}%",    ">87%",    succ/total>=.87),
                ("1st Try", f"{first_t/total*100:.0f}%", ">60%",    first_t/total>=.60),
                ("Avg Att", f"{avg_att:.2f}",            "<1.5",    avg_att<1.5),
            ]):
                clr = "#00C896" if good else "#FF4D6A"
                col.markdown(f"""
                <div class="mc" style="text-align:center">
                  <div class="mc-val" style="color:{clr}">{val}</div>
                  <div class="mc-lbl">{lbl}</div>
                  <div style="font-size:.7rem;color:#5A6478">{tgt}</div>
                </div>""", unsafe_allow_html=True)

            # Difficulty breakdown
            from collections import defaultdict
            dd = defaultdict(lambda: {"t":0,"s":0})
            for r in rows:
                dd[r["Difficulty"]]["t"] += 1
                if r["✓"] == "✅": dd[r["Difficulty"]]["s"] += 1
            if dd:
                fig = px.bar(
                    pd.DataFrame([{"Difficulty":d,"Success Rate %":round(v["s"]/v["t"]*100,1)}
                                  for d,v in dd.items()]),
                    x="Difficulty", y="Success Rate %",
                    color="Difficulty",
                    color_discrete_map={"easy":"#00C896","medium":"#F0A500","hard":"#FF4D6A"},
                    title="Success Rate by Difficulty",
                )
                fig.add_hline(y=87,line_dash="dash",line_color="#5A6478",
                              annotation_text="target 87%",
                              annotation_font_color="#A8B5C8")
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                                  font=dict(color='#EAEDF2'),showlegend=False,
                                  xaxis=dict(gridcolor='rgba(255,255,255,.05)'),
                                  yaxis=dict(gridcolor='rgba(255,255,255,.05)'))
                st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
