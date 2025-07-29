
import streamlit as st
import pandas as pd
import plotly.express as px
from prophet import Prophet
import requests
from datetime import datetime, timedelta

# --------------------------
st.set_page_config(page_title="US Electricity Market Dashboard", layout="wide")
st.title("⚡ Electricity Market Analytics")
st.markdown("Live load, renewables, congestion & intertie metrics from EIA")

# --------------------------
# Default to CISO (California ISO) if nothing selected
ba_dict = {
    "CISO": "California ISO",
    "ERCO": "ERCOT (Texas)",
    "ISNE": "ISO New England",
    "MISO": "Midcontinent ISO",
    "NYIS": "NYISO",
    "PJM": "PJM Interconnection",
    "SPP": "Southwest Power Pool",
    "BPAT": "Bonneville Power",
    "PACW": "PacifiCorp West",
    "SEPA": "Southeast Power Admin"
}
selected_ba = st.selectbox("Select Balancing Authority", list(ba_dict.keys()), index=0, format_func=lambda x: ba_dict[x])

# --------------------------
# Rolling 7-day EIA v2 fetch
def fetch_eia_v2_hourly_series(respondent: str, metric: str, api_key: str):
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    st.caption(f"🔄 Data range: {start_str} to {end_str}")

    metric_map = {
        "demand": "D",
        "net_generation": "NG",
        "wind": "NG.WND",
        "solar": "NG.SUN",
        "net_interchange": "NI",
        "lmp_da": "LMP_DA",
        "lmp_rt": "LMP_RT"
    }
    if metric not in metric_map:
        st.error(f"Unsupported metric: {metric}")
        return pd.DataFrame()

    url = (
        f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
        f"?frequency=hourly&data[0]=value"
        f"&facets[respondent][]={respondent}"
        f"&facets[type][]=ALL"
        f"&facets[metric][]={metric_map[metric]}"
        f"&start={start_str}T00"
        f"&end={end_str}T23"
        f"&sort[0][column]=period"
        f"&sort[0][direction]=asc"
        f"&api_key={api_key}"
    )

    r = requests.get(url)
    if r.status_code != 200:
        st.warning(f"EIA v2 API call failed for {respondent} - {metric}")
        return pd.DataFrame()

    data = r.json().get("response", {}).get("data", [])
    if not data:
        st.warning(f"No data found for {respondent} - {metric}")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["period"])
    df = df[["datetime", "value"]].rename(columns={"value": metric})
    return df

# --------------------------
# Load and Forecast
api_key = st.secrets.get("EIA_API_KEY", "DEMO_KEY")
load_df = fetch_eia_v2_hourly_series(selected_ba, "demand", api_key)

if not load_df.empty:
    st.subheader("Hourly Load and Forecast")
    st.line_chart(load_df.set_index("datetime"))

    df_p = load_df.rename(columns={load_df.columns[1]: "y", "datetime": "ds"})
    m = Prophet()
    m.fit(df_p)
    future = m.make_future_dataframe(periods=48, freq="H")
    forecast = m.predict(future)
    fig1 = px.line(forecast, x="ds", y=["yhat", "yhat_lower", "yhat_upper"], title="Load Forecast (Next 48h)")
    st.plotly_chart(fig1, use_container_width=True)

# --------------------------
# Renewables Integration
st.subheader("Renewable Integration: Wind + Solar vs Load")
wind_df = fetch_eia_v2_hourly_series(selected_ba, "wind", api_key)
solar_df = fetch_eia_v2_hourly_series(selected_ba, "solar", api_key)

if not wind_df.empty and not solar_df.empty and not load_df.empty:
    merged = load_df.merge(wind_df, on="datetime").merge(solar_df, on="datetime")
    fig2 = px.area(merged, x="datetime", y=[wind_df.columns[1], solar_df.columns[1], load_df.columns[1]],
                   title="Stacked Renewables vs Load", labels={"value": "MW"})
    st.plotly_chart(fig2, use_container_width=True)

# --------------------------
# Intertie Arbitrage
st.subheader("💵 Intertie Arbitrage Analysis")
ni_df = fetch_eia_v2_hourly_series(selected_ba, "net_interchange", api_key)
da_df = fetch_eia_v2_hourly_series(selected_ba, "lmp_da", api_key)
rt_df = fetch_eia_v2_hourly_series(selected_ba, "lmp_rt", api_key)

if not ni_df.empty and not da_df.empty and not rt_df.empty:
    merged_prices = da_df.merge(rt_df, on="datetime", suffixes=("_DA", "_RT")).merge(ni_df, on="datetime")
    merged_prices["Spread ($/MWh)"] = merged_prices[da_df.columns[1]] - merged_prices[rt_df.columns[1]]
    merged_prices.rename(columns={ni_df.columns[1]: "Net Interchange (MW)"}, inplace=True)

    fig3 = px.line(merged_prices, x="datetime", y=["Net Interchange (MW)", "Spread ($/MWh)"],
                   title="Net Interchange vs DA-RT Spread")
    st.plotly_chart(fig3, use_container_width=True)
    st.dataframe(merged_prices.tail(24))
else:
    st.info("Some intertie or price data is unavailable for this BA.")
