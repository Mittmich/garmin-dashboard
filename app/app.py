import dash
from dash import Input, Output, callback, State, dash_table
import datetime
from garth import Client as GarthClient
from garth.exc import GarthHTTPError
import dash_core_components as dcc
import dash_html_components as html
import os
import pandas as pd
from datetime import date
from dash.dependencies import Input, Output
import dash_daq as daq
from dotenv import load_dotenv
import dash_auth
import plotly.graph_objects as go


load_dotenv()

ACTIVITY_CACHE = {

}

DETAIL_CACHE = {

}


def get_acitvity_hrt(client,user_name, activity_id):
    """
    Get heart rate time in zones for a given activity id
    """
    cache_key = f"{user_name}_{activity_id}"
    if cache_key in ACTIVITY_CACHE:
        return ACTIVITY_CACHE[cache_key]
    hrt = client.connectapi(f"/activity-service/activity/{activity_id}/hrTimeInZones")
    ACTIVITY_CACHE[cache_key] = hrt
    return hrt

def get_runs_by_date(client, start_date, end_date):
    """
    Get a list of activity ids for a given date range
    """
    params = {
        "activityType": "running",
        "startDate": start_date,
        "endDate": end_date,
    }
    activities = client.connectapi("/activitylist-service/activities/search/activities", params=params)
    return activities


def get_htr_time_in_zones(client,user_name, activities):
    """
    Get heart rate time in zones for a list of activity ids
    """
    output = []
    for activity in activities:
        # get activity date
        actid = activity["activityId"]
        hrt = pd.DataFrame(get_acitvity_hrt(client,user_name, actid))
        output.append(hrt.assign(activity_date=activity["startTimeLocal"],
                                  activity_id=actid,
                                  duration_h=activity["duration"]/(60*60),
                                  distance_km=activity["distance"]/(1000)))
    return output


def get_activity_details(client, activity_id):
    """Get detailed time-series metrics for an activity."""
    cache_key = f"details_{activity_id}"
    if cache_key in DETAIL_CACHE:
        return DETAIL_CACHE[cache_key]
    details = client.connectapi(
        f"/activity-service/activity/{activity_id}/details",
        params={"maxChartSize": 2000}
    )
    DETAIL_CACHE[cache_key] = details
    return details


def get_activity_splits(client, activity_id):
    """Get split data for an activity."""
    cache_key = f"splits_{activity_id}"
    if cache_key in DETAIL_CACHE:
        return DETAIL_CACHE[cache_key]
    splits = client.connectapi(f"/activity-service/activity/{activity_id}/splits")
    DETAIL_CACHE[cache_key] = splits
    return splits


def parse_activity_details(details):
    """Parse activity detail metrics into a DataFrame with distance, pace, and heart rate."""
    if not details or "metricDescriptors" not in details or "activityDetailMetrics" not in details:
        return pd.DataFrame()

    descriptors = {d["metricsIndex"]: d["key"] for d in details["metricDescriptors"]}

    rows = []
    for point in details["activityDetailMetrics"]:
        row = {}
        metrics = point.get("metrics", [])
        for idx, value in enumerate(metrics):
            if idx in descriptors and value is not None:
                row[descriptors[idx]] = value
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Find and normalize speed column to pace (min/km)
    speed_col = next((c for c in df.columns if "speed" in c.lower()), None)
    if speed_col:
        df["pace_min_km"] = df[speed_col].apply(
            lambda x: (1000 / (x * 60)) if x and x > 0 else None
        )

    # Find and normalize HR column
    hr_col = next((c for c in df.columns if "heartrate" in c.lower()), None)
    if hr_col:
        df["heart_rate"] = df[hr_col]

    # Find and normalize distance column
    dist_col = next((c for c in df.columns if "distance" in c.lower()), None)
    if dist_col:
        df["distance_m"] = df[dist_col]
        df["distance_km"] = df[dist_col] / 1000

    return df


