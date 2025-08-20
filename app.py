\
import streamlit as st
import pandas as pd
from dateutil.relativedelta import relativedelta
from datetime import date

st.set_page_config(page_title="Прогресс накопления", layout="wide")

GOAL_AMOUNT = 426_000
GOAL_DEADLINE = date(2025, 11, 1)
GOAL_TITLE = "Прогресс накопления на первый взнос"

COLS_NUMERIC = ["income","expenses","installments","autoloan","savings","debt_return"]

@st.cache_data
def load_data():
    plans = pd.read_csv("plans.csv", parse_dates=["month"], dayfirst=True)
    plans["month"] = plans["month"].dt.to_period("M").dt.to_timestamp()
    for c in COLS_NUMERIC:
        if c not in plans.columns:
            plans[c] = 0
    if "comment" not in plans.columns:
        plans["comment"] = ""
    return plans.sort_values("month")

def recalc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["balance"] = (
        df["income"]
        - df["expenses"]
        - df["installments"]
        - df["autoloan"]
        + df["debt_return"]
        - df["savings"]
    )
    df["total_saved"] = df["savings"].cumsum()
    return df

def save_plans(df: pd.DataFrame):
    # сохраняем с форматом даты DD-MM-YYYY (1-е число каждого месяца)
    tmp = df.copy()
    tmp["month"] = tmp["month"].dt.strftime("%d-%m-%Y")
    tmp.to_csv("plans.csv", index=False)

# ---------- LOAD ----------
plans = recalc(load_data())

# ---------- HEADER ----------
today = date.today().replace(day=1)
accumulated = float(plans.loc[plans["month"] <= pd.Timestamp(today), "savings"].sum())
remaining = GOAL_AMOUNT - accumulated
planned_future = float(plans.loc[(plans["month"] > pd.Timestamp(today)) & (plans["month"] <= pd.Timestamp(GOAL_DEADLINE)), "savings"].sum())
loan_needed = max(0, GOAL_AMOUNT - (accumulated + planned_future))

st.markdown(f"## 🎯 {GOAL_TITLE}")
col1, col2, col3 = st.columns([2,1,1])
with col1:
    st.metric("Цель", f"{GOAL_AMOUNT:,.0f} ₽".replace(",", " "))
    prog = max(0, min(1, accumulated / GOAL_AMOUNT if GOAL_AMOUNT else 0))
    st.progress(prog, text=f"{int(prog*100)}% ({int(accumulated):,} ₽)".replace(",", " "))
with col2:
    st.metric("Накоплено", f"{int(accumulated):,} ₽".replace(",", " "))
with col3:
    st.metric("Осталось", f"{max(0,int(remaining)):,} ₽".replace(",", " "))

if loan_needed > 0:
    st.warning(f"⚠️ До {GOAL_DEADLINE.strftime('%b %Y')} не хватает ~{int(loan_needed):,} ₽", icon="⚠️")

st.divider()

# ---------- SIDEBAR FORM ----------
st.sidebar.header("➕ Добавить операцию")
with st.sidebar.form("add_op_form", clear_on_submit=True):
    # список месяцев из плана + опция "Новый месяц"
    month_options = list(plans["month"].dt.strftime("%m.%Y").unique())
    month_choice = st.selectbox("Месяц", options=month_options + ["Новый месяц..."])

    if month_choice == "Новый месяц...":
        new_month = st.date_input("Выбери новую дату (любое число месяца)", value=pd.Timestamp(today))
        target_month = pd.to_datetime(new_month).to_period("M").to_timestamp()
    else:
        target_month = pd.to_datetime("01-" + month_choice, dayfirst=True)

    op_type = st.selectbox(
        "Тип операции",
        options=[
            ("Доход", "income"),
            ("Расход", "expenses"),
            ("Рассрочка", "installments"),
            ("Автокредит", "autoloan"),
            ("Накопление", "savings"),
            ("Возврат долга", "debt_return"),
        ],
        format_func=lambda x: x[0]
    )
    amount = st.number_input("Сумма, ₽", min_value=0, step=1000, value=10000)
    comment_add = st.text_input("Комментарий (опционально)", "")

    submitted = st.form_submit_button("Добавить")

    if submitted:
        col_key = op_type[1]
        df = plans.copy()

        if (df["month"] == target_month).any():
            idx = df.index[df["month"] == target_month][0]
            df.loc[idx, col_key] = float(df.loc[idx, col_key]) + float(amount)
            if comment_add:
                base = str(df.loc[idx, "comment"]) if pd.notna(df.loc[idx, "comment"]) else ""
                glue = " | " if base else ""
                df.loc[idx, "comment"] = f"{base}{glue}+{op_type[0]}: {int(amount)}₽ ({comment_add})"
        else:
            row = {c:0 for c in COLS_NUMERIC}
            row[col_key] = float(amount)
            df = pd.concat([df, pd.DataFrame([{
                "month": target_month,
                **row,
                "comment": f"+{op_type[0]}: {int(amount)}₽ ({comment_add})" if comment_add else f"+{op_type[0]}: {int(amount)}₽"
            }])], ignore_index=True)

        df = df.sort_values("month")
        df = recalc(df)
        save_plans(df)
        st.success("Операция добавлена и сохранена в plans.csv")
        st.experimental_rerun()

# ---------- YEAR TABS ----------
min_year = plans["month"].dt.year.min()
max_year = plans["month"].dt.year.max()
years = list(range(min_year, max_year + 1))
tabs = st.tabs([str(y) for y in years])

for i, y in enumerate(years):
    with tabs[i]:
        df_year = plans[plans["month"].dt.year == y].copy()
        if df_year.empty:
            st.info("Нет данных за этот год.")
            continue
        show = df_year.assign(
            Месяц=lambda d: d["month"].dt.strftime("%b %Y"),
            Доходы=lambda d: d["income"],
            Расходы=lambda d: d["expenses"],
            Рассрочки=lambda d: d["installments"],
            Автокредит=lambda d: d["autoloan"],
            Накопления=lambda d: d["savings"],
            Возврат_долгов=lambda d: d["debt_return"],
            Баланс=lambda d: d["balance"],
            Всего_накоплено=lambda d: d["total_saved"],
            Комментарий=lambda d: d.get("comment","")
        )[["Месяц","Доходы","Расходы","Рассрочки","Автокредит","Накопления","Возврат_долгов","Баланс","Всего_накоплено","Комментарий"]]
        st.dataframe(
            show.style.format({
                "Доходы":"{:,.0f}".format,
                "Расходы":"{:,.0f}".format,
                "Рассрочки":"{:,.0f}".format,
                "Автокредит":"{:,.0f}".format,
                "Накопления":"{:,.0f}".format,
                "Возврат_долгов":"{:,.0f}".format,
                "Баланс":"{:,.0f}".format,
                "Всего_накоплено":"{:,.0f}".format,
            }),
            use_container_width=True,
            hide_index=True
        )
