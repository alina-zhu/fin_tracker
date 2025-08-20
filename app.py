import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="Tracker", page_icon="📊", layout="wide")

# -------------------------- DATA LOADER --------------------------
@st.cache_data
def load_local_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return normalize_df(df)

@st.cache_data
def make_demo_df(n=800, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=220, freq="D")
    df = pd.DataFrame({
        "date": np.random.choice(dates, n),
        "region": rng.choice(["EU","US","LATAM","APAC"], n, p=[0.4,0.25,0.2,0.15]),
        "product": rng.choice(["Web","iOS","Android"], n, p=[0.5,0.25,0.25]),
        "value": np.round(rng.normal(100, 25, n)).clip(5),
        "converted": rng.choice([0,1], n, p=[0.8,0.2])
    }).sort_values("date")
    return normalize_df(df)

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Приводим к ожидаемым колонкам: date, region, product, value, converted."""
    cols = {c.lower(): c for c in df.columns}
    def find(col):
        return next((c for c in df.columns if c.lower() == col), None)

    rename = {}
    for want in ["date", "region", "product", "value", "converted"]:
        cand = find(want)
        if cand and cand != want:
            rename[cand] = want
    df = df.rename(columns=rename).copy()

    # обязательные колонки
    if "date" not in df: df["date"] = pd.Timestamp.today().normalize()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    for col, fill in [("region","NA"),("product","NA"),("value",0.0),("converted",0)]:
        if col not in df: df[col] = fill

    # типы
    df["region"]   = df["region"].astype(str)
    df["product"]  = df["product"].astype(str)
    df["value"]    = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    df["converted"]= pd.to_numeric(df["converted"], errors="coerce").fillna(0).astype(int)

    return df.sort_values("date").reset_index(drop=True)

# -------------------------- SIDEBAR --------------------------
st.sidebar.title("⚙️ Настройки")

data_source = st.sidebar.radio(
    "Источник данных",
    ["Demo data", "Upload CSV", "Repo CSV (data/sample_metrics.csv)"],
    index=0
)

if data_source == "Upload CSV":
    up = st.sidebar.file_uploader("Загрузите CSV", type=["csv"])
    if up is not None:
        df = normalize_df(pd.read_csv(up))
    else:
        st.sidebar.info("Пока файл не загружен — используем демо.")
        df = make_demo_df()
elif data_source == "Repo CSV (data/sample_metrics.csv)":
    try:
        df = load_local_csv("data/sample_metrics.csv")
    except Exception as e:
        st.sidebar.error(f"Не удалось прочитать data/sample_metrics.csv: {e}")
        df = make_demo_df()
else:
    df = make_demo_df()

# Фильтры
all_regions  = sorted(df["region"].unique())
all_products = sorted(df["product"].unique())

regions = st.sidebar.multiselect("Region", all_regions, default=all_regions)
products = st.sidebar.multiselect("Product", all_products, default=all_products)

period = st.sidebar.selectbox("Aggregation period", ["D","W-MON","MS"], index=1)
metric = st.sidebar.selectbox(
    "Metric",
    [("Mean value","mean_value"), ("Sum value","sum_value"), ("Conversion (mean converted)","mean_converted")],
    index=0, format_func=lambda x: x[0]
)[1]

group_by = st.sidebar.multiselect(
    "Group by (legend)",
    options=["region","product"],
    default=["region"]
)

dmin, dmax = df["date"].min().date(), df["date"].max().date()
d0, d1 = st.sidebar.date_input("Date range", (dmin, dmax))
if isinstance(d0, tuple) or isinstance(d1, tuple):
    # На случай старого поведения streamlit
    d0, d1 = dmin, dmax

st.sidebar.caption("Подсказка: для недель используем понедельник как старт (W-MON).")

# -------------------------- FILTERING --------------------------
q = df[(df["region"].isin(regions)) & (df["product"].isin(products))]
q = q[(q["date"] >= pd.Timestamp(d0)) & (q["date"] <= pd.Timestamp(d1))]

st.caption(f"Отфильтровано строк: **{len(q):,}**")

if q.empty:
    st.warning("Нет данных под выбранные фильтры.")
    st.stop()

# -------------------------- AGGREGATION --------------------------
q = q.set_index("date").sort_index()
# важно: без .dt; берем start времени периода
q["_period"] = q.index.to_period(period).to_timestamp(how="start")

agg_keys = (group_by or []) + ["_period"]

agg = (
    q.groupby(agg_keys)
     .agg(
        mean_value=("value","mean"),
        sum_value=("value","sum"),
        mean_converted=("converted","mean")
     )
     .reset_index()
)

# -------------------------- UI --------------------------
st.title("📊 Tracker")

# график
left, right = st.columns((2,1), gap="large")

with left:
    color = group_by[0] if group_by else None
    ylab = {"mean_value":"Mean value", "sum_value":"Sum value", "mean_converted":"Conversion"}[metric]
    fig = px.line(
        agg, x="_period", y=metric, color=color, markers=True,
        title=f"{ylab} by {period}" + (f" ({', '.join(group_by)})" if group_by else "")
    )
    fig.update_layout(legend_title_text="")
    fig.update_xaxes(title="Period")
    if metric == "mean_converted":
        fig.update_yaxes(title=ylab, tickformat=".2%")
    else:
        fig.update_yaxes(title=ylab)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Latest by group")
    latest = (
        agg.sort_values("_period")
           .groupby(group_by or ["_dummy"], dropna=False)
           .tail(1)
           .drop(columns=["_period"])
    )
    if "_dummy" in latest.columns:
        latest = latest.drop(columns=["_dummy"])
    st.dataframe(
        latest.style.format({
            "mean_value": "{:,.2f}",
            "sum_value": "{:,.0f}",
            "mean_converted": "{:.2%}"
        }),
        use_container_width=True
    )

with st.expander("🔎 Raw aggregated data"):
    st.dataframe(agg, use_container_width=True)

# -------------------------- FOOTER --------------------------
st.caption(
    "Tip: положите свой CSV в `data/sample_metrics.csv` (колонки: date, region, product, value, converted) "
    "или используйте загрузку файла в сайдбаре."
)