def _format_duration(seconds):
    """Format duration in seconds to MM:SS."""
    if not seconds or seconds <= 0:
        return "-"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def _format_pace(speed_ms):
    """Convert speed in m/s to pace string MM:SS min/km."""
    if not speed_ms or speed_ms <= 0:
        return "-"
    pace_total_seconds = 1000 / speed_ms
    minutes = int(pace_total_seconds // 60)
    seconds = int(pace_total_seconds % 60)
    return f"{minutes}:{seconds:02d}"


def parse_splits(splits_data):
    """Parse split data into DataFrames for km splits and intervals."""
    km_splits = pd.DataFrame()
    intervals = pd.DataFrame()

    if not splits_data:
        return km_splits, intervals

    # Parse lap DTOs (intervals)
    laps = splits_data.get("lapDTOs", [])
    if laps:
        lap_rows = []
        for i, lap in enumerate(laps):
            avg_hr = lap.get("averageHR", 0)
            lap_rows.append({
                "Interval": i + 1,
                "Distance (km)": round(lap.get("distance", 0) / 1000, 2),
                "Duration": _format_duration(lap.get("duration", 0)),
                "Avg Pace (min/km)": _format_pace(lap.get("averageSpeed", 0)),
                "Avg HR (bpm)": int(round(avg_hr)) if avg_hr else "-",
            })
        intervals = pd.DataFrame(lap_rows)

    # Parse split summaries (per-km)
    for summary in splits_data.get("splitSummaries", []):
        split_type = summary.get("splitType", "")
        if "KILOMETER" in split_type.upper() or "DISTANCE" in split_type.upper():
            splits = summary.get("splits", [])
            if splits:
                split_rows = []
                for i, s in enumerate(splits):
                    avg_hr = s.get("averageHR", 0)
                    split_rows.append({
                        "Km": i + 1,
                        "Distance (km)": round(s.get("distance", 0) / 1000, 2),
                        "Duration": _format_duration(s.get("duration", 0)),
                        "Avg Pace (min/km)": _format_pace(s.get("averageSpeed", 0)),
                        "Avg HR (bpm)": int(round(avg_hr)) if avg_hr else "-",
                    })
                km_splits = pd.DataFrame(split_rows)
            break

    return km_splits, intervals


def description_card():
    """

    :return: A Div containing dashboard title & descriptions.
    """
    return html.Div(
        id="description-card",
        children=[
            html.H5("Garmin connect HFR"),
            html.Div(
                id="intro",
                children="Hear frequency range for a given date range",
            ),
        ],
    )


def generate_control_card():
    """

    :return: A Div containing controls for graphs.
    """
    return html.Div(
        id="control-card",
        children=[
            html.P("Add your Garmin credentials"),
            html.Div(
                id="login-fields",
                children=[
                    html.Label("Username"),
                    dcc.Input(id="username-input", type="text"),
                    html.Label("Password"),
                    dcc.Input(id="password-input", type="password"),
                    html.Div(id='container-button-basic',style={'margin':'5px'}, children=[
                        html.Button("Add account", id="login-button", n_clicks=0),
                    ]),
                    html.Div(id='account-message',style={'margin':'5px'}, children="")
                ],
            ),
            html.P("Select account", style={'margin':'5px'}),
            dcc.Dropdown(
                id="dropdown",
                options=[
                ],
            ),
            html.P('Settings'),
            html.Div(
                id="settings",
                children=[
                    *generate_toggle()
                ]
            ),
        ],
    )

def generate_date_selector():
    return [html.P("Select aggregation time interval"),
                dcc.DatePickerRange(
                    id="date-range-selector",
                    start_date_placeholder_text="Start Date",
                    end_date_placeholder_text="End Date",
                    start_date=date.today() - datetime.timedelta(days=30),
                    end_date=date.today(),
                )]

def generate_toggle():
    return [
            daq.BooleanSwitch(
                id='my-toggle-switch',
                label='Calendar weeks',
                on=True,
            )
        ]


def _get_training_string(n_trainings):
    if n_trainings == 0:
        return "No trainings"
    elif n_trainings == 1:
        return "1 training considered"
    else:
        return f"{n_trainings} trainings considered"

def generate_bar_chart(df, n_trainings):
    return [
            html.H5("Heart frequencey range"),
            html.H3(_get_training_string(n_trainings)),
            dcc.Graph(
                id="bar-chart",
                figure={
                    "data": [
                        {
                            "x": df["zoneNumber"],
                            "y": df["secsInZone"],
                            "type": "bar",
                            "marker": {"color": "#0074D9"},
                        }
                    ],
                    "layout": {
                        "title": {"text": "Heart frequency range"},
                        "height": 500,
                        "padding": 150,
                        "xaxis": {"title": "Zone Number"},
                        "yaxis": {"title": "% in zone"},
                    },
                },
            ),
    ]

def generate_stacked_bars(df):
    return [
        html.H5("Heart frequency range over time"),
        dcc.Graph(
            id="stacked-bars",
            figure={
                "data": [
                    {
                        "x": df["activity_date"],
                        "y": df[1],
                        "type": "bar",
                        "name": "Zone 1",
                    },
                    {
                        "x": df["activity_date"],
                        "y": df[2],
                        "type": "bar",
                        "name": "Zone 2",
                    },
                    {
                        "x": df["activity_date"],
                        "y": df[3],
                        "type": "bar",
                        "name": "Zone 3",
                    },
                    {
                        "x": df["activity_date"],
                        "y": df[4],
                        "type": "bar",
                        "name": "Zone 4",
                    },
                    {
                        "x": df["activity_date"],
                        "y": df[5],
                        "type": "bar",
                        "name": "Zone 5",
                    },
                ],
                "layout": {
                    "title": {"text": "Heart frequency range over time [7 day average]"},
                    "barmode": "stack",
                    "xaxis": {"title": "Date"},
                    "yaxis": {"title": "Frequency"},
                },
            },
        ),
    ]


def generate_activity_count_chart(df):
    return [
        html.H5("Activity count"),
        dcc.Graph(
            id="activity-count-chart",
            figure={
                "data": [
                    {
                        "x": df["activity_date"],
                        "y": df["activity_count"],
                        "type": "bar",
                        "marker": {"color": "#0074D9"},
                    }
                ],
                "layout": {
                    "title": {"text": "Activity count"},
                    "height": 500,
                    "padding": 150,
                    "xaxis": {"title": "Date"},
                    "yaxis": {"title": "Activity count"},
                },
            },
        ),
    ]

def generate_training_time_chart(df):
    return [
        html.H5("Training time"),
        dcc.Graph(
            id="training-time-chart",
            figure={
                "data": [
                    {
                        "x": df["activity_date"],
                        "y": df["duration_h"],
                        "type": "bar",
                        "marker": {"color": "#0074D9"},
                    }
                ],
                "layout": {
                    "title": {"text": "Training time"},
                    "height": 500,
                    "padding": 150,
                    "xaxis": {"title": "Date"},
                    "yaxis": {"title": "Training time [h]"},
                },
            },
        ),
    ]

def generate_training_distance_chart(df):
    return [
        html.H5("Training distance"),
        dcc.Graph(
            id="training-distance-chart",
            figure={
                "data": [
                    {
                        "x": df["activity_date"],
                        "y": df["distance_km"],
                        "type": "bar",
                        "marker": {"color": "#0074D9"},
                    }
                ],
                "layout": {
                    "title": {"text": "Training distance"},
                    "height": 500,
                    "padding": 150,
                    "xaxis": {"title": "Date"},
                    "yaxis": {"title": "Training distance [km]"},
                },
            }
        ),
    ]


def generate_pace_profile(df):
    """Generate pace profile graph with heatmap coloring, pannable and zoomable."""
    if df.empty or "pace_min_km" not in df.columns or "distance_km" not in df.columns:
        return html.Div("No pace data available")

    plot_df = df.dropna(subset=["pace_min_km", "distance_km"]).copy()
    if plot_df.empty:
        return html.Div("No pace data available")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["distance_km"],
        y=plot_df["pace_min_km"],
        mode="markers+lines",
        marker=dict(
            color=plot_df["pace_min_km"],
            colorscale="RdYlGn",
            colorbar=dict(title="Pace<br>(min/km)"),
            size=5,
        ),
        line=dict(color="rgba(150,150,150,0.3)", width=1),
        hovertemplate="Distance: %{x:.2f} km<br>Pace: %{y:.2f} min/km<extra></extra>",
    ))

    fig.update_layout(
        title="Pace Profile",
        xaxis_title="Distance (km)",
        yaxis_title="Pace (min/km)",
        yaxis=dict(autorange="reversed"),
        dragmode="pan",
        height=400,
        template="plotly_white",
    )

    return dcc.Graph(
        id="pace-profile-graph",
        figure=fig,
        config={"scrollZoom": True, "displayModeBar": True},
    )


