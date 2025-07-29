
import streamlit as st
import pandas as pd
import plotly.express as px
from prophet import Prophet
import requests
import datetime




def fetch_eia_v2_hourly_series(respondent: str, metric: str, api_key: str):
    # Rolling date range (last 7 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

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
        f"&start={start_str}T00"
        f"&end={end_str}T23"
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


