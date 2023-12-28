import dash
from dash import Input, Output, callback, State
import datetime
from garth import Client as GarthClient
from garth.exc import GarthHTTPError
import dash_core_components as dcc
import dash_html_components as html
import os
import pandas as pd
from datetime import date
from dash.dependencies import Input, Output
from dotenv import load_dotenv
import dash_auth


load_dotenv()

ACTIVITY_CACHE = {

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
                                  duration_h=activity["duration"]/(60*60)))
    return output


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
            html.P("Select account"),
            dcc.Dropdown(
                id="dropdown",
                options=[
                ],
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
    [Input("date-range-selector", "start_date"), Input("date-range-selector", "end_date"), Input("dropdown", "value")],
    [State("garmin_store", "data")],
    prevent_initial_call=True,
)
def on_date_change(start_date, end_date,account_value ,store_data):
    # check wheter logged in
    if account_value is None:
        return []
    # load client
    client = GarthClient()
    client.configure(domain="garmin.com")
    client.loads(store_data[account_value])
    hf_data = get_htr_time_in_zones(client,account_value, get_runs_by_date(client, start_date, end_date))
    if len(hf_data) == 0:
        df = pd.DataFrame(
            {
                "zoneNumber": [1, 2, 3, 4, 5],
                "secsInZone": [0, 0, 0, 0, 0],
                "activity_date": [start_date] * 5,
                "activity_id": ["1"] * 5,
                "duration_h": [0] * 5,
            }
        )
    else:
        df = pd.concat(hf_data)
    averages = df.groupby("zoneNumber").secsInZone.sum().div(df.secsInZone.sum()).mul(100).round(2).reset_index()
    # create stacked
    df_w_date = df.assign(activity_date=pd.to_datetime(df.activity_date))
    aggregations_by_date = df_w_date.groupby([pd.Grouper(key='activity_date', freq='7d'), "zoneNumber"]).secsInZone.sum().div(
    df_w_date.groupby([pd.Grouper(key='activity_date', freq='7d')]).secsInZone.sum()
    ).mul(100).unstack().reset_index()
    # create activity count
    activity_count = df_w_date.groupby([pd.Grouper(key='activity_date', freq='7d')]).activity_id.nunique().rename("activity_count").reset_index()
    # create training time
    training_time = df_w_date.drop_duplicates(subset="activity_id").groupby([pd.Grouper(key='activity_date', freq='7d')]).duration_h.sum().reset_index()
    return (
        generate_bar_chart(averages, len(hf_data)) 
        + generate_stacked_bars(aggregations_by_date)
        + generate_activity_count_chart(activity_count)
        + generate_training_time_chart(training_time)
    )

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
                      )],
        ),
    ],
)

if __name__ == "__main__":
    app.run_server(debug=True)