def generate_hr_profile(df):
    """Generate heart rate profile graph with heatmap coloring, pannable and zoomable."""
    if df.empty or "heart_rate" not in df.columns or "distance_km" not in df.columns:
        return html.Div("No heart rate data available")

    plot_df = df.dropna(subset=["heart_rate", "distance_km"]).copy()
    if plot_df.empty:
        return html.Div("No heart rate data available")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["distance_km"],
        y=plot_df["heart_rate"],
        mode="markers+lines",
        marker=dict(
            color=plot_df["heart_rate"],
            colorscale="YlOrRd",
            colorbar=dict(title="HR<br>(bpm)"),
            size=5,
        ),
        line=dict(color="rgba(150,150,150,0.3)", width=1),
        hovertemplate="Distance: %{x:.2f} km<br>HR: %{y:.0f} bpm<extra></extra>",
    ))

    fig.update_layout(
        title="Heart Rate Profile",
        xaxis_title="Distance (km)",
        yaxis_title="Heart Rate (bpm)",
        dragmode="pan",
        height=400,
        template="plotly_white",
    )

    return dcc.Graph(
        id="hr-profile-graph",
        figure=fig,
        config={"scrollZoom": True, "displayModeBar": True},
    )


def generate_km_table(km_splits):
    """Generate a DataTable for per-km splits with average pace and heart rate."""
    if km_splits.empty:
        return html.Div("No km split data available")

    return html.Div([
        html.H5("Km Splits"),
        dash_table.DataTable(
            id="km-splits-table",
            columns=[{"name": col, "id": col} for col in km_splits.columns],
            data=km_splits.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "center", "padding": "8px", "fontSize": "13px"},
            style_header={
                "backgroundColor": "#0074D9",
                "color": "white",
                "fontWeight": "bold",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#f9f9f9"},
            ],
        ),
    ])


