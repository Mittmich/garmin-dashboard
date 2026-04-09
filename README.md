# 🏃 Garmin Dashboard

A web-based dashboard for visualizing your Garmin Connect running data. Built with [Plotly Dash](https://dash.plotly.com/) and powered by [Garth](https://github.com/matin/garth) for Garmin Connect API access.

## Features

- **Heart Rate Zone Analysis** — View time spent in each heart rate zone across your runs
- **Heart Rate Zones Over Time** — Track how your heart rate zone distribution changes week by week
- **Activity Count** — See how many runs you completed per week
- **Training Duration** — Monitor your weekly training time in hours
- **Training Distance** — Track your weekly running distance in kilometers
- **Multi-Account Support** — Add and switch between multiple Garmin Connect accounts
- **Calendar Week Aggregation** — Toggle between calendar weeks and rolling 7-day windows
- **Date Range Selection** — Filter data to any custom date range

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- A [Garmin Connect](https://connect.garmin.com/) account
- SSL certificates for the Nginx reverse proxy (see [SSL Setup](#ssl-setup))

## Quick Start

1. **Clone the repository**

   ```bash
   git clone https://github.com/Mittmich/garmin-dashboard.git
   cd garmin-dashboard
   ```

2. **Create a `.env` file** in the project root with your dashboard credentials:

   ```env
   DASH_USER=your_dashboard_username
   DASH_PW=your_dashboard_password
   ```

   These credentials protect access to the dashboard itself (HTTP Basic Auth) — they are _not_ your Garmin credentials.

3. **Set up SSL certificates** (see [SSL Setup](#ssl-setup))

4. **Start the application**

   ```bash
   docker compose up --build
   ```

5. **Open your browser** and navigate to `https://localhost`. Log in with the `DASH_USER` / `DASH_PW` credentials you configured.

6. **Add your Garmin account** using the login form in the left panel, select it from the dropdown, choose a date range, and explore your data.

## SSL Setup

The Nginx reverse proxy expects SSL certificates at `nginx-server/certificates/`. You can generate self-signed certificates for local development:

```bash
mkdir -p nginx-server/certificates
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx-server/certificates/nginx-selfsigned.key \
  -out nginx-server/certificates/nginx-selfsigned.crt \
  -subj "/CN=localhost"
```

For production use, replace these with certificates from a trusted certificate authority.

## Architecture

```
┌──────────┐       ┌───────────────┐       ┌──────────────────┐
│  Browser  │──────▶│  Nginx (443)  │──────▶│  Dash App (8050) │
│           │◀──────│  reverse proxy│◀──────│  Python / Plotly  │
└──────────┘       └───────────────┘       └──────────────────┘
                                                   │
                                                   ▼
                                           ┌──────────────┐
                                           │ Garmin Connect│
                                           │     API       │
                                           └──────────────┘
```

| Service    | Description                                          |
|------------|------------------------------------------------------|
| `flask-app`| Dash application serving interactive charts on `:8050` |
| `nginx`    | Reverse proxy with SSL termination on `:443`          |

## Running Without Docker

If you prefer to run the app directly:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file as described above, then:

```bash
cd app
python app.py
```

The dashboard will be available at `http://localhost:8050`.

## Tech Stack

| Component        | Technology                                          |
|------------------|-----------------------------------------------------|
| Web Framework    | [Dash](https://dash.plotly.com/)                      |
| Garmin API Client| [Garth](https://github.com/matin/garth)               |
| Data Processing  | [Pandas](https://pandas.pydata.org/)                  |
| Auth             | [Dash Auth](https://dash.plotly.com/authentication)   |
| Reverse Proxy    | [Nginx](https://nginx.org/)                          |
| Containerization | [Docker](https://www.docker.com/) + Docker Compose   |

## License

This project is provided as-is. See the repository for license details.
