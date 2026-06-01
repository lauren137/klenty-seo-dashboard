"""Asana-inspired CSS for the Streamlit dashboard."""

ASANA_CSS = """
<style>
/* ---- Reset Streamlit chrome ---- */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

/* Keep the header bar visible so the sidebar toggle works.
   Just make it transparent so it doesn't visually clash. */
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 2.5rem;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}

/* ---- Asana palette ---- */
:root {
    --asana-coral: #F06A6A;
    --asana-coral-hover: #E25555;
    --asana-coral-soft: #FCE9E9;
    --asana-bg: #F6F7F8;
    --asana-card: #FFFFFF;
    --asana-border: #EDEDED;
    --asana-text: #1E1F21;
    --asana-text-muted: #6F7782;
    --asana-green: #14A37F;
    --asana-red: #E8384F;
    --asana-blue: #4573D2;
}

html, body, .stApp {
    background: var(--asana-bg) !important;
    color: var(--asana-text) !important;
    color-scheme: light !important;
}

body, .stApp {
    font-family: -apple-system, "Helvetica Neue", "Segoe UI", Roboto, sans-serif;
}

/* Keep Material icon fonts intact (expander arrows, etc.) */
[data-testid="stExpanderToggleIcon"],
[data-testid="stIconMaterial"],
.material-icons,
.material-symbols-rounded,
.material-symbols-outlined,
span[class*="material"],
span[class*="Material"],
span[class*="icon"] {
    font-family: "Material Symbols Rounded", "Material Icons", "Material Symbols Outlined", sans-serif !important;
}

/* ---- Force light text on light bg everywhere ---- */
.stApp p, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
    color: var(--asana-text);
}
.stMarkdown, .stMarkdown p { color: var(--asana-text) !important; }

/* ---- Sidebar text must be readable ---- */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--asana-text) !important;
}

/* ---- Expander header: prevent label/icon overlap ---- */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
[data-testid="stExpander"] summary {
    padding: 0.4rem 0.6rem !important;
}
[data-testid="stExpander"] summary > div {
    display: flex !important;
    align-items: center !important;
    gap: 0.5rem !important;
    width: 100%;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--asana-text) !important;
    font-weight: 600 !important;
}

/* ---- Data table: light theme ---- */
.stDataFrame, .stDataFrame * {
    color: var(--asana-text) !important;
}
.stDataFrame [data-testid="stDataFrameResizable"] {
    background: white !important;
}
div[data-testid="stDataFrame"] {
    background: white !important;
}
div[data-testid="stDataFrame"] table {
    background: white !important;
}
div[data-testid="stDataFrame"] thead tr th {
    background: #FAFAFB !important;
    color: var(--asana-text-muted) !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
}
div[data-testid="stDataFrame"] tbody tr td {
    background: white !important;
    color: var(--asana-text) !important;
    border-bottom: 1px solid var(--asana-border) !important;
}
div[data-testid="stDataFrame"] tbody tr:hover td {
    background: #FAFAFB !important;
}

/* ---- Selectbox + text input: light ---- */
.stSelectbox div[data-baseweb="select"] > div {
    background: white !important;
    color: var(--asana-text) !important;
    border-color: var(--asana-border) !important;
}
.stTextInput input {
    background: white !important;
    color: var(--asana-text) !important;
}

/* ---- Header bar ---- */
.dash-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0 1.25rem 0;
    border-bottom: 1px solid var(--asana-border);
    margin-bottom: 1.5rem;
}
.dash-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: -0.02em;
}
.dash-logo {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--asana-coral) 0%, #F89A9A 100%);
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 1rem;
}
.dash-subtitle {
    color: var(--asana-text-muted);
    font-size: 0.85rem;
    margin-top: 2px;
}

/* ---- Summary cards ---- */
.metric-card {
    background: var(--asana-card);
    border: 1px solid var(--asana-border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.metric-label {
    color: var(--asana-text-muted);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.35rem;
}
.metric-value {
    font-size: 1.75rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.metric-delta {
    font-size: 0.8rem;
    margin-top: 0.25rem;
}
.delta-up { color: var(--asana-green); }
.delta-down { color: var(--asana-red); }
.delta-flat { color: var(--asana-text-muted); }

/* ---- Buttons ---- */
.stButton > button {
    background: var(--asana-coral) !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    padding: 0.4rem 1rem !important;
    transition: background 0.15s ease !important;
}
.stButton > button:hover {
    background: var(--asana-coral-hover) !important;
}
.stButton > button[kind="secondary"] {
    background: white !important;
    color: var(--asana-text) !important;
    border: 1px solid var(--asana-border) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: #FAFAFB !important;
    border-color: #D8D9DC !important;
}

/* ---- Time-range pills (radio styled) ---- */
div[role="radiogroup"] {
    gap: 0.4rem !important;
    flex-wrap: wrap;
}
div[role="radiogroup"] > label {
    background: white;
    border: 1px solid var(--asana-border);
    border-radius: 999px;
    padding: 0.35rem 0.9rem !important;
    cursor: pointer;
    transition: all 0.15s ease;
    font-size: 0.85rem !important;
    color: var(--asana-text-muted);
}
div[role="radiogroup"] > label:hover {
    border-color: var(--asana-coral);
    color: var(--asana-text);
}
div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}
div[role="radiogroup"] > label[data-baseweb="radio"]:has(input:checked) {
    background: var(--asana-coral) !important;
    color: white !important;
    border-color: var(--asana-coral) !important;
    font-weight: 500;
}

/* ---- Data table ---- */
.stDataFrame {
    border: 1px solid var(--asana-border);
    border-radius: 10px;
    overflow: hidden;
    background: white;
}

/* ---- Section headers ---- */
.section-title {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--asana-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 1.5rem 0 0.75rem 0;
}

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid var(--asana-border);
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 0;
    padding: 0.6rem 1rem;
    color: var(--asana-text-muted);
    font-size: 0.9rem;
    font-weight: 500;
}
.stTabs [aria-selected="true"] {
    color: var(--asana-coral) !important;
    border-bottom: 2px solid var(--asana-coral) !important;
}

/* ---- Inputs ---- */
input[type="text"], .stTextInput input, .stSelectbox > div > div {
    border-radius: 6px !important;
    border-color: var(--asana-border) !important;
}

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: white;
    border-right: 1px solid var(--asana-border);
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 2rem;
}

/* ---- Status pills ---- */
.pill {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 500;
}
.pill-good { background: #E6F4F0; color: var(--asana-green); }
.pill-warn { background: #FFF4E5; color: #B25E09; }
.pill-bad  { background: #FBE7EA; color: var(--asana-red); }

/* ---- Footer note ---- */
.footnote {
    color: var(--asana-text-muted);
    font-size: 0.75rem;
    margin-top: 2rem;
    text-align: center;
}
</style>
"""