def generate_interval_table(intervals):
    """Generate a DataTable for intervals/laps with average pace and heart rate."""
    if intervals.empty:
        return html.Div("No interval data available")

    return html.Div([
        html.H5("Intervals"),
        dash_table.DataTable(
            id="intervals-table",
            columns=[{"name": col, "id": col} for col in intervals.columns],
            data=intervals.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "center", "padding": "8px", "fontSize": "13px"},
            style_header={
                "backgroundColor": "#0074D9",
                "color": "white",
                "fontWeight": "bold",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#f9f9f9"},
            ],
        ),
    ])


app = dash.Dash(__name__, suppress_callback_exceptions = True)
auth = dash_auth.BasicAuth(
    app,
    {
        os.getenv("DASH_USER"): os.getenv("DASH_PW")
    }
)

# handlers

@callback(
    Output('garmin_store', 'data'),
    Output('account-message', 'children'),
    Output('username-input', 'value'),
    Output('password-input', 'value'),
    inputs=[Input('login-button', 'n_clicks')],
    state=[State('username-input', 'value'), State('password-input', 'value'),
            State('garmin_store', 'data')],
    prevent_initial_call=True
)
def on_click(n_clicks, username, password, data):
    if username is None or password is None:
        return None, "Please enter username and password", username, password
    # try login
    try:
        client = GarthClient()
        client.configure(domain="garmin.com")
        client.login(username, password)
    except GarthHTTPError as e:
        return None, "Login failed", "", ""
    # load store data
    if data is None:
        json_output = {}
    else:
        json_output = data
    # store token in store
    json_output[username] = client.dumps()
    return json_output, "Account added", "", ""

