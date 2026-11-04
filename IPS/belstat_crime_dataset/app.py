import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

# Set page config for a nice look
st.set_page_config(page_title="Belstat Crime Data", layout="wide")

st.title("📊 Belstat Crime Dataset Explorer")

# Database connection
DB_PATH = "./belstat_crime_dataset/data/belstat_crime.sqlite"

@st.cache_data
def get_data(query):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Sidebar filters
st.sidebar.header("Фильтры")

# Get territories using name_ru
territories_df = get_data("SELECT name_ru FROM territories")
selected_territory = st.sidebar.selectbox("Выберите регион:", territories_df['name_ru'].unique())

# Get indicators using name_ru
indicators_df = get_data("SELECT name_ru FROM indicators")
selected_indicator = st.sidebar.selectbox("Выберите показатель:", indicators_df['name_ru'].unique())

# Main content
st.header(f"Анализ: {selected_indicator}")
st.subheader(f"Регион: {selected_territory}")

# Query facts based on selections using actual column names
query = f"""
SELECT f.value, f.time_period 
FROM facts f
WHERE f.geo_name_ru = '{selected_territory}' AND f.indicator_name_ru = '{selected_indicator}'
ORDER BY f.time_period
"""

try:
    df = get_data(query)
    if not df.empty:
        fig = px.line(df, x='time_period', y='value', title=f"Динамика по {selected_indicator}")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df)
    else:
        st.warning("Данные не найдены для выбранной комбинации.")
except Exception as e:
    st.error(f"Ошибка при загрузке данных: {e}")
