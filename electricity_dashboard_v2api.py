
import streamlit as st
import pandas as pd
import plotly.express as px
from prophet import Prophet
import requests
import datetime



def fetch_eia_v2_hourly_series(respondent: str, metric: str, api_key: str, start_date="2023-07-01", end_date="2023-07-15"):
    # Map metric to appropriate EIA v2 series ID
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

    series_metric = metric_map[metric]
    url = (
        f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
        f"?frequency=hourly"
        f"&data[0]=value"
        f"&facets[respondent][]={respondent}"
        f"&facets[type][]=ALL"
        f"&facets[metric][]={series_metric}"
        f"&start={start_date}T00"
        f"&end={end_date}T23"
        f"&sort[0][column]=period"
        f"&sort[0][direction]=asc"
        f"&api_key={api_key}"
    )

    r = requests.get(url)
    if r.status_code != 200:
        st.warning(f"EIA v2 API call failed for {respondent} {metric}")
        return pd.DataFrame()

    data = r.json().get("response", {}).get("data", [])
    if not data:
        st.warning(f"No data found for {respondent} {metric}")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["period"])
    df = df[["datetime", "value"]].rename(columns={"value": metric})
    return df


# --------------------------
# Setup
st.set_page_config(page_title="US Electricity Market Dashboard", layout="wide")
st.title("⚡ Electricity Market Analytics")
st.markdown("Live load, renewables, congestion & intertie metrics from EIA")

# --------------------------
# BA Selector
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
selected_ba = st.selectbox("Select Balancing Authority", list(ba_dict.keys()), format_func=lambda x: ba_dict[x])

# --------------------------
# Helper: Fetch EIA data

# OLD FETCH FUNCTION DISABLED\ndef fetch_eia_series(series_id, api_key):
    url = f"https://api.eia.gov/series/?api_key={api_key}&series_id={series_id}"
    r = requests.get(url)
    if r.status_code != 200:
        st.warning(f"EIA API call failed for {series_id}")
        return pd.DataFrame()

    json_data = r.json()
    if "series" not in json_data:
        st.warning(f"No data returned for {series_id}")
        return pd.DataFrame()

    try:
        data = json_data["series"][0]["data"]
        df = pd.DataFrame(data, columns=["datetime", "value"])
        df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d%H", errors="coerce")
        df = df.dropna(subset=["datetime"])
        df = df.sort_values("datetime")
        df = df.rename(columns={"value": series_id.split(".")[-2]})
        return df
    except Exception as e:
        st.error(f"Parsing error: {e}")
        return pd.DataFrame()


# --------------------------

# Load Data & Prophet Forecast
api_key = st.secrets.get("EIA_API_KEY", "DEMO_KEY")  # Replace with your EIA API key

load_id = f"EBA.{selected_ba}-ALL.D.H"
load_df = fetch_eia_series(load_id, api_key)

if not load_df.empty:
    st.subheader("Hourly Load and Forecast")
    st.line_chart(load_df.set_index("datetime"))

    # Prophet Forecast
    load_df_p = load_df.rename(columns={load_df.columns[1]: "y", "datetime": "ds"})
    m = Prophet()
    m.fit(load_df_p)
    future = m.make_future_dataframe(periods=48, freq="H")
    forecast = m.predict(future)

    fig1 = px.line(forecast, x="ds", y=["yhat", "yhat_lower", "yhat_upper"], title="Load Forecast (next 48h)")
    st.plotly_chart(fig1, use_container_width=True)

# --------------------------
# Renewable Integration
st.subheader("Renewable Integration: Wind + Solar vs Load")

wind_id = f"EBA.{selected_ba}-ALL.WD.H"
solar_id = f"EBA.{selected_ba}-ALL.SUN.H"

wind_df = fetch_eia_series(wind_id, api_key)
solar_df = fetch_eia_series(solar_id, api_key)

if not wind_df.empty and not solar_df.empty and not load_df.empty:
    merged = load_df.merge(wind_df, on="datetime").merge(solar_df, on="datetime")
    fig2 = px.area(merged, x="datetime", y=[wind_df.columns[1], solar_df.columns[1], load_df.columns[1]],
                   labels={"value": "MW"}, title="Stacked Renewable Generation vs Load")
    st.plotly_chart(fig2, use_container_width=True)

# --------------------------
# --------------------------
# Intertie Price Arbitrage Module
st.subheader("💵 Intertie Arbitrage Analysis")

# Fetch Net Interchange and LMPs
ni_id = f"EBA.{selected_ba}-ALL.NI.H"
da_id = f"EBA.{selected_ba}-ALL.DA.H"
rt_id = f"EBA.{selected_ba}-ALL.RT.H"

ni_df = fetch_eia_series(ni_id, api_key)
da_df = fetch_eia_series(da_id, api_key)
rt_df = fetch_eia_series(rt_id, api_key)

if not ni_df.empty and not da_df.empty and not rt_df.empty:
    merged_prices = da_df.merge(rt_df, on="datetime", suffixes=("_DA", "_RT")).merge(ni_df, on="datetime")
    merged_prices["Spread ($/MWh)"] = merged_prices[da_df.columns[1]] - merged_prices[rt_df.columns[1]]
    merged_prices.rename(columns={ni_df.columns[1]: "Net Interchange (MW)"}, inplace=True)

    fig3 = px.line(merged_prices, x="datetime", y=["Net Interchange (MW)", "Spread ($/MWh)"],
                   title="Net Interchange vs DA-RT Price Spread", labels={"value": "MW / $/MWh"})
    st.plotly_chart(fig3, use_container_width=True)

    st.dataframe(merged_prices.tail(24))
else:
    st.warning("Not enough data available to compute arbitrage metrics.")
st.subheader("Net Interchange (NI) and Price Spread")
st.markdown("_Module coming soon: compares NI and DA-RT LMP spread across BAs_")