@callback(
    Output("bar-chart-card", "children"),
    Output("activity-selector", "options"),
    Output("activity-selector", "value"),
    [Input("date-range-selector", "start_date"),
     Input("date-range-selector", "end_date"),
     Input("dropdown", "value"),
     Input('my-toggle-switch', 'on')
     ],
    [State("garmin_store", "data")],
    prevent_initial_call=True,
)
def on_date_change(start_date, end_date,account_value ,use_calendar_weeks,store_data):
    # check wheter logged in
    if account_value is None:
        return [], [], None
    # load client
    client = GarthClient()
    client.configure(domain="garmin.com")
    client.loads(store_data[account_value])
    activities = get_runs_by_date(client, start_date, end_date)
    hf_data = get_htr_time_in_zones(client,account_value, activities)

    # Build activity dropdown options
    activity_options = []
    for a in activities:
        name = a.get("activityName", "Activity")
        date_str = a.get("startTimeLocal", "")[:10]
        distance = round(a.get("distance", 0) / 1000, 1)
        activity_options.append({
            "label": f"{name} - {date_str} ({distance} km)",
            "value": a["activityId"],
        })

    if len(hf_data) == 0:
        df = pd.DataFrame(
            {
                "zoneNumber": [1, 2, 3, 4, 5],
                "secsInZone": [0, 0, 0, 0, 0],
                "activity_date": [start_date] * 5,
                "activity_id": ["1"] * 5,
                "duration_h": [0] * 5,
                "distance_km": [0] * 5,
            }
        )
    else:
        df = pd.concat(hf_data)
    averages = df.groupby("zoneNumber").secsInZone.sum().div(df.secsInZone.sum()).mul(100).round(2).reset_index()
    # decide on calendar weeks
    if use_calendar_weeks:
        rounding_string = "W-MON"
    else:
        rounding_string = "7d"
    # create stacked
    df_w_date = df.assign(activity_date=pd.to_datetime(df.activity_date))
    aggregations_by_date = df_w_date.groupby([pd.Grouper(key='activity_date', freq=rounding_string, label='left'), "zoneNumber"]).secsInZone.sum().div(
    df_w_date.groupby([pd.Grouper(key='activity_date', freq=rounding_string, label='left')]).secsInZone.sum()
    ).mul(100).unstack().reset_index()
    # create activity count
    activity_count = df_w_date.groupby([pd.Grouper(key='activity_date', freq=rounding_string, label='left')]).activity_id.nunique().rename("activity_count").reset_index()
    # create training time
    training_time = df_w_date.drop_duplicates(subset="activity_id").groupby([pd.Grouper(key='activity_date', freq=rounding_string, label='left')]).duration_h.sum().reset_index()
    # create training distance
    training_distance = df_w_date.drop_duplicates(subset="activity_id").groupby([pd.Grouper(key='activity_date', freq=rounding_string, label='left')]).distance_km.sum().reset_index()
    return (
        generate_bar_chart(averages, len(hf_data)) 
        + generate_stacked_bars(aggregations_by_date)
        + generate_activity_count_chart(activity_count)
        + generate_training_time_chart(training_time)
        + generate_training_distance_chart(training_distance)
    ), activity_options, None

@callback(
    Output("dropdown", "options"),
    [Input("garmin_store", "data")],
)
def get_accounts(data):
    if data is None:
        return []
    return [
        {
            "label": key,
            "value": key,
        } for key in data.keys()
    ]

@callback(
    Output("activity-detail-card", "children"),
    [Input("activity-selector", "value")],
    [State("garmin_store", "data"),
     State("dropdown", "value")],
    prevent_initial_call=True,
)
def on_activity_select(activity_id, store_data, account_value):
    """Fetch and display detailed pace/HR profiles and split tables for a selected activity."""
    if activity_id is None or store_data is None or account_value is None:
        return []

    client = GarthClient()
    client.configure(domain="garmin.com")
    client.loads(store_data[account_value])

    details = get_activity_details(client, activity_id)
    splits_data = get_activity_splits(client, activity_id)

    detail_df = parse_activity_details(details)
    km_splits, intervals = parse_splits(splits_data)

    components = []
    components.append(generate_pace_profile(detail_df))
    components.append(generate_hr_profile(detail_df))
    components.append(generate_km_table(km_splits))
    components.append(generate_interval_table(intervals))

    return components


app.layout = html.Div(
    id="app-container",
    children=[
        dcc.Store(id="garmin_store", storage_type='local'),
        # Banner
        html.Div(
            id="banner",
            className="banner",
            children=[html.Img(src=app.get_asset_url("plotly_logo.png"))],
        ),
        # Left column
        html.Div(
            id="left-column",
            className="four columns",
            children=[description_card(), generate_control_card()]
            + [
                html.Div(
                    ["initial child"], id="output-clientside", style={"display": "none"}
                )
            ],
        ),
        # Right column
        html.Div(
            id="right-column",
            className="eight columns",
            children=[*generate_date_selector(),
                      html.Div(
                          id="bar-chart-card",
                          children=[]
                      ),
                      html.Hr(),
                      html.H5("Activity Details"),
                      html.P("Select an activity to view detailed pace and heart rate profiles"),
                      dcc.Dropdown(
                          id="activity-selector",
                          options=[],
                          placeholder="Select an activity...",
                      ),
                      html.Div(
                          id="activity-detail-card",
                          children=[]
                      ),
                      ],
        ),
    ],
)

if __name__ == "__main__":
    app.run_server(host='0.0.0.0', debug=False)
